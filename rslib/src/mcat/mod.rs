// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! MCAT Anki Mastery: per-topic mastery aggregation.
//!
//! This module powers the study dashboard's coverage/memory metrics. Topics are
//! identified by note tags namespaced under a prefix (default `mcat`), e.g.
//! `mcat::biobiochem::metabolism`. All statistics are derived from native
//! collection data (cards, tags, FSRS memory state, revlog), so the numbers are
//! correct on any device that has synced the collection and are shared
//! identically by the desktop and mobile apps. This is intentionally computed
//! in the Rust engine rather than Python so it can aggregate large review
//! histories quickly and run unchanged on mobile through the FFI bridge.

mod ai;
mod gamification;
mod interleaving;
mod recommender;
mod scores;
mod service;
mod snapshot;
mod taxonomy;

#[cfg(test)]
mod feature_tests;

use std::collections::HashMap;
use std::collections::HashSet;

use fsrs::FSRS;
use fsrs::FSRS5_DEFAULT_DECAY;

use crate::prelude::*;
use crate::search::SortMode;

/// Default target answer time (seconds) used to classify a review as
/// "overtime" when the request does not specify one. MCAT pacing is central to
/// the product, so timing is a first-class input even in the MVP.
const DEFAULT_TARGET_SECONDS: f64 = 30.0;

/// A card counts as "mastered" for a topic once its current FSRS recall
/// probability is at or above this threshold.
const MASTERY_RETRIEVABILITY_THRESHOLD: f32 = 0.9;

#[derive(Default)]
struct RevlogAgg {
    time_sum_secs: f64,
    count: u32,
    overtime: u32,
    last_reviewed_at: i64,
}

#[derive(Default)]
struct TopicAccumulator {
    topic_name: String,
    section: String,
    cards_total: u32,
    cards_seen: u32,
    cards_mastered: u32,
    recall_sum: f64,
    recall_count: u32,
    response_time_sum_secs: f64,
    response_count: u32,
    overtime_count: u32,
    last_reviewed_at: i64,
}

