// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! The study feature under test: timed interleaving.
//!
//! Hypothesis (rubric §8): mixing related topics in one session (interleaving)
//! improves transfer to new mixed-topic questions at equal study time, versus
//! blocked practice (all of one topic, then the next). This generator produces
//! either ordering deterministically so the on/off toggle can be ablated.

use anki_proto::mcat as pb;

use crate::prelude::*;

impl Collection {
    pub(crate) fn mcat_interleaved_session(
        &mut self,
        req: pb::InterleavedSessionRequest,
    ) -> Result<pb::InterleavedSession> {
        let snap = self.mcat_snapshot(&req.tag_prefix)?;
        let max_cards = if req.max_cards == 0 {
            20
        } else {
            req.max_cards as usize
        };

        // Per-topic due queues (already deterministic within a topic).
        let mut queues: Vec<(String, Vec<CardId>)> = snap
            .topics
            .iter()
            .filter(|t| !t.due_card_ids.is_empty())
            .map(|t| (t.full_tag.clone(), t.due_card_ids.clone()))
            .collect();
        queues.sort_by(|a, b| a.0.cmp(&b.0));

        let mut card_ids: Vec<i64> = Vec::new();
        let mut topic_keys: Vec<String> = Vec::new();

        if req.interleave {
            // Round-robin across topics: A B C A B C ...
            let mut i = 0;
            let mut remaining = true;
            while remaining && card_ids.len() < max_cards {
                remaining = false;
                for (topic, queue) in queues.iter() {
                    if let Some(cid) = queue.get(i) {
                        card_ids.push(cid.0);
                        topic_keys.push(topic.clone());
                        remaining = true;
                        if card_ids.len() >= max_cards {
                            break;
                        }
                    }
                }
                i += 1;
            }
        } else {
            // Blocked: exhaust one topic before the next: A A A B B B ...
            'outer: for (topic, queue) in queues.iter() {
                for cid in queue {
                    card_ids.push(cid.0);
                    topic_keys.push(topic.clone());
                    if card_ids.len() >= max_cards {
                        break 'outer;
                    }
                }
            }
        }

        let log = format!(
            "session mode={} topics={} cards={}",
            if req.interleave {
                "interleaved"
            } else {
                "blocked"
            },
            queues.len(),
            card_ids.len()
        );

        Ok(pb::InterleavedSession {
            card_ids,
            topic_keys,
            interleaved: req.interleave,
            log,
        })
    }

    pub(crate) fn mcat_topic_targets(
        &mut self,
        req: pb::ExamReadinessRequest,
    ) -> Result<pb::TopicTargetList> {
        let snap = self.mcat_snapshot(&req.tag_prefix)?;
        let default_target = req.default_target_seconds;
        let targets = snap
            .topics
            .iter()
            .map(|t| pb::TopicTarget {
                topic_key: t.full_tag.clone(),
                topic_name: t.topic_name.clone(),
                section_key: t.section_key.clone(),
                section_name: t.section_name.clone(),
                target_seconds: if t.target_seconds > 0.0 {
                    t.target_seconds
                } else {
                    default_target
                },
                exam_weight: t.weight,
                fact_based: t.fact_based,
                in_deck: t.has_knowledge(),
            })
            .collect();
        Ok(pb::TopicTargetList {
            targets,
            tag_prefix: snap.taxonomy.tag_prefix.clone(),
        })
    }
}
