// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! 9.3 Source-grounded card generation.
//!
//! Generates N candidate cards from a *registered* source. Generation is
//! rejected outright if no valid source is supplied (fake-source defence, 9.9).
//! Each candidate carries its source name/section, question, answer, topic tag
//! and difficulty, is duplicate-checked and passed through the 9.4 quality
//! checker, and lands in a review queue with a status — never auto-added to the
//! study deck. Acceptance turns a candidate into a real, tagged note.

use std::sync::Arc;

use anki_proto::mcat as pb;
use serde::Deserialize;

use super::complete_json;
use super::prompt::fence_source;
use super::prompt::DATA_ONLY_INSTRUCTION;
use super::AiError;
use super::AiResult;
use super::AiTask;
use super::ChatRequest;
use crate::notetype::Notetype;
use crate::prelude::*;

/// Default destination deck for accepted AI cards.
const DEFAULT_AI_DECK: &str = "MCAT::AI Generated";
/// Label applied to every accepted AI card.
pub(crate) const AI_LABEL_TAG: &str = "ai-generated";

/// The three difficulty tiers spanned by the deck. Kept as an ordered slice so
/// callers (and the deck-build pipeline) share one vocabulary.
///
/// * `recall`  — basic recall / definition.
/// * `mcat`    — exam-level application / reasoning (the standard MCAT band).
/// * `stretch` — harder than the real MCAT: multi-concept integration, edge
///   cases, wider scope.
pub(crate) const DIFFICULTY_TIERS: [&str; 3] = ["recall", "mcat", "stretch"];

/// Tag namespace applied on acceptance so every card advertises its tier, e.g.
/// `difficulty::stretch`. This is what makes the wide difficulty range visible
/// and filterable in the deck.
pub(crate) const DIFFICULTY_TAG_PREFIX: &str = "difficulty";

/// Tag namespace recording the named source an accepted AI card was grounded
/// in, e.g. `ai-source::src-1712345`. It makes the source trace filterable in
/// the browser and survives sync; the value is the registered source id, which
/// resolves back (via the source registry) to the full name/section/excerpt.
pub(crate) const SOURCE_TAG_PREFIX: &str = "ai-source";

/// A human-readable "Source: …" line appended to an accepted card's answer so
/// the named source is visible during review (schema → stored → surfaced in
/// the UI). Empty when no source name is available.
pub(crate) fn source_citation_line(source_name: &str, source_section: &str) -> String {
    let name = source_name.trim();
    if name.is_empty() {
        return String::new();
    }
    let section = source_section.trim();
    if section.is_empty() {
        format!("Source: {name}")
    } else {
        format!("Source: {name} — {section}")
    }
}

/// Turn a source id into a tag-safe token (tags may not contain whitespace).
pub(crate) fn source_tag(source_id: &str) -> Option<String> {
    let id = source_id.trim();
    if id.is_empty() {
        return None;
    }
    let safe: String = id
        .chars()
        .map(|c| if c.is_whitespace() { '_' } else { c })
        .collect();
    Some(format!("{SOURCE_TAG_PREFIX}::{safe}"))
}

#[derive(Deserialize)]
struct AiGenerateResponse {
    cards: Vec<AiGeneratedCard>,
}

#[derive(Deserialize)]
struct AiGeneratedCard {
    #[serde(default)]
    question: String,
    #[serde(default)]
    answer: String,
    #[serde(default)]
    topic_tag: String,
    #[serde(default)]
    difficulty: String,
}

impl Collection {
    /// Locate a Basic-style notetype (>= 2 fields) for created cards.
    pub(crate) fn mcat_basic_notetype(&mut self) -> Result<Arc<Notetype>> {
        if let Some(id) = self.storage.get_notetype_id("Basic")? {
            if let Some(nt) = self.get_notetype(id)? {
                return Ok(nt);
            }
        }
        for (id, _name) in self.storage.get_all_notetype_names()? {
            if let Some(nt) = self.get_notetype(id)? {
                if nt.fields.len() >= 2 {
                    return Ok(nt);
                }
            }
        }
        invalid_input!("no suitable notetype found to create cards");
    }