impl Collection {
    /// Aggregate per-topic mastery statistics across MCAT-tagged cards.
    ///
    /// A card is counted toward every MCAT topic tag it carries. Tags equal to
    /// the bare prefix (with no `::subtopic`) are ignored.
    pub fn topic_mastery(
        &mut self,
        req: anki_proto::mcat::TopicMasteryRequest,
    ) -> Result<anki_proto::mcat::TopicMasteryList> {
        let prefix = if req.tag_prefix.trim().is_empty() {
            "mcat".to_string()
        } else {
            req.tag_prefix.trim().to_string()
        };
        let child_prefix = format!("{prefix}::");
        let target_secs = if req.default_target_seconds > 0.0 {
            req.default_target_seconds
        } else {
            DEFAULT_TARGET_SECONDS
        };

        let guard = self.search_cards_into_table(req.search.as_str(), SortMode::NoOrder)?;
        let cards = guard.col.storage.all_searched_cards()?;
        let revlog = guard.col.storage.get_revlog_entries_for_searched_cards()?;
        let timing = guard.col.timing_today()?;

        // Aggregate revlog per card: time taken, overtime count, last review.
        let mut per_card: HashMap<CardId, RevlogAgg> = HashMap::new();
        for entry in &revlog {
            if !entry.has_rating() {
                continue;
            }
            let agg = per_card.entry(entry.cid).or_default();
            let secs = entry.taken_millis as f64 / 1000.0;
            agg.time_sum_secs += secs;
            agg.count += 1;
            if secs > target_secs {
                agg.overtime += 1;
            }
            let reviewed_at = entry.id.as_secs().0;
            if reviewed_at > agg.last_reviewed_at {
                agg.last_reviewed_at = reviewed_at;
            }
        }

        // Retrievability needs no trained params.
        let fsrs = FSRS::new(None).unwrap();
        let mut topics: HashMap<String, TopicAccumulator> = HashMap::new();
        // Distinct-card rollups (a card may belong to several topics).
        let mut distinct_total: HashSet<CardId> = HashSet::new();
        let mut distinct_seen: HashSet<CardId> = HashSet::new();

        for card in &cards {
            let note = guard
                .col
                .storage
                .get_note(card.note_id)?
                .or_not_found(card.note_id)?;
            let topic_tags: Vec<&String> = note
                .tags
                .iter()
                .filter(|t| t.starts_with(&child_prefix) && t.len() > child_prefix.len())
                .collect();
            if topic_tags.is_empty() {
                continue;
            }

            let seen = card.reps > 0;
            distinct_total.insert(card.id);
            if seen {
                distinct_seen.insert(card.id);
            }

            // Current recall probability, if the card has FSRS memory state.
            let recall = card.memory_state.map(|state| {
                let elapsed = card.seconds_since_last_review(&timing).unwrap_or_default();
                fsrs.current_retrievability_seconds(
                    state.into(),
                    elapsed,
                    card.decay.unwrap_or(FSRS5_DEFAULT_DECAY),
                )
            });

            for tag in topic_tags {
                let remainder = &tag[child_prefix.len()..];
                let section = remainder.split("::").next().unwrap_or("").to_string();
                let topic_name = remainder
                    .rsplit("::")
                    .next()
                    .unwrap_or(remainder)
                    .to_string();
                let acc = topics.entry(tag.clone()).or_default();
                if acc.section.is_empty() {
                    acc.section = section;
                    acc.topic_name = topic_name;
                }
                acc.cards_total += 1;
                if seen {
                    acc.cards_seen += 1;
                }
                if let Some(r) = recall {
                    acc.recall_sum += r as f64;
                    acc.recall_count += 1;
                    if r >= MASTERY_RETRIEVABILITY_THRESHOLD {
                        acc.cards_mastered += 1;
                    }
                }
                if let Some(rev) = per_card.get(&card.id) {
                    acc.response_time_sum_secs += rev.time_sum_secs;
                    acc.response_count += rev.count;
                    acc.overtime_count += rev.overtime;
                    if rev.last_reviewed_at > acc.last_reviewed_at {
                        acc.last_reviewed_at = rev.last_reviewed_at;
                    }
                }
            }
        }

        // Emit sorted by topic key for deterministic output.
        let mut keys: Vec<&String> = topics.keys().collect();
        keys.sort();
        let mut out_topics = Vec::with_capacity(keys.len());
        for key in keys {
            let acc = &topics[key];
            let average_recall = if acc.recall_count > 0 {
                acc.recall_sum / acc.recall_count as f64
            } else {
                0.0
            };
            let average_response_time = if acc.response_count > 0 {
                acc.response_time_sum_secs / acc.response_count as f64
            } else {
                0.0
            };
            let overtime_rate = if acc.response_count > 0 {
                acc.overtime_count as f64 / acc.response_count as f64
            } else {
                0.0
            };
            let coverage_percent = if acc.cards_total > 0 {
                acc.cards_seen as f64 / acc.cards_total as f64 * 100.0
            } else {
                0.0
            };
            // Low recall means weak. With no memory data yet, treat the topic as
            // maximally weak so it surfaces for study rather than looking mastered.
            let weakness_score = if acc.recall_count > 0 {
                (1.0 - average_recall).clamp(0.0, 1.0)
            } else {
                1.0
            };
            out_topics.push(anki_proto::mcat::TopicMastery {
                topic_key: key.clone(),
                topic_name: acc.topic_name.clone(),
                section: acc.section.clone(),
                cards_total: acc.cards_total,
                cards_seen: acc.cards_seen,
                cards_mastered: acc.cards_mastered,
                average_recall_probability: average_recall,
                average_response_time_secs: average_response_time,
                overtime_rate,
                last_reviewed_at: acc.last_reviewed_at,
                weakness_score,
                coverage_percent,
            });
        }

        let cards_total = distinct_total.len() as u32;
        let cards_seen = distinct_seen.len() as u32;
        let overall_coverage_percent = if cards_total > 0 {
            cards_seen as f64 / cards_total as f64 * 100.0
        } else {
            0.0
        };

        Ok(anki_proto::mcat::TopicMasteryList {
            topics: out_topics,
            cards_total,
            cards_seen,
            overall_coverage_percent,
        })
    }
}

#[cfg(test)]
mod test {
    use anki_proto::mcat::TopicMasteryRequest;

    use crate::card::FsrsMemoryState;
    use crate::collection::Collection;
    use crate::prelude::*;

    fn req() -> TopicMasteryRequest {
        TopicMasteryRequest {
            search: String::new(),
            tag_prefix: String::new(),
            default_target_seconds: 0.0,
        }
    }

    /// Add a Basic note with the given front field and tags; returns the note.
    fn add_tagged(col: &mut Collection, front: &str, tags: &[&str]) -> Note {
        let nt = col.basic_notetype();
        let mut note = nt.new_note();
        note.set_field(0, front).unwrap();
        note.tags = tags.iter().map(|t| t.to_string()).collect();
        col.add_note(&mut note, DeckId(1)).unwrap();
        note
    }

