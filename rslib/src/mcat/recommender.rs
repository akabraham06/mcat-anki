// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Deterministic "single best next thing to study" recommender (no AI).
//!
//! Priority = exam weight x weakness x coverage-gap x due-ness. Fully
//! deterministic and explainable, so it can serve as the honest baseline the
//! rubric requires and be reproduced identically on any device.

use anki_proto::mcat as pb;

use crate::mcat::snapshot::Snapshot;
use crate::mcat::snapshot::TopicAgg;
use crate::prelude::*;

struct Scored {
    priority: f64,
    exam_weight: f64,
    weakness: f64,
    coverage_gap: f64,
    due_cards: u32,
    idx: usize,
}

fn score_topic(topic: &TopicAgg, max_weight: f64) -> Scored {
    let recall = topic.memory_recall().unwrap_or(0.0);
    let weakness = (1.0 - recall).clamp(0.0, 1.0);
    let due_cards = topic.due_card_ids.len() as u32;
    let coverage_gap = if topic.knowledge_cards > 0 {
        (due_cards as f64 / topic.knowledge_cards as f64).clamp(0.0, 1.0)
    } else {
        1.0
    };
    let weight_norm = if max_weight > 0.0 {
        topic.weight as f64 / max_weight
    } else {
        0.0
    };
    let due_factor = 1.0 + due_cards as f64;
    let priority = weight_norm * weakness * (0.5 + 0.5 * coverage_gap) * due_factor;
    Scored {
        priority,
        exam_weight: topic.weight as f64,
        weakness,
        coverage_gap,
        due_cards,
        idx: 0,
    }
}

impl Collection {
    pub(crate) fn recommendation_from_snapshot(&self, snap: &Snapshot) -> pb::StudyRecommendation {
        let max_topic_weight = snap
            .taxonomy
            .sections
            .iter()
            .flat_map(|s| s.topics.iter())
            .map(|t| t.weight)
            .max()
            .unwrap_or(1) as f64;

        let mut scored: Vec<Scored> = snap
            .topics
            .iter()
            .enumerate()
            .map(|(idx, topic)| {
                let mut s = score_topic(topic, max_topic_weight);
                s.idx = idx;
                s
            })
            .collect();

        // Deterministic ordering: priority desc, then exam weight desc, then
        // topic key asc.
        scored.sort_by(|a, b| {
            b.priority
                .partial_cmp(&a.priority)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then(
                    b.exam_weight
                        .partial_cmp(&a.exam_weight)
                        .unwrap_or(std::cmp::Ordering::Equal),
                )
                .then(
                    snap.topics[a.idx]
                        .full_tag
                        .cmp(&snap.topics[b.idx].full_tag),
                )
        });

        if scored.is_empty() {
            return pb::StudyRecommendation {
                available: false,
                ..Default::default()
            };
        }

        let best = &scored[0];
        let topic = &snap.topics[best.idx];
        let recall_pct = topic.memory_recall().map(|r| r * 100.0);
        let explanation = build_explanation(topic, best, recall_pct);

        let candidates = scored
            .iter()
            .take(5)
            .map(|s| {
                let t = &snap.topics[s.idx];
                pb::RecommendationCandidate {
                    topic_key: t.full_tag.clone(),
                    topic_name: t.topic_name.clone(),
                    priority_score: s.priority,
                    exam_weight: s.exam_weight,
                    weakness: s.weakness,
                    coverage_gap: s.coverage_gap,
                    due_cards: s.due_cards,
                }
            })
            .collect();

        pb::StudyRecommendation {
            available: true,
            topic_key: topic.full_tag.clone(),
            topic_name: topic.topic_name.clone(),
            section_key: topic.section_key.clone(),
            priority_score: best.priority,
            explanation,
            candidates,
        }
    }
}

fn build_explanation(topic: &TopicAgg, s: &Scored, recall_pct: Option<f64>) -> String {
    let mut parts = vec![format!(
        "{} ({}) is the best next topic",
        topic.topic_name, topic.section_name
    )];
    parts.push(format!("exam weight {}", s.exam_weight as i64));
    match recall_pct {
        Some(r) => parts.push(format!("recall {:.0}%", r)),
        None => parts.push("no memory data yet".to_string()),
    }
    if s.due_cards > 0 {
        parts.push(format!("{} card(s) due", s.due_cards));
    } else if topic.knowledge_cards == 0 {
        parts.push("not yet in your deck".to_string());
    }
    format!("{}.", parts.join(", "))
}
