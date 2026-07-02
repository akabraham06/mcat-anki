// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Tests for the MCAT scoring, recommender, interleaving, transfer-gap and XP
//! features. These verify the deterministic engine logic that both the desktop
//! dashboard and the mobile companion rely on.

use anki_proto::mcat as pb;

use crate::card::FsrsMemoryState;
use crate::collection::Collection;
use crate::mcat::scores::estimate;
use crate::notetype::Notetype;
use crate::prelude::*;

fn rreq() -> pb::ExamReadinessRequest {
    pb::ExamReadinessRequest {
        search: String::new(),
        tag_prefix: String::new(),
        default_target_seconds: 0.0,
    }
}

/// Add a Basic (knowledge) note with the given tags.
fn add_knowledge(col: &mut Collection, front: &str, tags: &[&str]) -> Note {
    let nt = col.basic_notetype();
    let mut note = nt.new_note();
    note.set_field(0, front).unwrap();
    note.tags = tags.iter().map(|t| t.to_string()).collect();
    col.add_note(&mut note, DeckId(1)).unwrap();
    note
}

/// Create (and register) an `MCATPerf` notetype for exam-style questions.
fn perf_notetype(col: &mut Collection) -> Notetype {
    let mut nt = col.basic_notetype();
    nt.id = NotetypeId(0);
    nt.name = "MCATPerf".to_string();
    col.add_notetype(&mut nt, false).unwrap();
    nt
}

fn add_perf(col: &mut Collection, nt: &Notetype, front: &str, tags: &[&str]) {
    let mut note = nt.new_note();
    note.set_field(0, front).unwrap();
    note.tags = tags.iter().map(|t| t.to_string()).collect();
    col.add_note(&mut note, DeckId(1)).unwrap();
}

fn strong_memory(col: &mut Collection, note: &Note) {
    let cid = col.storage.all_cards_of_note(note.id).unwrap()[0].id;
    let mut card = col.storage.get_card(cid).unwrap().unwrap();
    card.memory_state = Some(FsrsMemoryState {
        stability: 200.0,
        difficulty: 5.0,
    });
    card.decay = Some(fsrs::FSRS5_DEFAULT_DECAY);
    card.last_review_time = Some(TimestampSecs::now());
    col.storage.update_card(&card).unwrap();
}

#[test]
fn estimate_is_deterministic_and_clamped() {
    // Low coverage + no evidence => wide band, clamped to the scale, low conf.
    let (point, low, _high, confidence) = estimate(472.0, 528.0, 0.5, 0.0, 0);
    assert_eq!(point, 500.0);
    assert_eq!(low, 472.0);
    assert_eq!(confidence, "low");

    // Perfect ability, full coverage, lots of evidence => top of scale, high.
    let (point, _low, high, confidence) = estimate(472.0, 528.0, 1.0, 1.0, 10_000);
    assert_eq!(point, 528.0);
    assert_eq!(high, 528.0);
    assert_eq!(confidence, "high");
}

#[test]
fn readiness_abstains_without_enough_evidence() {
    let mut col = Collection::new();
    add_knowledge(&mut col, "a", &["mcat::biobiochem::metabolism"]);

    let r = col.mcat_exam_readiness(rreq()).unwrap();

    // The give-up rule is stated and enforced.
    let rule = r.give_up_rule.unwrap();
    assert_eq!(rule.min_graded_reviews, 100);
    assert!(rule.min_coverage_percent > 0.0);

    let readiness = r.readiness.unwrap();
    assert!(!readiness.available);
    assert!(!readiness.abstain_reason.is_empty());

    // No memory state yet => memory score also abstains.
    assert!(!r.memory.unwrap().available);

    // One covered topic out of the whole taxonomy => partial coverage.
    assert!(r.overall_coverage_percent > 0.0 && r.overall_coverage_percent < 100.0);
}

