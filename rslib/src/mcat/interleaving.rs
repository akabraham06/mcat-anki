// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! The study feature under test: timed interleaving.
//!
//! Hypothesis (rubric §8): mixing related topics in one session (interleaving)
//! improves transfer to new mixed-topic questions at equal study time, versus
//! blocked practice (all of one topic, then the next). This generator produces
//! either ordering deterministically so the on/off toggle can be ablated.

use std::collections::BTreeMap;

use anki_proto::mcat as pb;

use crate::prelude::*;

/// A single topic's due cards, tagged with the section it belongs to.
struct TopicQueue {
    section_key: String,
    full_tag: String,
    cards: Vec<CardId>,
}

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

        // Per-topic due queues, carrying the owning section. Sorting by full tag
        // keeps a topic's cards contiguous and groups a section's topics
        // together, which is exactly the blocked ordering.
        let mut queues: Vec<TopicQueue> = snap
            .topics
            .iter()
            .filter(|t| !t.due_card_ids.is_empty())
            .map(|t| TopicQueue {
                section_key: t.section_key.clone(),
                full_tag: t.full_tag.clone(),
                cards: t.due_card_ids.clone(),
            })
            .collect();
        queues.sort_by(|a, b| a.full_tag.cmp(&b.full_tag));

        let mut card_ids: Vec<i64> = Vec::new();
        let mut topic_keys: Vec<String> = Vec::new();

        if req.interleave {
            // True cross-section interleaving. Group topics by section (sections
            // ordered deterministically by key, topics kept tag-sorted), build a
            // per-section stream that round-robins that section's topics, then
            // round-robin ACROSS sections so consecutive cards come from
            // different sections wherever possible. This alternates sections even
            // when each topic only has a single due card, so the result is
            // clearly distinct from the section-grouped blocked ordering.
            let mut sections: BTreeMap<&str, Vec<&TopicQueue>> = BTreeMap::new();
            for q in &queues {
                sections.entry(&q.section_key).or_default().push(q);
            }

            let section_streams: Vec<Vec<(&str, i64)>> = sections
                .values()
                .map(|topics| {
                    let mut stream: Vec<(&str, i64)> = Vec::new();
                    let mut i = 0;
                    let mut remaining = true;
                    while remaining {
                        remaining = false;
                        for tq in topics {
                            if let Some(cid) = tq.cards.get(i) {
                                stream.push((tq.full_tag.as_str(), cid.0));
                                remaining = true;
                            }
                        }
                        i += 1;
                    }
                    stream
                })
                .collect();

            let mut i = 0;
            let mut remaining = true;
            while remaining && card_ids.len() < max_cards {
                remaining = false;
                for stream in &section_streams {
                    if let Some((tag, cid)) = stream.get(i) {
                        card_ids.push(*cid);
                        topic_keys.push((*tag).to_string());
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
            // (and, because tags sort section-first, one section before the next).
            'outer: for q in queues.iter() {
                for cid in &q.cards {
                    card_ids.push(cid.0);
                    topic_keys.push(q.full_tag.clone());
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
