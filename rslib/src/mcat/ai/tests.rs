// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Unit tests for the Phase 2 AI features, all using the deterministic
//! [`MockAiClient`] so they run with no network and no key. They cover each
//! feature's shape plus the 9.9 safety requirement that the core app keeps
//! working when AI fails.

use std::sync::atomic::AtomicUsize;
use std::sync::atomic::Ordering;
use std::sync::Arc;

use anki_proto::mcat as pb;

use super::mask_key;
use super::AiConfig;
use super::AiError;
use super::MockAiClient;
use crate::collection::Collection;
use crate::prelude::*;

fn rreq() -> pb::ExamReadinessRequest {
    pb::ExamReadinessRequest {
        search: String::new(),
        tag_prefix: String::new(),
        default_target_seconds: 0.0,
    }
}

/// A collection whose AI client is the deterministic mock.
fn mock_col() -> Collection {
    let mut col = Collection::new();
    col.set_config("mcat.ai.mock", &true).unwrap();
    col
}

fn add_knowledge(col: &mut Collection, front: &str, back: &str, tags: &[&str]) -> Note {
    let nt = col.basic_notetype();
    let mut note = nt.new_note();
    note.set_field(0, front).unwrap();
    note.set_field(1, back).unwrap();
    note.tags = tags.iter().map(|t| t.to_string()).collect();
    col.add_note(&mut note, DeckId(1)).unwrap();
    note
}

fn register_source(col: &mut Collection, excerpt: &str) -> String {
    let list = col
        .mcat_register_source(pb::AiSource {
            source_id: String::new(),
            source_name: "Kaplan Biochem Ch. 3".into(),
            source_section: "p. 42".into(),
            excerpt: excerpt.into(),
            registered_at: 0,
        })
        .unwrap();
    list.sources.last().unwrap().source_id.clone()
}

// --- Config resolution -----------------------------------------------------

#[test]
fn config_defaults_and_masking() {
    let col = Collection::new();
    let cfg = col.mcat_ai_config();
    assert_eq!(cfg.base_url, super::DEFAULT_BASE_URL);
    assert_eq!(cfg.model, super::DEFAULT_MODEL);
    assert_eq!(cfg.checker_cutoff, super::DEFAULT_CHECKER_CUTOFF);
    // No key and a non-local endpoint => unavailable.
    assert!(!cfg.configured());
    assert!(!cfg.available());

    assert_eq!(mask_key("sk-abcdef123456"), "sk-...3456");
    assert_eq!(mask_key(""), "");
}

#[test]
fn local_endpoint_is_configured_without_key() {
    let mut col = Collection::new();
    col.mcat_set_ai_config(pb::AiConfig {
        base_url: "http://localhost:11434/v1".into(),
        model: "llama3".into(),
        api_key: String::new(),
        checker_cutoff: 0.7,
        enabled: true,
        api_key_set: false,
    })
    .unwrap();
    let cfg = col.mcat_ai_config();
    assert_eq!(cfg.base_url, "http://localhost:11434/v1");
    assert!(cfg.configured(), "a local endpoint needs no key");
    assert!(cfg.available());
}

#[test]
fn set_config_masked_key_roundtrip_preserves_key() {
    let mut col = Collection::new();
    col.mcat_set_ai_config(pb::AiConfig {
        base_url: "https://api.openai.com/v1".into(),
        model: "gpt-4o-mini".into(),
        api_key: "sk-realsecret1234".into(),
        checker_cutoff: 0.8,
        enabled: true,
        api_key_set: false,
    })
    .unwrap();
    let masked = col.mcat_ai_config_pb();
    assert!(masked.api_key_set);
    assert!(masked.api_key.starts_with("sk-..."));
    // Saving the masked value back must not overwrite the stored key.
    col.mcat_set_ai_config(masked.clone()).unwrap();
    let cfg = col.mcat_ai_config();
    assert_eq!(cfg.api_key.as_deref(), Some("sk-realsecret1234"));
    assert_eq!(cfg.checker_cutoff, 0.8);
}

