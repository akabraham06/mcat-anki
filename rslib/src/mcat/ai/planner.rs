// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! 9.6 AI study planner.
//!
//! Produces an ordered plan of `{action, minutes}` items, each with a reason
//! and the app evidence behind it. Inputs are pulled ONLY from measured data
//! (coverage, mastery, performance, timing, due counts) so the AI cites app
//! evidence and cannot invent readiness. The deterministic recommender is the
//! always-available fallback when AI is off or unavailable.

use anki_proto::mcat as pb;
use serde::Deserialize;

use super::complete_json;
use super::AiTask;
use super::ChatRequest;
use crate::mcat::snapshot::Snapshot;
use crate::prelude::*;

#[derive(Deserialize)]
struct AiPlanResponse {
    #[serde(default)]
    summary: String,
    #[serde(default)]
    items: Vec<AiPlanItem>,
}

#[derive(Deserialize)]
struct AiPlanItem {
    #[serde(default)]
    action: String,
    #[serde(default)]
    minutes: i32,
    #[serde(default)]
    reason: String,
    #[serde(default)]
    evidence: Vec<String>,
}

impl Collection {
    pub(crate) fn mcat_ai_study_plan(
        &mut self,
        req: pb::ExamReadinessRequest,
    ) -> Result<pb::AiStudyPlan> {
        let snap = self.mcat_snapshot(&req.tag_prefix)?;
        let evidence = build_evidence(&snap);
        let fallback = self.recommendation_from_snapshot(&snap);
        let fallback_items = deterministic_items(&snap, &fallback);

        let client = self.mcat_ai_client();
        if !client.config().available() {
            return Ok(pb::AiStudyPlan {
                ai_available: false,
                unavailable_reason: client.config().status_reason(),
                items: fallback_items,
                summary: "Deterministic study plan (AI unavailable).".to_string(),
                used_fallback: true,
                evidence,
                fallback: Some(fallback),
            });
        }

        let system = "You are an MCAT study planner. You are given ONLY measured data \
             from the student's app. Produce a short ordered plan. You MUST base every \
             item on the supplied evidence and cite it in the item's evidence array. Do \
             NOT invent a readiness score or any numbers not present in the evidence. \
             Respond with strict JSON \
             {\"summary\":\"...\",\"items\":[{\"action\":\"...\",\"minutes\":20,\"reason\":\"...\",\"evidence\":[\"...\"]}]}."
            .to_string();
        let user = format!("Measured evidence:\n- {}", evidence.join("\n- "));
        let payload = serde_json::json!({
            "evidence": evidence,
            "recommendation_topic": fallback.topic_name,
            "recommendation_reason": fallback.explanation,
        });
        let chat = ChatRequest::new(AiTask::Plan, system, user).with_payload(payload);

        match complete_json::<AiPlanResponse>(&client, &chat) {
            Ok(plan) if !plan.items.is_empty() => {
                let items = plan
                    .items
                    .into_iter()
                    .map(|i| pb::AiStudyPlanItem {
                        action: i.action,
                        minutes: i.minutes.clamp(0, 240),
                        reason: i.reason,
                        // Ensure every item is grounded in app evidence.
                        evidence: if i.evidence.is_empty() {
                            evidence.clone()
                        } else {
                            i.evidence
                        },
                    })
                    .collect();
                Ok(pb::AiStudyPlan {
                    ai_available: true,
                    unavailable_reason: String::new(),
                    items,
                    summary: plan.summary,
                    used_fallback: false,
                    evidence,
                    fallback: Some(fallback),
                })
            }
            other => {
                let reason = match other {
                    Ok(_) => "AI returned an empty plan".to_string(),
                    Err(e) => e.reason(),
                };
                Ok(pb::AiStudyPlan {
                    ai_available: false,
                    unavailable_reason: reason,
                    items: fallback_items,
                    summary: "Deterministic study plan (AI unavailable).".to_string(),
                    used_fallback: true,
                    evidence,
                    fallback: Some(fallback),
                })
            }
        }
    }
}

/// The measured app data the plan must be grounded in.
fn build_evidence(snap: &Snapshot) -> Vec<String> {
    let mut ev = Vec::new();
    ev.push(format!(
        "Overall topic coverage: {:.0}%",
        snap.overall_coverage() * 100.0
    ));
    ev.push(format!("Graded reviews so far: {}", snap.graded_reviews));
    ev.push(format!(
        "Knowledge cards reviewed: {} of {}",
        snap.knowledge_cards_reviewed, snap.knowledge_cards_total
    ));
    ev.push(format!("Review streak: {} day(s)", snap.streak_days));

    // Weakest covered topics by recall.
    let mut weak: Vec<(&str, f64, u32)> = snap
        .topics
        .iter()
        .filter(|t| t.has_knowledge())
        .map(|t| {
            (
                t.topic_name.as_str(),
                t.memory_recall().unwrap_or(0.0),
                t.due_card_ids.len() as u32,
            )
        })
        .collect();
    weak.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));
    for (name, recall, due) in weak.iter().take(3) {
        ev.push(format!(
            "Weak topic: {name} — recall {:.0}%, {due} card(s) due",
            recall * 100.0
        ));
    }

    // Largest transfer gaps (recall much higher than application accuracy).
    let mut gaps: Vec<(&str, f64)> = snap
        .topics
        .iter()
        .filter_map(|t| {
            let m = t.memory_recall()?;
            let p = t.performance_accuracy()?;
            Some((t.topic_name.as_str(), m - p))
        })
        .collect();
    gaps.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    if let Some((name, gap)) = gaps.first() {
        if *gap > 0.1 {
            ev.push(format!(
                "Transfer gap: {name} — recall exceeds application accuracy by {:.0} points",
                gap * 100.0
            ));
        }
    }
    ev
}

/// A deterministic plan derived from the recommender candidates. This is the
/// fallback that keeps working with AI off.
fn deterministic_items(snap: &Snapshot, rec: &pb::StudyRecommendation) -> Vec<pb::AiStudyPlanItem> {
    let mut items = Vec::new();
    for cand in rec.candidates.iter().take(3) {
        let minutes = 15 + (cand.due_cards.min(20) as i32);
        items.push(pb::AiStudyPlanItem {
            action: format!("Study {}", cand.topic_name),
            minutes,
            reason: format!(
                "Exam weight {:.0}, weakness {:.0}%, {} card(s) due",
                cand.exam_weight,
                cand.weakness * 100.0,
                cand.due_cards
            ),
            evidence: vec![format!(
                "Recommender priority {:.3} for {}",
                cand.priority_score, cand.topic_key
            )],
        });
    }
    if items.is_empty() {
        items.push(pb::AiStudyPlanItem {
            action: "Add and study MCAT-tagged cards to start building coverage".to_string(),
            minutes: 20,
            reason: "No topics have due cards yet.".to_string(),
            evidence: vec![format!(
                "Coverage {:.0}%, {} graded reviews",
                snap.overall_coverage() * 100.0,
                snap.graded_reviews
            )],
        });
    }
    items
}
