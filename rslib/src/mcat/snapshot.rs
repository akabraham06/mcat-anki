// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! A single pass over the collection that produces every aggregate the MCAT
//! features need (scores, coverage, recommender, transfer gap, interleaving,
//! XP). Computed in the Rust engine so it is fast and identical across
//! desktop and mobile.

use std::collections::HashMap;

use fsrs::FSRS;
use fsrs::FSRS5_DEFAULT_DECAY;

use crate::card::CardQueue;
use crate::mcat::taxonomy::Taxonomy;
use crate::prelude::*;
use crate::search::SortMode;

/// Notetype name that marks a card as an exam-style performance question.
pub(crate) const PERF_NOTETYPE: &str = "MCATPerf";

const DAY_SECS: i64 = 86_400;

/// Per-topic aggregates, one entry per taxonomy topic (present or not).
#[derive(Debug, Clone)]
pub(crate) struct TopicAgg {
    pub section_key: String,
    pub section_name: String,
    pub topic_name: String,
    pub full_tag: String,
    pub weight: u32,
    pub target_seconds: f64,
    pub fact_based: bool,
    /// Knowledge (memory) cards tagged with this topic.
    pub knowledge_cards: u32,
    pub recall_sum: f64,
    pub recall_count: u32,
    /// Exam-style performance-question reviews.
    pub perf_reviews: u32,
    pub perf_correct: u32,
    /// Knowledge-card reviews (for transfer-gap evidence).
    pub knowledge_reviews: u32,
    pub due_card_ids: Vec<CardId>,
    pub last_reviewed_at: i64,
}

impl TopicAgg {
    pub(crate) fn has_knowledge(&self) -> bool {
        self.knowledge_cards > 0
    }

    /// Mean current recall probability on knowledge cards (0..1).
    pub(crate) fn memory_recall(&self) -> Option<f64> {
        (self.recall_count > 0).then(|| self.recall_sum / self.recall_count as f64)
    }

    /// Accuracy on exam-style questions (0..1).
    pub(crate) fn performance_accuracy(&self) -> Option<f64> {
        (self.perf_reviews > 0).then(|| self.perf_correct as f64 / self.perf_reviews as f64)
    }
}

pub(crate) struct Snapshot {
    pub taxonomy: Taxonomy,
    pub topics: Vec<TopicAgg>,
    pub graded_reviews: i64,
    pub reviews_today: i64,
    pub streak_days: i64,
    pub now_secs: i64,
}

impl Snapshot {
    pub(crate) fn topics_in_section<'a>(
        &'a self,
        section_key: &'a str,
    ) -> impl Iterator<Item = &'a TopicAgg> {
        self.topics
            .iter()
            .filter(move |t| t.section_key == section_key)
    }

    /// Weighted coverage over the whole exam (0..1): topic weight that has at
    /// least one knowledge card, divided by total topic weight.
    pub(crate) fn overall_coverage(&self) -> f64 {
        let total: u32 = self.topics.iter().map(|t| t.weight).sum();
        if total == 0 {
            return 0.0;
        }
        let covered: u32 = self
            .topics
            .iter()
            .filter(|t| t.has_knowledge())
            .map(|t| t.weight)
            .sum();
        covered as f64 / total as f64
    }

    pub(crate) fn section_coverage(&self, section_key: &str) -> f64 {
        let total: u32 = self.topics_in_section(section_key).map(|t| t.weight).sum();
        if total == 0 {
            return 0.0;
        }
        let covered: u32 = self
            .topics_in_section(section_key)
            .filter(|t| t.has_knowledge())
            .map(|t| t.weight)
            .sum();
        covered as f64 / total as f64
    }
}

#[derive(Default)]
struct RevAgg {
    total: u32,
    correct: u32,
    last_reviewed_at: i64,
}