    pub(crate) fn mcat_generate_cards(
        &mut self,
        req: pb::GenerateCardsRequest,
    ) -> Result<pb::GeneratedCardList> {
        // Fake-source defence: a valid registered source is mandatory.
        let source = match self.mcat_find_source(&req.source_id) {
            Some(s) => s,
            None => {
                return Ok(pb::GeneratedCardList {
                    ai_available: false,
                    unavailable_reason: "No registered source supplied. Register a source before \
                                         generating cards."
                        .to_string(),
                    cards: vec![],
                    source_id: req.source_id.clone(),
                });
            }
        };

        let client = self.mcat_ai_client();
        if !client.config().available() {
            return Ok(pb::GeneratedCardList {
                ai_available: false,
                unavailable_reason: client.config().status_reason(),
                cards: vec![],
                source_id: source.source_id.clone(),
            });
        }

        let count = req.count.clamp(1, 20);
        // A requested tier (recall/mcat/stretch) is authoritative for tagging and
        // steers the prompt; empty asks the model for a mixed batch.
        let requested_tier = normalize_difficulty_opt(&req.difficulty);
        let generated = match generate_from_source(
            &client,
            &source,
            count,
            &req.topic_hint,
            requested_tier.as_deref(),
        ) {
            Ok(g) => g,
            Err(e) => {
                return Ok(pb::GeneratedCardList {
                    ai_available: false,
                    unavailable_reason: e.reason(),
                    cards: vec![],
                    source_id: source.source_id.clone(),
                });
            }
        };

        let cutoff = client.config().checker_cutoff;
        let mut cards = Vec::new();
        for gc in generated.cards {
            if gc.question.trim().is_empty() || gc.answer.trim().is_empty() {
                continue;
            }
            let topic_tag = if gc.topic_tag.trim().is_empty() {
                req.topic_hint.clone()
            } else {
                gc.topic_tag.trim().to_string()
            };

            let check_req = pb::CheckCardRequest {
                question: gc.question.clone(),
                answer: gc.answer.clone(),
                topic_tag: topic_tag.clone(),
                source_id: source.source_id.clone(),
                source_excerpt: source.excerpt.clone(),
                tag_prefix: req.tag_prefix.clone(),
            };
            let dupe = self.mcat_duplicate_check(&gc.question, &gc.answer, &req.tag_prefix, 0.8)?;
            let taxonomy = crate::mcat::taxonomy::Taxonomy::load();
            let tagged_ok = tag_in_taxonomy(&taxonomy, &req.tag_prefix, &topic_tag);
            let source_supported = answer_supported(&source.excerpt, &gc.answer);
            let report = self.mcat_run_checker(
                &client,
                &check_req,
                &dupe,
                tagged_ok,
                source_supported,
                cutoff,
            );

            let status = if dupe.is_duplicate {
                pb::GeneratedCardStatus::Duplicate
            } else if report.passed {
                pb::GeneratedCardStatus::NeedsReview
            } else {
                pb::GeneratedCardStatus::Blocked
            };

            // A caller-requested tier wins (the model was told to write at that
            // tier); otherwise fall back to the model's per-card label.
            let difficulty = requested_tier
                .clone()
                .unwrap_or_else(|| normalize_difficulty(&gc.difficulty));

            cards.push(pb::GeneratedCard {
                source_id: source.source_id.clone(),
                source_name: source.source_name.clone(),
                source_section: source.source_section.clone(),
                question: gc.question.trim().to_string(),
                answer: gc.answer.trim().to_string(),
                topic_tag,
                difficulty,
                status: status as i32,
                quality: Some(report),
                source_excerpt: source.excerpt.clone(),
            });
        }

        Ok(pb::GeneratedCardList {
            ai_available: true,
            unavailable_reason: String::new(),
            cards,
            source_id: source.source_id.clone(),
        })
    }

