// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! 9.4 AI Card Quality Checker.
//!
//! Every AI-generated card passes this gate before a student can see it. Each
//! category yields pass/fail + score + reason. The passing cutoff is
//! configurable and stored in config (default [`DEFAULT_CHECKER_CUTOFF`]) so it
//! is fixed *before* testing. Wrong / vague / trivial / duplicate /
//! unsupported cards are Blocked. When AI is unavailable the card is Blocked
//! (never auto-trusted), keeping the app safe with AI off.

use anki_proto::mcat as pb;
use serde::Deserialize;

use super::complete_json;
use super::AiClient;
use super::AiError;
use super::AiResult;
use super::AiTask;
use super::ChatRequest;
use crate::mcat::taxonomy::Taxonomy;
use crate::prelude::*;
use crate::search::SortMode;

/// Categories the model judges. The Rust side adds not_duplicate,
/// properly_tagged and source_supported.
const AI_CATEGORIES: &[(&str, &str)] = &[
    ("factually_correct", "Factually correct"),
    ("useful_for_mcat", "Useful for the MCAT"),
    ("clear_question", "Clear question"),
    ("clear_answer", "Clear answer"),
    ("not_vague", "Not vague"),
    ("not_too_trivial", "Not too trivial"),
];

/// Hard-fail categories: if any of these fails, the card is Blocked regardless
/// of the overall score. Covers the rubric's "wrong / vague / trivial /
/// duplicate / unsupported" cards.
const HARD_FAIL: &[&str] = &[
    "factually_correct",
    "not_duplicate",
    "source_supported",
    "not_vague",
    "not_too_trivial",
];

#[derive(Deserialize)]
struct AiCheckResponse {
    categories: Vec<AiCheckCategory>,
}

#[derive(Deserialize)]
struct AiCheckCategory {
    key: String,
    #[serde(default)]
    passed: bool,
    #[serde(default)]
    score: f64,
    #[serde(default)]
    reason: String,
}

/// Normalise text to a token set for duplicate detection.
pub(crate) fn normalize_tokens(text: &str) -> Vec<String> {
    text.to_lowercase()
        .chars()
        .map(|c| if c.is_alphanumeric() { c } else { ' ' })
        .collect::<String>()
        .split_whitespace()
        .map(|s| s.to_string())
        .collect()
}

/// Jaccard similarity between two token sets (0..1).
pub(crate) fn token_similarity(a: &[String], b: &[String]) -> f64 {
    use std::collections::HashSet;
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    let sa: HashSet<&String> = a.iter().collect();
    let sb: HashSet<&String> = b.iter().collect();
    let inter = sa.intersection(&sb).count() as f64;
    let union = sa.union(&sb).count() as f64;
    if union == 0.0 {
        0.0
    } else {
        inter / union
    }
}

/// Result of a duplicate scan against existing notes.
pub(crate) struct DupeCheck {
    pub is_duplicate: bool,
    pub best_similarity: f64,
}

impl Collection {
    /// Collect the primary text of existing notes under the tag prefix, for
    /// duplicate / leakage detection.
    pub(crate) fn mcat_existing_texts(&mut self, tag_prefix: &str) -> Result<Vec<String>> {
        let prefix = if tag_prefix.trim().is_empty() {
            "mcat".to_string()
        } else {
            tag_prefix.trim().to_string()
        };
        let child_prefix = format!("{prefix}::");
        let guard = self.search_cards_into_table("", SortMode::NoOrder)?;
        let cards = guard.col.storage.all_searched_cards()?;
        let mut seen_notes = std::collections::HashSet::new();
        let mut texts = Vec::new();
        for card in &cards {
            if !seen_notes.insert(card.note_id) {
                continue;
            }
            let note = guard
                .col
                .storage
                .get_note(card.note_id)?
                .or_not_found(card.note_id)?;
            if !note.tags.iter().any(|t| t.starts_with(&child_prefix)) {
                continue;
            }
            // Join the first two fields (question + answer) as the comparable
            // text, so paraphrase leakage is caught too.
            let joined = note
                .fields()
                .iter()
                .take(2)
                .cloned()
                .collect::<Vec<_>>()
                .join(" ");
            texts.push(joined);
        }
        Ok(texts)
    }