// --- Source registry (9.3 / 9.9) -------------------------------------------

#[test]
fn source_requires_excerpt() {
    let mut col = Collection::new();
    let err = col.mcat_register_source(pb::AiSource {
        source_name: "No excerpt".into(),
        ..Default::default()
    });
    assert!(err.is_err(), "a source without an excerpt must be rejected");
}

#[test]
fn generation_rejects_without_registered_source() {
    let mut col = mock_col();
    let res = col
        .mcat_generate_cards(pb::GenerateCardsRequest {
            source_id: "does-not-exist".into(),
            count: 3,
            topic_hint: "mcat::biobiochem::metabolism".into(),
            tag_prefix: String::new(),
            difficulty: String::new(),
        })
        .unwrap();
    assert!(!res.ai_available);
    assert!(res.cards.is_empty());
    assert!(res.unavailable_reason.to_lowercase().contains("source"));
}

// --- 9.3 generation --------------------------------------------------------

#[test]
fn generation_produces_checked_cards_and_accepts_them() {
    let mut col = mock_col();
    let excerpt = "Phosphofructokinase-1 catalyzes the committed step of glycolysis. \
         The citric acid cycle occurs in the mitochondrial matrix. Competitive inhibitors \
         raise the apparent Km while leaving Vmax unchanged.";
    let sid = register_source(&mut col, excerpt);

    let res = col
        .mcat_generate_cards(pb::GenerateCardsRequest {
            source_id: sid.clone(),
            count: 3,
            topic_hint: "mcat::biobiochem::glycolysis".into(),
            tag_prefix: String::new(),
            difficulty: String::new(),
        })
        .unwrap();
    assert!(res.ai_available);
    assert!(!res.cards.is_empty());
    for card in &res.cards {
        // Every card carries a source and a quality report (9.3 acceptance
        // criteria: no card without a source; checked before the deck).
        assert_eq!(card.source_id, sid);
        assert!(!card.source_name.is_empty());
        let q = card.quality.as_ref().unwrap();
        assert!(!q.categories.is_empty());
        assert!(q.categories.iter().any(|c| c.key == "source_supported"));
    }

    // Accept only the NeedsReview cards -> real, labelled notes.
    let accept = col
        .mcat_accept_cards(pb::AcceptCardsRequest {
            cards: res.cards.clone(),
            deck_name: String::new(),
            tag_prefix: String::new(),
        })
        .unwrap();
    assert_eq!(accept.created as usize, accept.note_ids.len());
    // At least one grounded card should pass and be created.
    assert!(accept.created >= 1, "expected some accepted cards");

    // Created notes are tagged ai-generated and land in the MCAT AI deck.
    let nid = NoteId(accept.note_ids[0]);
    let note = col.storage.get_note(nid).unwrap().unwrap();
    assert!(note.tags.iter().any(|t| t == "ai-generated"));
}

// --- Difficulty tiering + tagging (wide difficulty range) ------------------

#[test]
fn difficulty_normalizes_to_three_tiers() {
    use super::generate::normalize_difficulty;
    use super::generate::normalize_difficulty_opt;
    // Canonical tiers pass through.
    assert_eq!(normalize_difficulty("recall"), "recall");
    assert_eq!(normalize_difficulty("mcat"), "mcat");
    assert_eq!(normalize_difficulty("stretch"), "stretch");
    // Legacy easy/medium/hard map onto the tiers.
    assert_eq!(normalize_difficulty("easy"), "recall");
    assert_eq!(normalize_difficulty("medium"), "mcat");
    assert_eq!(normalize_difficulty("hard"), "stretch");
    // Case / whitespace tolerant, unknown => the standard band.
    assert_eq!(normalize_difficulty("  STRETCH "), "stretch");
    assert_eq!(normalize_difficulty("whatever"), "mcat");
    // The optional form distinguishes "no tier requested".
    assert_eq!(normalize_difficulty_opt(""), None);
    assert_eq!(normalize_difficulty_opt("  "), None);
    assert_eq!(normalize_difficulty_opt("hard").as_deref(), Some("stretch"));
}