    #[test]
    fn counts_parsing_and_ignored_tags() {
        let mut col = Collection::new();
        add_tagged(&mut col, "a", &["mcat::biobiochem::metabolism"]);
        add_tagged(&mut col, "b", &["mcat::biobiochem::metabolism"]);
        add_tagged(&mut col, "c", &["mcat::chemphys::electrochem"]);
        add_tagged(&mut col, "d", &["unrelated"]); // no mcat tag -> ignored
        add_tagged(&mut col, "e", &["mcat"]); // bare prefix -> ignored

        let res = col.topic_mastery(req()).unwrap();
        assert_eq!(res.topics.len(), 2);

        // Sorted by full tag key; biobiochem sorts before chemphys.
        let metab = &res.topics[0];
        assert_eq!(metab.topic_key, "mcat::biobiochem::metabolism");
        assert_eq!(metab.section, "biobiochem");
        assert_eq!(metab.topic_name, "metabolism");
        assert_eq!(metab.cards_total, 2);
        assert_eq!(metab.cards_seen, 0);
        assert_eq!(metab.coverage_percent, 0.0);

        let electro = &res.topics[1];
        assert_eq!(electro.section, "chemphys");
        assert_eq!(electro.cards_total, 1);

        // Distinct rollup counts only the 3 MCAT-tagged cards.
        assert_eq!(res.cards_total, 3);
        assert_eq!(res.cards_seen, 0);
        assert_eq!(res.overall_coverage_percent, 0.0);
    }

    #[test]
    fn coverage_after_review() {
        let mut col = Collection::new();
        add_tagged(&mut col, "a", &["mcat::chemphys::electrochem"]);
        add_tagged(&mut col, "b", &["mcat::chemphys::electrochem"]);
        col.answer_good();
        col.clear_study_queues();

        let res = col.topic_mastery(req()).unwrap();
        let t = &res.topics[0];
        assert_eq!(t.cards_total, 2);
        assert_eq!(t.cards_seen, 1);
        assert!((t.coverage_percent - 50.0).abs() < 1e-6);
        assert_eq!(res.cards_seen, 1);
    }

    #[test]
    fn timing_and_overtime() {
        let mut col = Collection::new();
        add_tagged(&mut col, "a", &["mcat::psychsoc::memory"]);
        col.answer_good();
        col.clear_study_queues();
        // Force the review's time-taken to 60s; default target is 30s.
        col.storage
            .db
            .execute_batch("UPDATE revlog SET time = 60000")
            .unwrap();

        let res = col.topic_mastery(req()).unwrap();
        let t = &res.topics[0];
        assert!((t.average_response_time_secs - 60.0).abs() < 1e-6);
        assert!((t.overtime_rate - 1.0).abs() < 1e-6);
        assert!(t.last_reviewed_at > 0);
    }

    #[test]
    fn recall_and_mastery_from_memory_state() {
        let mut col = Collection::new();
        let note = add_tagged(&mut col, "a", &["mcat::cars::inference"]);
        let cid = col.storage.all_cards_of_note(note.id).unwrap()[0].id;
        let mut card = col.storage.get_card(cid).unwrap().unwrap();
        card.memory_state = Some(FsrsMemoryState {
            stability: 200.0,
            difficulty: 5.0,
        });
        card.decay = Some(fsrs::FSRS5_DEFAULT_DECAY);
        card.last_review_time = Some(TimestampSecs::now());
        col.storage.update_card(&card).unwrap();

        let res = col.topic_mastery(req()).unwrap();
        let t = &res.topics[0];
        assert!(
            t.average_recall_probability > 0.9,
            "recall={}",
            t.average_recall_probability
        );
        assert_eq!(t.cards_mastered, 1);
        assert!(t.weakness_score < 0.1);
    }

    /// Read-only query must not interfere with undo, and the collection must
    /// stay valid after an undo across the query.
    #[test]
    fn query_is_safe_across_undo() {
        let mut col = Collection::new();
        add_tagged(&mut col, "a", &["mcat::chemphys::electrochem"]);
        col.answer_good();
        col.clear_study_queues();

        // Query before undo.
        let before = col.topic_mastery(req()).unwrap();
        assert_eq!(before.cards_seen, 1);

        // Undo the review; the card returns to unseen.
        col.undo().unwrap();
        col.clear_study_queues();

        let after = col.topic_mastery(req()).unwrap();
        assert_eq!(after.topics.len(), 1);
        assert_eq!(after.cards_seen, 0);

        // Collection integrity is intact.
        let problems = col.check_database().unwrap().to_i18n_strings(&col.tr);
        assert!(
            problems.is_empty(),
            "database problems after undo: {problems:?}"
        );
    }
}