    /// Turn accepted candidates into real, tagged notes in the MCAT deck.
    /// Blocked/duplicate cards are skipped defensively (nothing untrusted
    /// enters the deck).
    pub(crate) fn mcat_accept_cards(
        &mut self,
        req: pb::AcceptCardsRequest,
    ) -> Result<pb::AcceptCardsResponse> {
        let deck_name = if req.deck_name.trim().is_empty() {
            DEFAULT_AI_DECK.to_string()
        } else {
            req.deck_name.trim().to_string()
        };
        let did = self.get_or_create_normal_deck(&deck_name)?.id;
        let notetype = self.mcat_basic_notetype()?;

        let mut note_ids = Vec::new();
        let mut skipped = 0u32;
        for card in &req.cards {
            let status = pb::GeneratedCardStatus::try_from(card.status).unwrap_or_default();
            let blocked = matches!(
                status,
                pb::GeneratedCardStatus::Blocked | pb::GeneratedCardStatus::Duplicate
            );
            if blocked || card.question.trim().is_empty() || card.answer.trim().is_empty() {
                skipped += 1;
                continue;
            }
            let mut note = notetype.new_note();
            note.set_field(0, &card.question)?;
            // Every accepted card keeps a visible "Source: …" citation so the
            // named source it was grounded in travels with the card into review.
            let citation = source_citation_line(&card.source_name, &card.source_section);
            let back = if citation.is_empty() {
                card.answer.trim().to_string()
            } else {
                format!("{}\n\n{}", card.answer.trim(), citation)
            };
            note.set_field(1, &back)?;
            let mut tags = vec![AI_LABEL_TAG.to_string()];
            if !card.topic_tag.trim().is_empty() {
                tags.push(card.topic_tag.trim().to_string());
            }
            // Tag the difficulty tier so the deck spans (and is filterable by) a
            // wide, measurable difficulty range: difficulty::{recall,mcat,stretch}.
            if let Some(tier) = normalize_difficulty_opt(&card.difficulty) {
                tags.push(format!("{DIFFICULTY_TAG_PREFIX}::{tier}"));
            }
            // Machine-readable source trace: ai-source::<source_id> resolves back
            // to the registered source (name/section/excerpt) and is filterable.
            if let Some(tag) = source_tag(&card.source_id) {
                tags.push(tag);
            }
            note.tags = tags;
            self.add_note(&mut note, did)?;
            note_ids.push(note.id.0);
        }

        Ok(pb::AcceptCardsResponse {
            created: note_ids.len() as u32,
            note_ids,
            skipped,
        })
    }
}

/// Map any difficulty label the model (or a caller) might use onto one of the
/// three canonical tiers, always returning a tier (defaults to the standard
/// `mcat` band). Legacy easy/medium/hard values are accepted too.
pub(crate) fn normalize_difficulty(d: &str) -> String {
    match d.trim().to_lowercase().as_str() {
        "recall" | "easy" | "basic" | "definition" | "e" => "recall".to_string(),
        "stretch" | "hard" | "advanced" | "expert" | "integration" | "h" => "stretch".to_string(),
        _ => "mcat".to_string(),
    }
}

/// Like [`normalize_difficulty`] but returns `None` for an empty/blank input,
/// so callers can distinguish "no tier requested" (mixed batch) from an
/// explicit tier.
pub(crate) fn normalize_difficulty_opt(d: &str) -> Option<String> {
    if d.trim().is_empty() {
        None
    } else {
        Some(normalize_difficulty(d))
    }
}