fn generate_tier(col: &mut Collection, sid: &str, tier: &str, count: u32) -> pb::GeneratedCardList {
    col.mcat_generate_cards(pb::GenerateCardsRequest {
        source_id: sid.to_string(),
        count,
        topic_hint: "mcat::biobiochem::glycolysis".into(),
        tag_prefix: String::new(),
        difficulty: tier.to_string(),
    })
    .unwrap()
}

const TIER_EXCERPT: &str = "Glycolysis occurs in the cytosol and converts glucose into two \
     pyruvate molecules. The committed rate-limiting step is catalyzed by phosphofructokinase-1. \
     The citric acid cycle oxidizes pyruvate inside the mitochondrial matrix. Competitive \
     inhibitors raise the apparent Km while leaving Vmax unchanged. Noncompetitive inhibitors \
     lower Vmax without changing Km. Oxidative phosphorylation produces the bulk of cellular ATP.";

#[test]
fn requested_tier_labels_every_card() {
    let mut col = mock_col();
    let sid = register_source(&mut col, TIER_EXCERPT);
    for tier in ["recall", "mcat", "stretch"] {
        let res = generate_tier(&mut col, &sid, tier, 3);
        assert!(res.ai_available);
        assert!(!res.cards.is_empty());
        for card in &res.cards {
            assert_eq!(
                card.difficulty, tier,
                "a requested tier must be authoritative for every card"
            );
        }
    }
}

#[test]
fn mixed_generation_spans_all_three_tiers() {
    let mut col = mock_col();
    let sid = register_source(&mut col, TIER_EXCERPT);
    // No requested tier => a mix.
    let res = col
        .mcat_generate_cards(pb::GenerateCardsRequest {
            source_id: sid,
            count: 6,
            topic_hint: "mcat::biobiochem::glycolysis".into(),
            tag_prefix: String::new(),
            difficulty: String::new(),
        })
        .unwrap();
    let tiers: std::collections::HashSet<&str> =
        res.cards.iter().map(|c| c.difficulty.as_str()).collect();
    for expected in ["recall", "mcat", "stretch"] {
        assert!(
            tiers.contains(expected),
            "mixed batch should include {expected}"
        );
    }
}

#[test]
fn accept_tags_difficulty_tier_and_spans_range() {
    let mut col = mock_col();
    let sid = register_source(&mut col, TIER_EXCERPT);
    // Build a wide-range set the way the pipeline does: generate + accept each
    // tier in turn, so later tiers are duplicate-checked against earlier ones.
    let mut created_per_tier = std::collections::HashMap::new();
    for tier in ["recall", "mcat", "stretch"] {
        let res = generate_tier(&mut col, &sid, tier, 3);
        let accept = col
            .mcat_accept_cards(pb::AcceptCardsRequest {
                cards: res.cards.clone(),
                deck_name: String::new(),
                tag_prefix: String::new(),
            })
            .unwrap();
        created_per_tier.insert(tier, accept.created);
        // Every accepted card carries difficulty::<tier> + the topic tag.
        for nid in &accept.note_ids {
            let note = col.storage.get_note(NoteId(*nid)).unwrap().unwrap();
            assert!(note
                .tags
                .iter()
                .any(|t| t == &format!("difficulty::{tier}")));
            assert!(note
                .tags
                .iter()
                .any(|t| t == "mcat::biobiochem::glycolysis"));
            assert!(note.tags.iter().any(|t| t == "ai-generated"));
        }
    }
    // The tiers do not cannibalise each other via the duplicate gate: each tier
    // contributes at least one accepted card, so the deck spans the full range.
    for tier in ["recall", "mcat", "stretch"] {
        assert!(
            created_per_tier[tier] >= 1,
            "tier {tier} should contribute at least one non-duplicate card"
        );
    }
}

