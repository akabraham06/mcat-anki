// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! The three separate scores (memory, performance, readiness), each reported
//! honestly with a range, coverage, confidence, reasons, and a written-down
//! give-up rule. Also the section breakdown, transfer gaps, and XP.

use anki_proto::mcat as pb;

use crate::mcat::snapshot::Snapshot;
use crate::prelude::*;

/// The written-down give-up rule (rubric: "refuse to give a score when it does
/// not have enough data").
pub(crate) const MIN_GRADED_REVIEWS: i64 = 100;
pub(crate) const MIN_COVERAGE: f64 = 0.5;

const XP_PER_REVIEW: i64 = 10;
const XP_PER_LEVEL: i64 = 500;

/// Deterministic point estimate + range on an exam scale.
///
/// `fraction` is the raw ability (0..1); `coverage` and `evidence` drive the
/// uncertainty band. Pure function so it can be unit-tested directly.
pub(crate) fn estimate(
    scale_min: f64,
    scale_max: f64,
    fraction: f64,
    coverage: f64,
    evidence: i64,
) -> (f64, f64, f64, String) {
    let fraction = fraction.clamp(0.0, 1.0);
    let coverage = coverage.clamp(0.0, 1.0);
    let range = scale_max - scale_min;
    let point = scale_min + fraction * range;
    let uncertainty =
        (0.5 * (1.0 - coverage) + 1.0 / ((evidence.max(0) as f64) + 1.0).sqrt()).clamp(0.03, 0.6);
    let margin = uncertainty * range;
    let low = (point - margin).max(scale_min);
    let high = (point + margin).min(scale_max);
    let confidence = if uncertainty < 0.12 {
        "high"
    } else if uncertainty < 0.30 {
        "medium"
    } else {
        "low"
    };
    (point, low, high, confidence.to_string())
}

struct Totals {
    recall_sum: f64,
    recall_count: i64,
    knowledge_reviews: i64,
    perf_reviews: i64,
    perf_correct: i64,
    last_updated: i64,
}

fn totals(snap: &Snapshot) -> Totals {
    let mut t = Totals {
        recall_sum: 0.0,
        recall_count: 0,
        knowledge_reviews: 0,
        perf_reviews: 0,
        perf_correct: 0,
        last_updated: 0,
    };
    for topic in &snap.topics {
        t.recall_sum += topic.recall_sum;
        t.recall_count += topic.recall_count as i64;
        t.knowledge_reviews += topic.knowledge_reviews as i64;
        t.perf_reviews += topic.perf_reviews as i64;
        t.perf_correct += topic.perf_correct as i64;
        t.last_updated = t.last_updated.max(topic.last_reviewed_at);
    }
    t
}