/// Human-facing guidance describing what a card at the given tier should test.
/// Fed into the generation prompt so questions match MCAT-style scope per tier
/// rather than generic trivia.
pub(crate) fn tier_guidance(tier: &str) -> &'static str {
    match tier {
        "recall" => {
            "Write BASIC RECALL cards: a single definition, fact, term or value \
             stated directly in the source. One step, no reasoning chain."
        }
        "stretch" => {
            "Write STRETCH cards that are HARDER than the real MCAT: integrate \
             multiple concepts from the source, probe edge cases, quantitative \
             reasoning or second-order consequences, and require several \
             inferential steps. Still fully grounded in the source — never \
             invent facts."
        }
        // "mcat" and anything else.
        _ => {
            "Write EXAM-LEVEL cards at standard MCAT difficulty: apply a concept \
             from the source to a scenario or require one or two reasoning steps, \
             not mere recall."
        }
    }
}

fn tag_in_taxonomy(
    taxonomy: &crate::mcat::taxonomy::Taxonomy,
    tag_prefix: &str,
    topic_tag: &str,
) -> bool {
    let prefix = if tag_prefix.trim().is_empty() {
        taxonomy.tag_prefix.clone()
    } else {
        tag_prefix.trim().to_string()
    };
    taxonomy.sections.iter().any(|s| {
        s.topics
            .iter()
            .any(|t| format!("{}::{}::{}", prefix, s.key, t.key) == topic_tag)
    })
}

fn answer_supported(excerpt: &str, answer: &str) -> bool {
    if excerpt.trim().is_empty() {
        return false;
    }
    let ex: std::collections::HashSet<String> = super::checker::normalize_tokens(excerpt)
        .into_iter()
        .collect();
    let ans = super::checker::normalize_tokens(answer);
    let content: Vec<&String> = ans.iter().filter(|t| t.len() > 3).collect();
    if content.is_empty() {
        let low = excerpt.to_lowercase();
        return ans.iter().any(|t| low.contains(t.as_str()));
    }
    let hits = content.iter().filter(|t| ex.contains(**t)).count();
    hits as f64 / content.len() as f64 >= 0.4
}

fn generate_from_source(
    client: &dyn super::AiClient,
    source: &crate::mcat::ai::sources::StoredSource,
    count: u32,
    topic_hint: &str,
    tier: Option<&str>,
) -> AiResult<AiGenerateResponse> {
    if !client.config().available() {
        return Err(AiError::Unconfigured {
            reason: client.config().status_reason(),
        });
    }
    let fenced = fence_source(&source.source_name, &source.source_section, &source.excerpt);
    let system = format!(
        "You are an expert MCAT tutor writing high-quality flashcards ONLY from the \
         provided source material. {DATA_ONLY_INSTRUCTION} Produce strict JSON of the \
         form {{\"cards\":[{{\"question\":\"...\",\"answer\":\"...\",\"topic_tag\":\"mcat::section::topic\",\"difficulty\":\"recall|mcat|stretch\"}}]}}. \
         Every fact must be supported by the source. Do not invent facts not present in \
         the source."
    );
    // Difficulty steering: a specific tier writes the whole batch at that band;
    // no tier asks for an explicit spread across all three so the deck covers a
    // wide range (including the middle).
    let difficulty_directive = match tier {
        Some(t) => format!(
            "{} Set every card's \"difficulty\" to \"{t}\".",
            tier_guidance(t)
        ),
        None => format!(
            "Produce a MIX of difficulties and label each card's \"difficulty\" \
             accordingly. {} {} {}",
            tier_guidance("recall"),
            tier_guidance("mcat"),
            tier_guidance("stretch"),
        ),
    };
    let user = format!(
        "Write {count} MCAT flashcards grounded in the following source.{hint} \
         {difficulty_directive}\n\n{fenced}",
        hint = if topic_hint.trim().is_empty() {
            String::new()
        } else {
            format!(" Prefer the topic tag {}.", topic_hint.trim())
        },
    );
    let payload = serde_json::json!({
        "source_name": source.source_name,
        "source_section": source.source_section,
        "excerpt": source.excerpt,
        "topic_hint": topic_hint,
        "count": count,
        "difficulty": tier.unwrap_or(""),
    });
    let chat = ChatRequest::new(AiTask::GenerateCards, system, user).with_payload(payload);
    complete_json::<AiGenerateResponse>(client, &chat)
}
