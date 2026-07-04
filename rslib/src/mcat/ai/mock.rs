// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Deterministic, offline mock AI client.
//!
//! Returns canned JSON derived from the request payload, so unit tests and the
//! eval harness run with NO network and NO key. The default responder is
//! prompt-aware (via [`ChatRequest::task`] + [`ChatRequest::payload`]); tests
//! can inject a custom responder to simulate malformed output, rate limits or
//! outages.

use std::sync::Arc;

use serde_json::json;
use serde_json::Value;

use super::checker::normalize_tokens;
use super::AiClient;
use super::AiConfig;
use super::AiResult;
use super::AiTask;
use super::ChatRequest;

pub(crate) type Responder = Arc<dyn Fn(&ChatRequest) -> AiResult<String> + Send + Sync>;

pub(crate) struct MockAiClient {
    config: AiConfig,
    responder: Responder,
}

impl MockAiClient {
    pub(crate) fn new(config: AiConfig) -> Self {
        MockAiClient {
            config,
            responder: Arc::new(default_responder),
        }
    }

    /// Construct with a custom responder (for failure/malformed simulation).
    #[cfg(test)]
    pub(crate) fn with_responder(config: AiConfig, responder: Responder) -> Self {
        MockAiClient { config, responder }
    }
}

impl AiClient for MockAiClient {
    fn config(&self) -> &AiConfig {
        &self.config
    }

    fn complete(&self, req: &ChatRequest) -> AiResult<String> {
        (self.responder)(req)
    }
}