impl Collection {
    pub(crate) fn mcat_exam_readiness(
        &mut self,
        req: pb::ExamReadinessRequest,
    ) -> Result<pb::ExamReadiness> {
        let snap = self.mcat_snapshot(&req.tag_prefix)?;
        let scale = snap.taxonomy.score_scale;
        let t = totals(&snap);
        let coverage = snap.overall_coverage();
        let last_updated = if t.last_updated > 0 {
            t.last_updated
        } else {
            snap.now_secs
        };

        // --- Memory ---
        let memory_fraction = if t.recall_count > 0 {
            t.recall_sum / t.recall_count as f64
        } else {
            0.0
        };
        let memory = if t.recall_count > 0 {
            let (point, low, high, confidence) = estimate(
                scale.total_min,
                scale.total_max,
                memory_fraction,
                coverage,
                t.knowledge_reviews,
            );
            pb::ScoreEstimate {
                label: "Memory".into(),
                available: true,
                abstain_reason: String::new(),
                point,
                low,
                high,
                scale_min: scale.total_min,
                scale_max: scale.total_max,
                confidence,
                coverage_percent: coverage * 100.0,
                last_updated,
                reasons: vec![
                    format!(
                        "Mean recall {:.0}% across studied cards",
                        memory_fraction * 100.0
                    ),
                    format!("{:.0}% of exam topics covered", coverage * 100.0),
                    format!("{} knowledge reviews", t.knowledge_reviews),
                ],
                evidence_count: t.knowledge_reviews,
            }
        } else {
            abstain(
                "Memory",
                scale.total_min,
                scale.total_max,
                coverage,
                "No memory data yet — study some knowledge cards first.",
            )
        };

        // --- Performance ---
        let performance_fraction = if t.perf_reviews > 0 {
            t.perf_correct as f64 / t.perf_reviews as f64
        } else {
            0.0
        };
        let perf_coverage = self.perf_coverage(&snap);
        let performance = if t.perf_reviews > 0 {
            let (point, low, high, confidence) = estimate(
                scale.total_min,
                scale.total_max,
                performance_fraction,
                perf_coverage,
                t.perf_reviews,
            );
            pb::ScoreEstimate {
                label: "Performance".into(),
                available: true,
                abstain_reason: String::new(),
                point,
                low,
                high,
                scale_min: scale.total_min,
                scale_max: scale.total_max,
                confidence,
                coverage_percent: perf_coverage * 100.0,
                last_updated,
                reasons: vec![
                    format!(
                        "{:.0}% correct on exam-style questions",
                        performance_fraction * 100.0
                    ),
                    format!("{} performance reviews", t.perf_reviews),
                ],
                evidence_count: t.perf_reviews,
            }
        } else {
            abstain(
                "Performance",
                scale.total_min,
                scale.total_max,
                perf_coverage,
                "No exam-style questions answered yet.",
            )
        };

        // --- Readiness (gated by the give-up rule) ---
        let give_up_ok = snap.graded_reviews >= MIN_GRADED_REVIEWS && coverage >= MIN_COVERAGE;
        let readiness = if give_up_ok && memory.available && performance.available {
            // Performance weighted higher: it is closer to the real exam.
            let readiness_fraction = 0.4 * memory_fraction + 0.6 * performance_fraction;
            let (point, low, high, confidence) = estimate(
                scale.total_min,
                scale.total_max,
                readiness_fraction,
                coverage.min(perf_coverage),
                snap.graded_reviews,
            );
            pb::ScoreEstimate {
                label: "Readiness".into(),
                available: true,
                abstain_reason: String::new(),
                point,
                low,
                high,
                scale_min: scale.total_min,
                scale_max: scale.total_max,
                confidence,
                coverage_percent: coverage * 100.0,
                last_updated,
                reasons: vec![
                    format!(
                        "Blends memory ({:.0}%) and performance ({:.0}%)",
                        memory_fraction * 100.0,
                        performance_fraction * 100.0
                    ),
                    format!(
                        "{} graded reviews, {:.0}% coverage",
                        snap.graded_reviews,
                        coverage * 100.0
                    ),
                ],
                evidence_count: snap.graded_reviews,
            }
        } else {
            let reason = if !memory.available {
                "No memory data yet.".to_string()
            } else if !performance.available {
                "No exam-style questions answered yet.".to_string()
            } else if snap.graded_reviews < MIN_GRADED_REVIEWS {
                format!(
                    "Only {} of {} required graded reviews.",
                    snap.graded_reviews, MIN_GRADED_REVIEWS
                )
            } else {
                format!(
                    "Only {:.0}% of {:.0}% required topic coverage.",
                    coverage * 100.0,
                    MIN_COVERAGE * 100.0
                )
            };
            abstain(
                "Readiness",
                scale.total_min,
                scale.total_max,
                coverage,
                &reason,
            )
        };

        // --- Section breakdown (memory) ---
        let mut sections = Vec::new();
        for section in &snap.taxonomy.sections {
            let (mut recall_sum, mut recall_count, mut kreviews) = (0.0, 0i64, 0i64);
            for topic in snap.topics_in_section(&section.key) {
                recall_sum += topic.recall_sum;
                recall_count += topic.recall_count as i64;
                kreviews += topic.knowledge_reviews as i64;
            }
            let cov = snap.section_coverage(&section.key);
            if recall_count > 0 {
                let frac = recall_sum / recall_count as f64;
                let (point, low, high, _c) =
                    estimate(scale.section_min, scale.section_max, frac, cov, kreviews);
                sections.push(pb::SectionScore {
                    section_key: section.key.clone(),
                    section_name: section.name.clone(),
                    available: true,
                    point,
                    low,
                    high,
                    coverage_percent: cov * 100.0,
                    recall: frac,
                });
            } else {
                sections.push(pb::SectionScore {
                    section_key: section.key.clone(),
                    section_name: section.name.clone(),
                    available: false,
                    point: 0.0,
                    low: 0.0,
                    high: 0.0,
                    coverage_percent: cov * 100.0,
                    recall: 0.0,
                });
            }
        }

        let transfer_gaps = transfer_gaps(&snap);
        let xp = xp_summary(&snap);
        let recommendation = self.recommendation_from_snapshot(&snap);

        Ok(pb::ExamReadiness {
            exam: snap.taxonomy.exam.clone(),
            memory: Some(memory),
            performance: Some(performance),
            readiness: Some(readiness),
            sections,
            overall_coverage_percent: coverage * 100.0,
            graded_reviews: snap.graded_reviews,
            recommendation: Some(recommendation),
            transfer_gaps,
            xp: Some(xp),
            give_up_rule: Some(pb::GiveUpRule {
                min_graded_reviews: MIN_GRADED_REVIEWS,
                min_coverage_percent: MIN_COVERAGE * 100.0,
                description: format!(
                    "No readiness score until at least {} graded reviews and {:.0}% topic coverage.",
                    MIN_GRADED_REVIEWS,
                    MIN_COVERAGE * 100.0
                ),
            }),
        })
    }