// --- 9.4 checker -----------------------------------------------------------

fn check(
    col: &mut Collection,
    q: &str,
    a: &str,
    tag: &str,
    excerpt: &str,
) -> pb::CardQualityReport {
    col.mcat_check_card(pb::CheckCardRequest {
        question: q.into(),
        answer: a.into(),
        topic_tag: tag.into(),
        source_id: String::new(),
        source_excerpt: excerpt.into(),
        tag_prefix: String::new(),
    })
    .unwrap()
}

#[test]
fn checker_passes_good_card_and_reports_all_categories() {
    let mut col = mock_col();
    let report = check(
        &mut col,
        "In glycolysis, which enzyme catalyzes the committed rate-limiting step?",
        "Phosphofructokinase-1 (PFK-1) converts fructose-6-phosphate to fructose-1,6-bisphosphate.",
        "mcat::biobiochem::glycolysis",
        "",
    );
    assert!(report.ai_available);
    assert!(report.passed, "a clear, specific card should pass");
    assert_eq!(report.verdict, "NeedsReview");
    // Nine categories total (6 AI + duplicate + tagged + source).
    assert_eq!(report.categories.len(), 9);
    assert!(report.overall_score >= report.cutoff);
}

#[test]
fn checker_blocks_vague_and_trivial_cards() {
    let mut col = mock_col();
    let vague = check(
        &mut col,
        "What about metabolism?",
        "It does various things and many stuff, generally.",
        "mcat::biobiochem::metabolism",
        "",
    );
    assert!(!vague.passed, "vague card must be blocked");
    assert_eq!(vague.verdict, "Blocked");
    assert!(vague
        .categories
        .iter()
        .any(|c| c.key == "not_vague" && !c.passed));

    let trivial = check(
        &mut col,
        "Krebs?",
        "Krebs.",
        "mcat::biobiochem::metabolism",
        "",
    );
    assert!(!trivial.passed, "trivial card must be blocked");
}

#[test]
fn checker_blocks_unsupported_answer_when_source_present() {
    let mut col = mock_col();
    // Answer's content words do not appear in the source excerpt.
    let report = check(
        &mut col,
        "What organelle houses the citric acid cycle?",
        "The ribosome performs photosynthesis in the chloroplast stroma entirely.",
        "mcat::biobiochem::metabolism",
        "The citric acid cycle occurs in the mitochondrial matrix.",
    );
    assert!(
        report
            .categories
            .iter()
            .any(|c| c.key == "source_supported" && !c.passed),
        "unsupported answer must fail source grounding"
    );
    assert!(!report.passed, "unsupported card is blocked (hard fail)");
}

#[test]
fn checker_detects_duplicates() {
    let mut col = mock_col();
    add_knowledge(
        &mut col,
        "Where does the citric acid (Krebs) cycle occur?",
        "The mitochondrial matrix.",
        &["mcat::biobiochem::metabolism"],
    );
    let report = check(
        &mut col,
        "Where does the citric acid Krebs cycle occur?",
        "The mitochondrial matrix.",
        "mcat::biobiochem::metabolism",
        "",
    );
    assert!(
        report.duplicate,
        "near-identical card should be flagged duplicate"
    );
    assert!(report
        .categories
        .iter()
        .any(|c| c.key == "not_duplicate" && !c.passed));
    assert!(!report.passed);
}