#[test]
fn recommender_prioritizes_high_weight_weak_topic() {
    let mut col = Collection::new();
    add_knowledge(&mut col, "s", &["mcat::chemphys::stoichiometry"]); // weight 2
    for i in 0..3 {
        add_knowledge(
            &mut col,
            &format!("m{i}"),
            &["mcat::biobiochem::metabolism"],
        );
        // weight 5
    }

    let r = col.mcat_exam_readiness(rreq()).unwrap();
    let rec = r.recommendation.unwrap();
    assert!(rec.available);
    assert_eq!(rec.topic_key, "mcat::biobiochem::metabolism");
    assert!(rec.explanation.contains("Metabolism"));
    assert!(!rec.candidates.is_empty());
    // Top candidate matches the recommendation.
    assert_eq!(rec.candidates[0].topic_key, "mcat::biobiochem::metabolism");
}

#[test]
fn interleaving_differs_from_blocked() {
    let mut col = Collection::new();
    add_knowledge(&mut col, "m1", &["mcat::biobiochem::metabolism"]);
    add_knowledge(&mut col, "m2", &["mcat::biobiochem::metabolism"]);
    add_knowledge(&mut col, "s1", &["mcat::chemphys::stoichiometry"]);
    add_knowledge(&mut col, "s2", &["mcat::chemphys::stoichiometry"]);

    let inter = col
        .mcat_interleaved_session(pb::InterleavedSessionRequest {
            tag_prefix: String::new(),
            max_cards: 0,
            interleave: true,
        })
        .unwrap();
    assert!(inter.interleaved);
    assert_eq!(inter.card_ids.len(), 4);
    // Round-robin: adjacent cards come from different topics.
    assert_ne!(inter.topic_keys[0], inter.topic_keys[1]);

    let blocked = col
        .mcat_interleaved_session(pb::InterleavedSessionRequest {
            tag_prefix: String::new(),
            max_cards: 0,
            interleave: false,
        })
        .unwrap();
    assert!(!blocked.interleaved);
    // Blocked: first two cards come from the same topic.
    assert_eq!(blocked.topic_keys[0], blocked.topic_keys[1]);
}

#[test]
fn performance_and_transfer_gap() {
    let mut col = Collection::new();
    let perf_nt = perf_notetype(&mut col);
    // Two exam-style questions on the same topic: one correct, one wrong.
    add_perf(&mut col, &perf_nt, "q1", &["mcat::biobiochem::metabolism"]);
    add_perf(&mut col, &perf_nt, "q2", &["mcat::biobiochem::metabolism"]);
    col.answer_good(); // q1 correct
    col.answer_again(); // q2 incorrect
    col.clear_study_queues();

    // A strong knowledge card on the same topic.
    let note = add_knowledge(&mut col, "k", &["mcat::biobiochem::metabolism"]);
    strong_memory(&mut col, &note);

    let r = col.mcat_exam_readiness(rreq()).unwrap();

    let perf = r.performance.unwrap();
    assert!(perf.available);
    assert!(perf.evidence_count >= 2);

    let gap = r
        .transfer_gaps
        .iter()
        .find(|g| g.topic_key == "mcat::biobiochem::metabolism")
        .expect("transfer gap for metabolism");
    assert!(gap.available);
    assert!((gap.performance_accuracy - 0.5).abs() < 1e-6);
    assert!(gap.memory_recall > 0.9);
    assert!((gap.gap - (gap.memory_recall - gap.performance_accuracy)).abs() < 1e-6);
}

#[test]
fn xp_tracks_reviews() {
    let mut col = Collection::new();
    add_knowledge(&mut col, "a", &["mcat::biobiochem::metabolism"]);
    col.answer_good();
    col.clear_study_queues();

    let r = col.mcat_exam_readiness(rreq()).unwrap();
    let xp = r.xp.unwrap();
    assert_eq!(xp.total_xp, r.graded_reviews * 10);
    assert!(xp.total_xp >= 10);
    assert!(xp.reviews_today >= 1);
    assert!(xp.level >= 1);
}