impl Collection {
    /// Build the MCAT snapshot for the given tag prefix (default `mcat`).
    pub(crate) fn mcat_snapshot(&mut self, tag_prefix: &str) -> Result<Snapshot> {
        let taxonomy = Taxonomy::load();
        let prefix = if tag_prefix.trim().is_empty() {
            taxonomy.tag_prefix.clone()
        } else {
            tag_prefix.trim().to_string()
        };
        let child_prefix = format!("{prefix}::");

        let mut topics: Vec<TopicAgg> = Vec::new();
        let mut index: HashMap<String, usize> = HashMap::new();
        for section in &taxonomy.sections {
            for topic in &section.topics {
                let full_tag = format!("{}::{}::{}", prefix, section.key, topic.key);
                index.insert(full_tag.clone(), topics.len());
                topics.push(TopicAgg {
                    section_key: section.key.clone(),
                    section_name: section.name.clone(),
                    topic_name: topic.name.clone(),
                    full_tag,
                    weight: topic.weight,
                    target_seconds: topic.target_seconds,
                    fact_based: topic.fact_based,
                    knowledge_cards: 0,
                    recall_sum: 0.0,
                    recall_count: 0,
                    perf_reviews: 0,
                    perf_correct: 0,
                    knowledge_reviews: 0,
                    due_card_ids: Vec::new(),
                    last_reviewed_at: 0,
                });
            }
        }

        let guard = self.search_cards_into_table("", SortMode::NoOrder)?;
        let cards = guard.col.storage.all_searched_cards()?;
        let revlog = guard.col.storage.get_revlog_entries_for_searched_cards()?;
        let timing = guard.col.timing_today()?;
        let now_secs = timing.now.0;
        let today_start = timing.next_day_at.0 - DAY_SECS;

        // Per-card review aggregates + global streak/today counters.
        let mut per_card: HashMap<CardId, RevAgg> = HashMap::new();
        let mut reviews_today: i64 = 0;
        let mut review_day_buckets: std::collections::HashSet<i64> =
            std::collections::HashSet::new();
        for entry in &revlog {
            if !entry.has_rating() {
                continue;
            }
            let reviewed_at = entry.id.as_secs().0;
            let agg = per_card.entry(entry.cid).or_default();
            agg.total += 1;
            if entry.button_chosen >= 3 {
                agg.correct += 1;
            }
            if reviewed_at > agg.last_reviewed_at {
                agg.last_reviewed_at = reviewed_at;
            }
            if reviewed_at >= today_start {
                reviews_today += 1;
            }
            // Day bucket: 0 = today, 1 = yesterday, ...
            let bucket = (timing.next_day_at.0 - reviewed_at) / DAY_SECS;
            if bucket >= 0 {
                review_day_buckets.insert(bucket);
            }
        }

        // Consecutive-day streak ending today.
        let mut streak_days: i64 = 0;
        while review_day_buckets.contains(&streak_days) {
            streak_days += 1;
        }

        let fsrs = FSRS::new(None).unwrap();
        let mut notetype_is_perf: HashMap<NotetypeId, bool> = HashMap::new();
        let mut graded_reviews: i64 = 0;

        for card in &cards {
            let note = guard
                .col
                .storage
                .get_note(card.note_id)?
                .or_not_found(card.note_id)?;
            let topic_indices: Vec<usize> = note
                .tags
                .iter()
                .filter(|t| t.starts_with(&child_prefix))
                .filter_map(|t| index.get(t.as_str()).copied())
                .collect();
            if topic_indices.is_empty() {
                continue;
            }

            let is_perf = *notetype_is_perf.entry(note.notetype_id).or_insert_with(|| {
                guard
                    .col
                    .storage
                    .get_notetype(note.notetype_id)
                    .ok()
                    .flatten()
                    .map(|nt| nt.name == PERF_NOTETYPE)
                    .unwrap_or(false)
            });

            let recall = card.memory_state.map(|state| {
                let elapsed = card.seconds_since_last_review(&timing).unwrap_or_default();
                fsrs.current_retrievability_seconds(
                    state.into(),
                    elapsed,
                    card.decay.unwrap_or(FSRS5_DEFAULT_DECAY),
                ) as f64
            });

            let is_due = match card.queue {
                CardQueue::New | CardQueue::Learn | CardQueue::DayLearn => true,
                CardQueue::Review => card.due <= timing.days_elapsed as i32,
                _ => false,
            };

            let rev = per_card.get(&card.id);
            if let Some(rev) = rev {
                graded_reviews += rev.total as i64;
            }

            for &ti in &topic_indices {
                let agg = &mut topics[ti];
                if is_perf {
                    if let Some(rev) = rev {
                        agg.perf_reviews += rev.total;
                        agg.perf_correct += rev.correct;
                    }
                } else {
                    agg.knowledge_cards += 1;
                    if let Some(r) = recall {
                        agg.recall_sum += r;
                        agg.recall_count += 1;
                    }
                    if let Some(rev) = rev {
                        agg.knowledge_reviews += rev.total;
                    }
                }
                if is_due {
                    agg.due_card_ids.push(card.id);
                }
                if let Some(rev) = rev {
                    if rev.last_reviewed_at > agg.last_reviewed_at {
                        agg.last_reviewed_at = rev.last_reviewed_at;
                    }
                }
            }
        }

        Ok(Snapshot {
            taxonomy,
            topics,
            graded_reviews,
            reviews_today,
            streak_days,
            now_secs,
        })
    }
}