    pub(crate) fn mcat_duplicate_check(
        &mut self,
        question: &str,
        answer: &str,
        tag_prefix: &str,
        threshold: f64,
    ) -> Result<DupeCheck> {
        let candidate = normalize_tokens(&format!("{question} {answer}"));
        let existing = self.mcat_existing_texts(tag_prefix)?;
        let mut best = 0.0f64;
        for text in &existing {
            let sim = token_similarity(&candidate, &normalize_tokens(text));
            if sim > best {
                best = sim;
            }
        }
        Ok(DupeCheck {
            is_duplicate: best >= threshold,
            best_similarity: best,
        })
    }

    /// Run the full quality checker for one card. `source_ok` indicates the
    /// answer is grounded in the registered source excerpt.
    pub(crate) fn mcat_check_card(
        &mut self,
        req: pb::CheckCardRequest,
    ) -> Result<pb::CardQualityReport> {
        let client = self.mcat_ai_client();
        let cutoff = client.config().checker_cutoff;

        // --- Deterministic (non-AI) categories, always computed ---
        let dupe = self.mcat_duplicate_check(&req.question, &req.answer, &req.tag_prefix, 0.8)?;
        let taxonomy = Taxonomy::load();
        let properly_tagged = taxonomy_has_tag(&taxonomy, &req.tag_prefix, &req.topic_tag);
        let source_supported = source_supports_answer(&req.source_excerpt, &req.answer);

        let report = self.mcat_run_checker(
            &client,
            &req,
            &dupe,
            properly_tagged,
            source_supported,
            cutoff,
        );
        Ok(report)
    }

    /// Shared checker core so generation can reuse a single AI client.
    pub(crate) fn mcat_run_checker(
        &self,
        client: &dyn AiClient,
        req: &pb::CheckCardRequest,
        dupe: &DupeCheck,
        properly_tagged: bool,
        source_supported: bool,
        cutoff: f64,
    ) -> pb::CardQualityReport {
        let mut categories: Vec<pb::QualityCategory> = Vec::new();

        // AI-judged categories.
        let ai_result = check_ai_categories(client, req);
        let (ai_available, unavailable_reason) = match &ai_result {
            Ok(_) => (true, String::new()),
            Err(e) => (false, e.reason()),
        };
        match ai_result {
            Ok(ai_cats) => {
                for (key, label) in AI_CATEGORIES {
                    let found = ai_cats.categories.iter().find(|c| c.key == *key);
                    let (passed, score, reason) = match found {
                        Some(c) => (c.passed, c.score.clamp(0.0, 1.0), c.reason.clone()),
                        None => (false, 0.0, "model omitted this category".to_string()),
                    };
                    categories.push(pb::QualityCategory {
                        key: key.to_string(),
                        label: label.to_string(),
                        passed,
                        score,
                        reason,
                    });
                }
            }
            Err(_) => {
                // AI unavailable: mark the AI categories as failing so the card
                // is Blocked (never auto-trusted).
                for (key, label) in AI_CATEGORIES {
                    categories.push(pb::QualityCategory {
                        key: key.to_string(),
                        label: label.to_string(),
                        passed: false,
                        score: 0.0,
                        reason: "AI unavailable — cannot verify".to_string(),
                    });
                }
            }
        }

        // Deterministic categories.
        categories.push(pb::QualityCategory {
            key: "not_duplicate".into(),
            label: "Not a duplicate".into(),
            passed: !dupe.is_duplicate,
            score: (1.0 - dupe.best_similarity).clamp(0.0, 1.0),
            reason: if dupe.is_duplicate {
                format!(
                    "{:.0}% similar to an existing card",
                    dupe.best_similarity * 100.0
                )
            } else {
                "No close match to existing cards".into()
            },
        });
        categories.push(pb::QualityCategory {
            key: "properly_tagged".into(),
            label: "Properly tagged".into(),
            passed: properly_tagged,
            score: if properly_tagged { 1.0 } else { 0.0 },
            reason: if properly_tagged {
                "Tagged to a real taxonomy topic".into()
            } else {
                "Topic tag is not in the MCAT taxonomy".into()
            },
        });
        // When no source excerpt is supplied (e.g. checking a human-authored
        // card, or the general quality gate), source grounding is Not
        // Applicable and passes. AI generation always supplies an excerpt, so
        // grounding is genuinely enforced there.
        let source_required = !req.source_excerpt.trim().is_empty();
        let source_pass = source_supported || !source_required;
        categories.push(pb::QualityCategory {
            key: "source_supported".into(),
            label: "Supported by the source".into(),
            passed: source_pass,
            score: if source_pass { 1.0 } else { 0.0 },
            reason: if !source_required {
                "No source required for this check".into()
            } else if source_supported {
                "Answer overlaps the registered source excerpt".into()
            } else {
                "Answer not clearly supported by the source excerpt".into()
            },
        });

        let overall_score = if categories.is_empty() {
            0.0
        } else {
            categories.iter().map(|c| c.score).sum::<f64>() / categories.len() as f64
        };
        let hard_fail = categories
            .iter()
            .any(|c| HARD_FAIL.contains(&c.key.as_str()) && !c.passed);
        let passed = ai_available && overall_score >= cutoff && !hard_fail;
        let verdict = if passed { "NeedsReview" } else { "Blocked" };

        pb::CardQualityReport {
            ai_available,
            unavailable_reason,
            categories,
            overall_score,
            cutoff,
            passed,
            duplicate: dupe.is_duplicate,
            verdict: verdict.to_string(),
        }
    }
}