    /// Coverage of exam-style questions across topics (weighted).
    fn perf_coverage(&self, snap: &Snapshot) -> f64 {
        let total: u32 = snap.topics.iter().map(|t| t.weight).sum();
        if total == 0 {
            return 0.0;
        }
        let covered: u32 = snap
            .topics
            .iter()
            .filter(|t| t.perf_reviews > 0)
            .map(|t| t.weight)
            .sum();
        covered as f64 / total as f64
    }
}

fn abstain(
    label: &str,
    scale_min: f64,
    scale_max: f64,
    coverage: f64,
    reason: &str,
) -> pb::ScoreEstimate {
    pb::ScoreEstimate {
        label: label.into(),
        available: false,
        abstain_reason: reason.into(),
        point: 0.0,
        low: 0.0,
        high: 0.0,
        scale_min,
        scale_max,
        confidence: "none".into(),
        coverage_percent: coverage * 100.0,
        last_updated: 0,
        reasons: vec![],
        evidence_count: 0,
    }
}

fn transfer_gaps(snap: &Snapshot) -> Vec<pb::TransferGap> {
    let mut gaps = Vec::new();
    for topic in &snap.topics {
        let memory_recall = topic.memory_recall();
        let performance_accuracy = topic.performance_accuracy();
        let available = memory_recall.is_some() && performance_accuracy.is_some();
        if !available {
            continue;
        }
        let m = memory_recall.unwrap();
        let p = performance_accuracy.unwrap();
        gaps.push(pb::TransferGap {
            topic_key: topic.full_tag.clone(),
            topic_name: topic.topic_name.clone(),
            available: true,
            memory_recall: m,
            performance_accuracy: p,
            gap: m - p,
            knowledge_reviews: topic.knowledge_reviews as i64,
            performance_reviews: topic.perf_reviews as i64,
        });
    }
    gaps
}

fn xp_summary(snap: &Snapshot) -> pb::XpSummary {
    let total_xp = snap.graded_reviews * XP_PER_REVIEW;
    let xp_today = snap.reviews_today * XP_PER_REVIEW;
    let level = total_xp / XP_PER_LEVEL + 1;
    let mut badges = Vec::new();
    if snap.graded_reviews >= 100 {
        badges.push("Century — 100 reviews".to_string());
    }
    if snap.streak_days >= 7 {
        badges.push("Week streak".to_string());
    }
    let covered_sections = snap
        .taxonomy
        .sections
        .iter()
        .filter(|s| snap.section_coverage(&s.key) > 0.0)
        .count();
    if covered_sections == snap.taxonomy.sections.len() && covered_sections > 0 {
        badges.push("Full breadth — all sections".to_string());
    }
    pb::XpSummary {
        total_xp,
        reviews_today: snap.reviews_today,
        xp_today,
        streak_days: snap.streak_days,
        level,
        badges,
    }
}