#[test]
fn checker_cutoff_is_configurable() {
    let mut col = mock_col();
    // An impossibly high cutoff blocks even a good card.
    col.set_config("mcat.ai.checker_cutoff", &0.99).unwrap();
    let report = check(
        &mut col,
        "Which enzyme catalyzes the committed step of glycolysis?",
        "Phosphofructokinase-1 converts fructose-6-phosphate to fructose-1,6-bisphosphate.",
        "mcat::biobiochem::glycolysis",
        "",
    );
    assert_eq!(report.cutoff, 0.99);
    assert!(
        !report.passed,
        "cutoff of 0.99 should block a normally-good card"
    );
}

// --- 9.5 explanation -------------------------------------------------------

#[test]
fn explain_miss_is_grounded_and_available() {
    let mut col = mock_col();
    let note = add_knowledge(
        &mut col,
        "Where does the Krebs cycle occur?",
        "The mitochondrial matrix.",
        &["mcat::biobiochem::metabolism"],
    );
    let cid = col.storage.all_cards_of_note(note.id).unwrap()[0].id;
    let exp = col
        .mcat_explain_miss(pb::ExplainMissRequest {
            card_id: cid.0,
            chosen_answer: "The nucleus".into(),
            tag_prefix: String::new(),
        })
        .unwrap();
    assert!(exp.ai_available);
    assert!(!exp.why_correct.is_empty());
    assert!(!exp.why_chosen_wrong.is_empty());
    assert_eq!(exp.related_topic, "mcat::biobiochem::metabolism");
    assert!(exp.source_citation.contains("metabolism"));
}

#[test]
fn explain_miss_handles_missing_card_gracefully() {
    let mut col = mock_col();
    let exp = col
        .mcat_explain_miss(pb::ExplainMissRequest {
            card_id: 999_999,
            chosen_answer: String::new(),
            tag_prefix: String::new(),
        })
        .unwrap();
    assert!(!exp.ai_available);
    assert!(!exp.unavailable_reason.is_empty());
}

// --- 9.6 planner -----------------------------------------------------------

#[test]
fn ai_plan_cites_evidence_when_available() {
    let mut col = mock_col();
    add_knowledge(&mut col, "q", "a", &["mcat::biobiochem::metabolism"]);
    col.answer_good();
    col.clear_study_queues();

    let plan = col.mcat_ai_study_plan(rreq()).unwrap();
    assert!(plan.ai_available);
    assert!(!plan.used_fallback);
    assert!(!plan.items.is_empty());
    assert!(
        !plan.evidence.is_empty(),
        "the data behind the plan is surfaced"
    );
    // Fallback recommender is always attached.
    assert!(plan.fallback.is_some());
    // Every plan item is grounded in evidence.
    assert!(plan.items.iter().all(|i| !i.evidence.is_empty()));
}

#[test]
fn ai_plan_falls_back_to_recommender_when_ai_off() {
    let mut col = Collection::new(); // no mock => AI unavailable
    add_knowledge(&mut col, "q", "a", &["mcat::biobiochem::metabolism"]);

    let plan = col.mcat_ai_study_plan(rreq()).unwrap();
    assert!(!plan.ai_available);
    assert!(plan.used_fallback);
    // The deterministic plan/fallback is still produced.
    assert!(!plan.items.is_empty());
    assert!(plan.fallback.is_some());
}

// --- 9.8 perf-question generation ------------------------------------------

