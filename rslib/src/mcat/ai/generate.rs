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
        let generated = match generate_from_source(&client, &source, count, &req.topic_hint) {
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

            cards.push(pb::GeneratedCard {
                source_id: source.source_id.clone(),
                source_name: source.source_name.clone(),
                source_section: source.source_section.clone(),
                question: gc.question.trim().to_string(),
                answer: gc.answer.trim().to_string(),
                topic_tag,
                difficulty: normalize_difficulty(&gc.difficulty),
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
            note.set_field(1, &card.answer)?;
            let mut tags = vec![AI_LABEL_TAG.to_string()];
            if !card.topic_tag.trim().is_empty() {
                tags.push(card.topic_tag.trim().to_string());
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

fn normalize_difficulty(d: &str) -> String {
    match d.trim().to_lowercase().as_str() {
        "easy" | "e" => "easy".to_string(),
        "hard" | "h" => "hard".to_string(),
        _ => "medium".to_string(),
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
         form {{\"cards\":[{{\"question\":\"...\",\"answer\":\"...\",\"topic_tag\":\"mcat::section::topic\",\"difficulty\":\"easy|medium|hard\"}}]}}. \
         Every fact must be supported by the source. Do not invent facts not present in \
         the source."
    );
    let user = format!(
        "Write {count} MCAT flashcards grounded in the following source.{hint}\n\n{fenced}",
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
    });
    let chat = ChatRequest::new(AiTask::GenerateCards, system, user).with_payload(payload);
    complete_json::<AiGenerateResponse>(client, &chat)
}
