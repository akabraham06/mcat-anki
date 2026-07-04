// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! 9.8 AI-assisted performance-question generation.
//!
//! From an existing card, generate 2 paraphrased *application* questions, each
//! with an explanation, difficulty, source trace and linked topic. Every
//! candidate is quality-checked (9.4) and passed through a leakage /
//! near-duplicate check against existing training/test questions. Accepted
//! items become MCATPerf-style notes labelled AI-generated (an `ai-generated`
//! tag plus the `mcat::exam` performance marker), so they feed the interleaving
//! / performance bank while staying distinguishable from human-authored items.

use anki_proto::mcat as pb;
use serde::Deserialize;

use super::complete_json;
use super::generate::source_citation_line;
use super::generate::source_tag;
use super::generate::AI_LABEL_TAG;
use super::prompt::fence_source;
use super::prompt::DATA_ONLY_INSTRUCTION;
use super::AiError;
use super::AiResult;
use super::AiTask;
use super::ChatRequest;
use crate::prelude::*;

/// Performance marker tag understood by the scoring engine (see snapshot.rs).
const PERF_TAG: &str = "mcat::exam";
/// Leakage threshold: a candidate too similar to an existing question is a
/// train/test leak and is Blocked.
const LEAKAGE_THRESHOLD: f64 = 0.7;

#[derive(Deserialize)]
struct AiPerfResponse {
    questions: Vec<AiPerfQuestion>,
}

#[derive(Deserialize)]
struct AiPerfQuestion {
    #[serde(default)]
    question: String,
    #[serde(default)]
    answer: String,
    #[serde(default)]
    explanation: String,
    #[serde(default)]
    difficulty: String,
}

impl Collection {
    pub(crate) fn mcat_generate_perf_questions(
        &mut self,
        req: pb::GeneratePerfQuestionsRequest,
    ) -> Result<pb::GeneratedPerfQuestionList> {
        let unavailable = |card_id: i64, reason: String| pb::GeneratedPerfQuestionList {
            ai_available: false,
            unavailable_reason: reason,
            card_id,
            ..Default::default()
        };

        let card = match self.storage.get_card(CardId(req.card_id))? {
            Some(c) => c,
            None => return Ok(unavailable(req.card_id, "Card not found.".to_string())),
        };
        let note = match self.storage.get_note(card.note_id)? {
            Some(n) => n,
            None => return Ok(unavailable(req.card_id, "Note not found.".to_string())),
        };

        let prefix = if req.tag_prefix.trim().is_empty() {
            "mcat".to_string()
        } else {
            req.tag_prefix.trim().to_string()
        };
        let child_prefix = format!("{prefix}::");
        let topic_tag = note
            .tags
            .iter()
            .find(|t| t.starts_with(&child_prefix) && *t != PERF_TAG)
            .cloned()
            .unwrap_or_default();

        // Ground either in a registered source, or in the card's own content.
        let (source_id, source_name, excerpt) = match self.mcat_find_source(&req.source_id) {
            Some(s) => (s.source_id, s.source_name, s.excerpt),
            None => (
                String::new(),
                "Origin card".to_string(),
                note.fields().join("\n"),
            ),
        };

        let client = self.mcat_ai_client();
        if !client.config().available() {
            return Ok(unavailable(req.card_id, client.config().status_reason()));
        }

        let generated = match generate_perf(&client, &source_name, &topic_tag, &excerpt) {
            Ok(g) => g,
            Err(e) => return Ok(unavailable(req.card_id, e.reason())),
        };

        let cutoff = client.config().checker_cutoff;
        let mut questions = Vec::new();
        for gq in generated.questions.into_iter().take(2) {
            if gq.question.trim().is_empty() {
                continue;
            }
            // Leakage / near-duplicate check against existing questions.
            let dupe = self.mcat_duplicate_check(
                &gq.question,
                &gq.answer,
                &req.tag_prefix,
                LEAKAGE_THRESHOLD,
            )?;
            let leakage = dupe.is_duplicate;

            let check_req = pb::CheckCardRequest {
                question: gq.question.clone(),
                answer: gq.answer.clone(),
                topic_tag: topic_tag.clone(),
                source_id: source_id.clone(),
                source_excerpt: excerpt.clone(),
                tag_prefix: req.tag_prefix.clone(),
            };
            let taxonomy = crate::mcat::taxonomy::Taxonomy::load();
            let tagged_ok = taxonomy.sections.iter().any(|s| {
                s.topics
                    .iter()
                    .any(|t| format!("{}::{}::{}", prefix, s.key, t.key) == topic_tag)
            });
            let report = self.mcat_run_checker(&client, &check_req, &dupe, tagged_ok, true, cutoff);

            let status = if leakage {
                pb::GeneratedCardStatus::Blocked
            } else if report.passed {
                pb::GeneratedCardStatus::NeedsReview
            } else {
                pb::GeneratedCardStatus::Blocked
            };

            questions.push(pb::GeneratedPerfQuestion {
                question: gq.question.trim().to_string(),
                answer: gq.answer.trim().to_string(),
                explanation: gq.explanation.trim().to_string(),
                difficulty: normalize_difficulty(&gq.difficulty),
                topic_tag: topic_tag.clone(),
                source_id: source_id.clone(),
                source_name: source_name.clone(),
                source_excerpt: excerpt.clone(),
                status: status as i32,
                quality: Some(report),
                leakage,
                leakage_reason: if leakage {
                    format!(
                        "{:.0}% similar to an existing question (train/test leak)",
                        dupe.best_similarity * 100.0
                    )
                } else {
                    String::new()
                },
            });
        }

        Ok(pb::GeneratedPerfQuestionList {
            ai_available: true,
            unavailable_reason: String::new(),
            card_id: req.card_id,
            topic_tag,
            source_id,
            questions,
        })
    }