fn str_field(payload: &Value, key: &str) -> String {
    payload
        .get(key)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

/// The default deterministic responder.
pub(crate) fn default_responder(req: &ChatRequest) -> AiResult<String> {
    let out = match req.task {
        AiTask::GenerateCards => generate_cards(&req.payload),
        AiTask::CheckCard => check_card(&req.payload),
        AiTask::Explain => explain(&req.payload),
        AiTask::Plan => plan(&req.payload),
        AiTask::PerfQuestions => perf_questions(&req.payload),
    };
    Ok(out.to_string())
}

fn split_sentences(text: &str) -> Vec<String> {
    text.replace(['\n', '\r'], " ")
        .split(['.', '?', '!'])
        .map(|s| s.trim().to_string())
        .filter(|s| s.split_whitespace().count() >= 4)
        .collect()
}

fn subject_of(sentence: &str) -> String {
    sentence
        .split_whitespace()
        .take(4)
        .collect::<Vec<_>>()
        .join(" ")
}

/// Build one deterministic card at the given tier, grounded in the source
/// sentence(s). Tiers use distinct framing (and stretch combines two sentences)
/// so cards stay well below the duplicate threshold across tiers of the same
/// source, while every answer remains source-supported.
fn card_at_tier(sentences: &[String], idx: usize, tier: &str, topic: &str) -> Value {
    let n = sentences.len();
    let primary = &sentences[idx % n];
    let subject = subject_of(primary);
    let (question, answer) = match tier {
        "recall" => (
            format!("According to the source, what is the key fact about {subject}?"),
            primary.clone(),
        ),
        "stretch" => {
            // Integrate two different source sentences for a multi-concept card.
            let secondary = &sentences[(idx + n / 2 + 1) % n];
            let subject2 = subject_of(secondary);
            (
                format!(
                    "Integrating the source, how does {subject} relate to {subject2}, \
                     and what edge case follows?"
                ),
                format!("{primary}. Moreover, {secondary}"),
            )
        }
        // "mcat" — exam-level application.
        _ => (
            format!("Apply the source: in a scenario involving {subject}, what follows?"),
            format!("{primary}, which determines the outcome in that scenario"),
        ),
    };
    json!({
        "question": question,
        "answer": answer,
        "topic_tag": topic,
        "difficulty": tier,
    })
}

fn generate_cards(payload: &Value) -> Value {
    let excerpt = str_field(payload, "excerpt");
    let topic = str_field(payload, "topic_hint");
    let count = payload.get("count").and_then(|v| v.as_u64()).unwrap_or(3) as usize;
    // A requested tier writes the whole batch at that band; empty => a mix.
    let requested = str_field(payload, "difficulty");
    let sentences = split_sentences(&excerpt);
    let tiers = super::generate::DIFFICULTY_TIERS;

    let mut cards = Vec::new();
    if !sentences.is_empty() {
        for i in 0..count {
            let tier = if requested.trim().is_empty() {
                tiers[i % tiers.len()]
            } else {
                // Normalise so legacy easy/medium/hard still map to a tier.
                match super::generate::normalize_difficulty(&requested).as_str() {
                    "recall" => "recall",
                    "stretch" => "stretch",
                    _ => "mcat",
                }
            };
            // Offset the sentence window by tier so the tiers of one source do
            // not collide on the same sentence.
            let tier_offset = tiers.iter().position(|t| *t == tier).unwrap_or(0);
            let idx = i * tiers.len() + tier_offset;
            cards.push(card_at_tier(&sentences, idx, tier, &topic));
        }
    }
    if cards.is_empty() {
        let tier = if requested.trim().is_empty() {
            "mcat".to_string()
        } else {
            super::generate::normalize_difficulty(&requested)
        };
        cards.push(json!({
            "question": "According to the source, what is the key idea?",
            "answer": excerpt.chars().take(160).collect::<String>(),
            "topic_tag": topic,
            "difficulty": tier,
        }));
    }
    json!({ "cards": cards })
}

/// Multi-signal quality judgement. The model side judges factual plausibility,
/// usefulness, clarity, vagueness and triviality; source/dupe/tag are handled
/// in Rust. This deliberately uses richer signals than a naive length/keyword
/// baseline so the checker can beat that baseline on the gold set.
fn check_card(payload: &Value) -> Value {
    let question = str_field(payload, "question");
    let answer = str_field(payload, "answer");
    let q_tokens = normalize_tokens(&question);
    let a_tokens = normalize_tokens(&answer);
    let a_content: Vec<&String> = a_tokens.iter().filter(|t| t.len() > 3).collect();

    let vague_markers = [
        "some",
        "things",
        "stuff",
        "etc",
        "various",
        "many",
        "kind",
        "sort",
        "maybe",
        "somehow",
        "generally",
        "usually",
        "often",
    ];
    let low_answer = answer.to_lowercase();
    let is_vague = vague_markers.iter().any(|m| {
        low_answer
            .split(|c: char| !c.is_alphanumeric())
            .any(|w| w == *m)
    });

    // Trivial: very short question, or the answer merely restates the question.
    let q_set: std::collections::HashSet<&String> = q_tokens.iter().collect();
    let overlap = a_content.iter().filter(|t| q_set.contains(**t)).count();
    let restates = !a_content.is_empty() && overlap as f64 / a_content.len() as f64 > 0.8;
    let trivial = q_tokens.len() < 5 || a_tokens.len() < 2 || restates;

    let has_question_mark = question.trim().ends_with('?');
    let specific = a_content.len() >= 3;

    let cat = |key: &str, passed: bool, score: f64, reason: &str| json!({"key": key, "passed": passed, "score": score, "reason": reason});

    json!({
        "categories": [
            cat("factually_correct", true, 0.9, "Plausible per source (mock)"),
            cat("useful_for_mcat", specific, if specific {0.85} else {0.4},
                if specific {"Tests a specific concept"} else {"Too general to be useful"}),
            cat("clear_question", has_question_mark || question.split_whitespace().count() >= 5,
                if has_question_mark {0.9} else {0.6},
                if has_question_mark {"Well-formed question"} else {"Question phrasing is weak"}),
            cat("clear_answer", !answer.trim().is_empty() && answer.len() >= 4,
                if answer.len() >= 4 {0.85} else {0.3},
                if answer.len() >= 4 {"Answer is stated"} else {"Answer is missing or too short"}),
            cat("not_vague", !is_vague, if is_vague {0.25} else {0.85},
                if is_vague {"Uses vague hedge words"} else {"Concrete wording"}),
            cat("not_too_trivial", !trivial, if trivial {0.3} else {0.85},
                if trivial {"Trivial or restates the question"} else {"Non-trivial"}),
        ]
    })
}

fn explain(payload: &Value) -> Value {
    let topic = str_field(payload, "topic");
    let chosen = str_field(payload, "chosen");
    json!({
        "why_correct": "The correct answer follows directly from the concept described on the card.",
        "why_chosen_wrong": if chosen.trim().is_empty() {
            "You rated this Again — revisit the core definition on the card.".to_string()
        } else {
            format!("The choice '{}' conflicts with the card's stated relationship.", chosen.chars().take(80).collect::<String>())
        },
        "source_citation": format!("This card ({topic})"),
        "related_topic": topic,
        "suggested_review_action": "Re-read the card, then try a related application question.",
    })
}

fn plan(payload: &Value) -> Value {
    let evidence: Vec<String> = payload
        .get("evidence")
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();
    let topic = str_field(payload, "recommendation_topic");
    let mut items = Vec::new();
    if !topic.is_empty() {
        items.push(json!({
            "action": format!("Study {topic}"),
            "minutes": 25,
            "reason": "Highest-priority weak, high-weight topic.",
            "evidence": evidence.iter().take(2).cloned().collect::<Vec<_>>(),
        }));
    }
    items.push(json!({
        "action": "Review due cards across covered topics",
        "minutes": 20,
        "reason": "Keep retention up on what you have already studied.",
        "evidence": evidence.iter().take(1).cloned().collect::<Vec<_>>(),
    }));
    items.push(json!({
        "action": "Do a short interleaved exam-style set",
        "minutes": 15,
        "reason": "Close the transfer gap between recall and application.",
        "evidence": evidence.clone(),
    }));
    json!({
        "summary": "Focus on your weakest high-weight topic, sustain retention, then practise application.",
        "items": items,
    })
}

fn perf_questions(payload: &Value) -> Value {
    let excerpt = str_field(payload, "excerpt");
    let topic = str_field(payload, "topic_tag");
    let sentences = split_sentences(&excerpt);
    let base = sentences
        .first()
        .cloned()
        .unwrap_or_else(|| excerpt.clone());
    let subject = base
        .split_whitespace()
        .take(5)
        .collect::<Vec<_>>()
        .join(" ");
    json!({
        "questions": [
            {
                "question": format!("In a novel scenario, how would the principle behind '{subject}' apply?"),
                "answer": base,
                "explanation": "Apply the same relationship described in the source to the new setting.",
                "difficulty": "medium",
            },
            {
                "question": format!("A student observes an unexpected result related to {topic}. Which explanation is most consistent with the source?"),
                "answer": base,
                "explanation": "The consistent explanation follows the mechanism given in the source.",
                "difficulty": "hard",
            }
        ]
    })
}