/// The topic tag must be a real `prefix::section::topic` under the taxonomy.
fn taxonomy_has_tag(taxonomy: &Taxonomy, tag_prefix: &str, topic_tag: &str) -> bool {
    let prefix = if tag_prefix.trim().is_empty() {
        taxonomy.tag_prefix.clone()
    } else {
        tag_prefix.trim().to_string()
    };
    for section in &taxonomy.sections {
        for topic in &section.topics {
            let full = format!("{}::{}::{}", prefix, section.key, topic.key);
            if full == topic_tag {
                return true;
            }
        }
    }
    false
}

/// The answer is "source supported" when a meaningful fraction of its
/// content words appear in the source excerpt. Empty excerpt => unsupported.
fn source_supports_answer(excerpt: &str, answer: &str) -> bool {
    if excerpt.trim().is_empty() {
        return false;
    }
    let answer_tokens = normalize_tokens(answer);
    let content: Vec<&String> = answer_tokens.iter().filter(|t| t.len() > 3).collect();
    if content.is_empty() {
        // Very short answers (numbers, single words): require exact appearance.
        let ex = excerpt.to_lowercase();
        return answer_tokens.iter().any(|t| ex.contains(t.as_str()));
    }
    let excerpt_tokens: std::collections::HashSet<String> =
        normalize_tokens(excerpt).into_iter().collect();
    let hits = content
        .iter()
        .filter(|t| excerpt_tokens.contains(**t))
        .count();
    hits as f64 / content.len() as f64 >= 0.4
}

fn check_ai_categories(
    client: &dyn AiClient,
    req: &pb::CheckCardRequest,
) -> AiResult<AiCheckResponse> {
    if !client.config().available() {
        return Err(AiError::Unconfigured {
            reason: client.config().status_reason(),
        });
    }
    let payload = serde_json::json!({
        "question": req.question,
        "answer": req.answer,
        "topic_tag": req.topic_tag,
        "has_source": !req.source_excerpt.trim().is_empty(),
        "source_excerpt": req.source_excerpt,
    });
    let system = format!(
        "You are a strict MCAT flashcard quality reviewer. Judge the card on each \
         category and respond with strict JSON of the form \
         {{\"categories\":[{{\"key\":\"factually_correct\",\"passed\":true,\"score\":0.0-1.0,\"reason\":\"...\"}}]}}. \
         Include exactly these keys: {}. Be skeptical: penalise wrong facts, vague \
         wording, and trivially easy cards.",
        AI_CATEGORIES.iter().map(|(k, _)| *k).collect::<Vec<_>>().join(", ")
    );
    let user = format!(
        "Question: {}\nAnswer: {}\nTopic: {}",
        req.question, req.answer, req.topic_tag
    );
    let chat = ChatRequest::new(AiTask::CheckCard, system, user).with_payload(payload);
    complete_json::<AiCheckResponse>(client, &chat)
}