    pub(crate) fn mcat_accept_perf_questions(
        &mut self,
        req: pb::AcceptPerfQuestionsRequest,
    ) -> Result<pb::AcceptCardsResponse> {
        let deck_name = if req.deck_name.trim().is_empty() {
            "MCAT::AI Generated".to_string()
        } else {
            req.deck_name.trim().to_string()
        };
        let did = self.get_or_create_normal_deck(&deck_name)?.id;
        let notetype = self.mcat_basic_notetype()?;

        let mut note_ids = Vec::new();
        let mut skipped = 0u32;
        for q in &req.questions {
            let status = pb::GeneratedCardStatus::try_from(q.status).unwrap_or_default();
            let blocked = matches!(
                status,
                pb::GeneratedCardStatus::Blocked | pb::GeneratedCardStatus::Duplicate
            );
            if blocked || q.leakage || q.question.trim().is_empty() {
                skipped += 1;
                continue;
            }
            let mut note = notetype.new_note();
            note.set_field(0, &q.question)?;
            let mut back = if q.explanation.trim().is_empty() {
                q.answer.clone()
            } else {
                format!("{}\n\n{}", q.answer, q.explanation)
            };
            // Keep the named source visible on the accepted performance item.
            let citation = source_citation_line(&q.source_name, "");
            if !citation.is_empty() {
                back = format!("{back}\n\n{citation}");
            }
            note.set_field(1, &back)?;
            // Label AI-generated + mark as performance evidence.
            let mut tags = vec![AI_LABEL_TAG.to_string(), PERF_TAG.to_string()];
            if !q.topic_tag.trim().is_empty() {
                tags.push(q.topic_tag.trim().to_string());
            }
            // Machine-readable source trace (resolves to the registered source).
            if let Some(tag) = source_tag(&q.source_id) {
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

fn normalize_difficulty(d: &str) -> String {
    match d.trim().to_lowercase().as_str() {
        "easy" | "e" => "easy".to_string(),
        "hard" | "h" => "hard".to_string(),
        _ => "medium".to_string(),
    }
}

fn generate_perf(
    client: &dyn super::AiClient,
    source_name: &str,
    topic_tag: &str,
    excerpt: &str,
) -> AiResult<AiPerfResponse> {
    if !client.config().available() {
        return Err(AiError::Unconfigured {
            reason: client.config().status_reason(),
        });
    }
    let fenced = fence_source(source_name, topic_tag, excerpt);
    let system = format!(
        "You are an MCAT item writer. Write exactly 2 NEW application-style questions that \
         test the same concept in a novel scenario (not copies of the source). \
         {DATA_ONLY_INSTRUCTION} Respond with strict JSON \
         {{\"questions\":[{{\"question\":\"...\",\"answer\":\"...\",\"explanation\":\"...\",\"difficulty\":\"easy|medium|hard\"}}]}}."
    );
    let user = format!("Topic: {topic_tag}\n\n{fenced}");
    let payload = serde_json::json!({
        "topic_tag": topic_tag,
        "excerpt": excerpt,
        "source_name": source_name,
    });
    let chat = ChatRequest::new(AiTask::PerfQuestions, system, user).with_payload(payload);
    complete_json::<AiPerfResponse>(client, &chat)
}