#[test]
fn perf_generation_labels_and_leakage_checks() {
    let mut col = mock_col();
    let note = add_knowledge(
        &mut col,
        "Which enzyme is the committed step of glycolysis?",
        "Phosphofructokinase-1 (PFK-1) commits glucose to glycolysis at the fructose-6-phosphate step.",
        &["mcat::biobiochem::glycolysis"],
    );
    let cid = col.storage.all_cards_of_note(note.id).unwrap()[0].id;
    let res = col
        .mcat_generate_perf_questions(pb::GeneratePerfQuestionsRequest {
            card_id: cid.0,
            tag_prefix: String::new(),
            source_id: String::new(),
        })
        .unwrap();
    assert!(res.ai_available);
    assert_eq!(
        res.questions.len(),
        2,
        "9.8 requires 2 application questions"
    );
    for q in &res.questions {
        assert!(q.quality.is_some());
        assert_eq!(q.topic_tag, "mcat::biobiochem::glycolysis");
    }

    // Accepted perf questions are labelled ai-generated + mcat::exam.
    let accept = col
        .mcat_accept_perf_questions(pb::AcceptPerfQuestionsRequest {
            questions: res.questions.clone(),
            deck_name: String::new(),
            tag_prefix: String::new(),
        })
        .unwrap();
    if accept.created >= 1 {
        let note = col
            .storage
            .get_note(NoteId(accept.note_ids[0]))
            .unwrap()
            .unwrap();
        assert!(note.tags.iter().any(|t| t == "ai-generated"));
        assert!(note.tags.iter().any(|t| t == "mcat::exam"));
    }
}

// --- 9.9 safety: AI failure never breaks the core app ----------------------

#[test]
fn malformed_ai_output_is_reported_not_fatal() {
    // A responder that always returns junk => Malformed after one retry.
    let cfg = AiConfig {
        base_url: "https://example.com/v1".into(),
        model: "m".into(),
        api_key: Some("k".into()),
        checker_cutoff: 0.7,
        enabled: true,
    };
    let client = MockAiClient::with_responder(cfg, Arc::new(|_| Ok("not json at all".into())));
    let req = super::ChatRequest::new(super::AiTask::Plan, "s", "u");
    let parsed: super::AiResult<serde_json::Value> = super::complete_json(&client, &req);
    assert!(matches!(parsed, Err(AiError::Malformed { .. })));
}

#[test]
fn retry_recovers_from_a_single_bad_response() {
    let calls = Arc::new(AtomicUsize::new(0));
    let calls2 = calls.clone();
    let cfg = AiConfig {
        base_url: "https://example.com/v1".into(),
        model: "m".into(),
        api_key: Some("k".into()),
        checker_cutoff: 0.7,
        enabled: true,
    };
    let responder = Arc::new(move |_req: &super::ChatRequest| {
        let n = calls2.fetch_add(1, Ordering::SeqCst);
        if n == 0 {
            Ok("garbage".to_string())
        } else {
            Ok(r#"{"ok": true}"#.to_string())
        }
    });
    let client = MockAiClient::with_responder(cfg, responder);
    let req = super::ChatRequest::new(super::AiTask::Plan, "s", "u");
    let parsed: super::AiResult<serde_json::Value> = super::complete_json(&client, &req);
    assert!(parsed.is_ok());
    assert_eq!(calls.load(Ordering::SeqCst), 2, "should retry exactly once");
}

/// The rubric-critical guarantee: when AI fails, review/scoring still work.
#[test]
fn core_scoring_works_when_ai_unavailable() {
    let mut col = Collection::new(); // AI off (no mock, no key)
    add_knowledge(&mut col, "q", "a", &["mcat::biobiochem::metabolism"]);
    col.answer_good();
    col.clear_study_queues();

    // AI status honestly reports unavailable.
    let status = col.mcat_ai_status();
    assert!(!status.available);
    assert!(!status.reason.is_empty());

    // AI-dependent features degrade to unavailable rather than erroring.
    let gen = col
        .mcat_generate_cards(pb::GenerateCardsRequest {
            source_id: String::new(),
            count: 3,
            topic_hint: String::new(),
            tag_prefix: String::new(),
            difficulty: String::new(),
        })
        .unwrap();
    assert!(!gen.ai_available);

    // Core scoring is unaffected.
    let readiness = col.mcat_exam_readiness(rreq()).unwrap();
    assert!(readiness.memory.is_some());
    assert!(readiness.recommendation.unwrap().available);
    // And the collection is still valid.
    let problems = col.check_database().unwrap().to_i18n_strings(&col.tr);
    assert!(problems.is_empty());
}
