// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! "Beat-your-ghost" gamification: race the user against their previous BEST
//! timed exam session.
//!
//! A *session* is a run of exam-style ("performance") reviews grouped from the
//! review log by an inactivity gap. For each session we know, in order, whether
//! each question was answered correctly and how long it took, which yields a
//! *pace profile*: cumulative time and cumulative accuracy after every
//! question. The **ghost** is the pace profile of the personal-best prior
//! session (best accuracy first, then fastest), so the reviewer can show, live,
//! whether the user is ahead/behind their past self and celebrate a new
//! personal best at the end.
//!
//! This is a pure, deterministic engagement layer. The ghost and session
//! numbers are derived only for display and are **never** an input to the
//! readiness / memory / performance scores (PRD Risk 5): nothing here is called
//! from `scores.rs`, and the module keeps its own math self-contained.

use anki_proto::mcat as pb;

use crate::mcat::snapshot::PERF_NOTETYPES;
use crate::mcat::snapshot::PERF_TAGS;
use crate::prelude::*;
use crate::search::SortMode;

/// Config key for the user-facing on/off toggle. Defaults to enabled.
pub(crate) const CFG_GHOST_ENABLED: &str = "mcat.ghost.enabled";

/// Reviews more than this many seconds apart start a new session. Thirty
/// minutes comfortably separates distinct study sittings while keeping the
/// natural pauses within one exam block together.
const SESSION_GAP_SECS: i64 = 30 * 60;

/// A session needs at least this many graded questions to qualify as a ghost;
/// shorter runs are too noisy to race against.
const MIN_SESSION_QUESTIONS: usize = 3;

/// A single graded exam answer, as pulled from the revlog.
#[derive(Debug, Clone, Copy)]
pub(crate) struct ExamAnswer {
    /// Review timestamp in unix milliseconds (the revlog id).
    pub at_millis: i64,
    pub correct: bool,
    pub time_ms: i64,
}

/// A derived timed session: an ordered run of exam answers.
#[derive(Debug, Clone)]
pub(crate) struct Session {
    pub start_millis: i64,
    pub answers: Vec<ExamAnswer>,
}

impl Session {
    pub(crate) fn question_count(&self) -> usize {
        self.answers.len()
    }

    pub(crate) fn correct_count(&self) -> u32 {
        self.answers.iter().filter(|a| a.correct).count() as u32
    }

    pub(crate) fn total_time_ms(&self) -> i64 {
        self.answers.iter().map(|a| a.time_ms).sum()
    }

    pub(crate) fn accuracy(&self) -> f64 {
        if self.answers.is_empty() {
            0.0
        } else {
            self.correct_count() as f64 / self.answers.len() as f64
        }
    }

    /// Mean answer time per question (ms); lower is faster. Used as the speed
    /// tie-break so sessions of different lengths compare fairly.
    fn avg_time_ms(&self) -> f64 {
        if self.answers.is_empty() {
            f64::MAX
        } else {
            self.total_time_ms() as f64 / self.answers.len() as f64
        }
    }
}

/// Group a time-sorted list of exam answers into sessions by inactivity gap.
///
/// Pure function: the input must be sorted ascending by `at_millis`.
pub(crate) fn derive_sessions(answers: &[ExamAnswer]) -> Vec<Session> {
    let mut sessions: Vec<Session> = Vec::new();
    let mut last_at: Option<i64> = None;
    for &ans in answers {
        let new_session = match last_at {
            None => true,
            Some(prev) => (ans.at_millis - prev) / 1000 > SESSION_GAP_SECS,
        };
        if new_session {
            sessions.push(Session {
                start_millis: ans.at_millis,
                answers: Vec::new(),
            });
        }
        sessions.last_mut().unwrap().answers.push(ans);
        last_at = Some(ans.at_millis);
    }
    sessions
}

/// Pick the personal-best session to race against.
///
/// Only sessions with at least [`MIN_SESSION_QUESTIONS`] questions qualify.
/// Ranking is accuracy first (higher wins), then speed (lower mean time per
/// question wins), then more questions (more evidence), then the earlier
/// session — a total, deterministic order. Returns the index into `sessions`.
pub(crate) fn select_best(sessions: &[Session]) -> Option<usize> {
    sessions
        .iter()
        .enumerate()
        .filter(|(_, s)| s.question_count() >= MIN_SESSION_QUESTIONS)
        .max_by(|(_, a), (_, b)| {
            a.accuracy()
                .partial_cmp(&b.accuracy())
                .unwrap()
                // faster (smaller avg time) is better -> reverse the compare
                .then_with(|| b.avg_time_ms().partial_cmp(&a.avg_time_ms()).unwrap())
                .then_with(|| a.question_count().cmp(&b.question_count()))
                // earlier session wins the final tie (so it stays stable)
                .then_with(|| b.start_millis.cmp(&a.start_millis))
        })
        .map(|(i, _)| i)
}

/// Format a millisecond duration as `M:SS` (minutes can exceed 59).
fn fmt_mmss(total_ms: i64) -> String {
    let total_secs = (total_ms.max(0)) / 1000;
    let m = total_secs / 60;
    let s = total_secs % 60;
    format!("{m}:{s:02}")
}

/// Short local date like `Jun 30`. Built without `%-d`/`%#d` so it is
/// platform-independent.
fn short_date(at_secs: i64) -> String {
    use chrono::Datelike;
    match TimestampSecs(at_secs).local_datetime() {
        Ok(dt) => format!("{} {}", dt.format("%b"), dt.day()),
        Err(_) => String::new(),
    }
}

impl Collection {
    /// Whether the beat-your-ghost feature is enabled (default true).
    pub(crate) fn mcat_ghost_enabled(&self) -> bool {
        self.get_config_optional::<bool, _>(CFG_GHOST_ENABLED)
            .unwrap_or(true)
    }

    /// Collect the graded exam-style answers in scope, sorted by time.
    fn mcat_exam_answers(&mut self, search: &str) -> Result<Vec<ExamAnswer>> {
        let guard = self.search_cards_into_table(search, SortMode::NoOrder)?;
        let cards = guard.col.storage.all_searched_cards()?;
        let revlog = guard.col.storage.get_revlog_entries_for_searched_cards()?;

        // Determine which searched cards are exam-style (perf tag or notetype).
        let mut exam_cids: std::collections::HashSet<CardId> = std::collections::HashSet::new();
        let mut notetype_is_perf: std::collections::HashMap<NotetypeId, bool> =
            std::collections::HashMap::new();
        for card in &cards {
            let note = guard
                .col
                .storage
                .get_note(card.note_id)?
                .or_not_found(card.note_id)?;
            let tag_marks_perf = note.tags.iter().any(|t| PERF_TAGS.iter().any(|p| t == p));
            let nt_is_perf = *notetype_is_perf.entry(note.notetype_id).or_insert_with(|| {
                guard
                    .col
                    .storage
                    .get_notetype(note.notetype_id)
                    .ok()
                    .flatten()
                    .map(|nt| PERF_NOTETYPES.contains(&nt.name.as_str()))
                    .unwrap_or(false)
            });
            if tag_marks_perf || nt_is_perf {
                exam_cids.insert(card.id);
            }
        }

        let mut answers: Vec<ExamAnswer> = revlog
            .iter()
            .filter(|e| e.has_rating() && exam_cids.contains(&e.cid))
            .map(|e| ExamAnswer {
                at_millis: e.id.0,
                correct: e.button_chosen >= 3,
                time_ms: e.taken_millis as i64,
            })
            .collect();
        answers.sort_by_key(|a| a.at_millis);
        Ok(answers)
    }

    /// Build the ghost pace for the given scope. Returns `available = false`
    /// (with a machine-readable reason) when the feature is disabled or there
    /// is no qualifying prior session to race — the first-run case.
    pub(crate) fn mcat_ghost_pace(&mut self, req: pb::GhostRequest) -> Result<pb::GhostPace> {
        if !self.mcat_ghost_enabled() {
            tracing::info!("mcat ghost: disabled by config");
            return Ok(pb::GhostPace {
                available: false,
                enabled: false,
                reason: "disabled".to_string(),
                ..Default::default()
            });
        }

        let answers = self.mcat_exam_answers(&req.search)?;
        let sessions = derive_sessions(&answers);
        let qualifying = sessions
            .iter()
            .filter(|s| s.question_count() >= MIN_SESSION_QUESTIONS)
            .count() as u32;

        let Some(best_idx) = select_best(&sessions) else {
            tracing::info!(
                sessions = sessions.len(),
                "mcat ghost: no qualifying prior session (first run)"
            );
            return Ok(pb::GhostPace {
                available: false,
                enabled: true,
                reason: "no_prior_session".to_string(),
                sessions_considered: qualifying,
                ..Default::default()
            });
        };
        let best = &sessions[best_idx];

        // Build the per-question pace profile (cumulative time + accuracy).
        let max_q = if req.max_questions == 0 {
            best.answers.len()
        } else {
            (req.max_questions as usize).min(best.answers.len())
        };
        let mut cumulative_time_ms = 0i64;
        let mut cumulative_correct = 0u32;
        let mut questions = Vec::with_capacity(max_q);
        for (i, ans) in best.answers.iter().enumerate() {
            cumulative_time_ms += ans.time_ms;
            if ans.correct {
                cumulative_correct += 1;
            }
            if i < max_q {
                questions.push(pb::GhostQuestion {
                    index: (i + 1) as u32,
                    cumulative_time_ms,
                    cumulative_correct,
                    correct: ans.correct,
                });
            }
        }

        let accuracy = best.accuracy();
        let total_time_ms = best.total_time_ms();
        let recorded_at = best.start_millis / 1000;
        let acc_pct = (accuracy * 100.0).round() as i64;
        let label = format!(
            "{}: {}% · {} · {}",
            self.tr.mcat_ghost_your_best(),
            acc_pct,
            fmt_mmss(total_time_ms),
            short_date(recorded_at),
        );

        tracing::info!(
            questions = best.question_count(),
            accuracy = acc_pct,
            total_time_ms,
            sessions_considered = qualifying,
            "mcat ghost: selected personal-best session"
        );

        Ok(pb::GhostPace {
            available: true,
            enabled: true,
            reason: String::new(),
            label,
            question_count: best.question_count() as u32,
            accuracy,
            total_time_ms,
            recorded_at,
            sessions_considered: qualifying,
            questions,
        })
    }
}

#[cfg(test)]
mod test {
    use super::*;
    use crate::collection::Collection;
    use crate::notetype::Notetype;
    use crate::revlog::RevlogEntry;
    use crate::revlog::RevlogReviewKind;

    fn ghost_req() -> pb::GhostRequest {
        pb::GhostRequest {
            tag_prefix: String::new(),
            search: String::new(),
            max_questions: 0,
        }
    }

    fn perf_notetype(col: &mut Collection) -> Notetype {
        let mut nt = col.basic_notetype();
        nt.id = NotetypeId(0);
        nt.name = "MCATPerf".to_string();
        col.add_notetype(&mut nt, false).unwrap();
        nt
    }

    fn add_perf_card(col: &mut Collection, nt: &Notetype, front: &str) -> CardId {
        let mut note = nt.new_note();
        note.set_field(0, front).unwrap();
        note.tags = vec![
            "mcat::exam".to_string(),
            "mcat::biobiochem::metabolism".to_string(),
        ];
        col.add_note(&mut note, DeckId(1)).unwrap();
        col.storage.all_cards_of_note(note.id).unwrap()[0].id
    }

    /// Insert a synthetic graded exam review directly into the revlog, so tests
    /// can control the timestamp (session grouping), correctness and duration.
    fn log_review(col: &mut Collection, cid: CardId, at_millis: i64, correct: bool, time_ms: u32) {
        let entry = RevlogEntry {
            id: crate::revlog::RevlogId(at_millis),
            cid,
            usn: Usn(-1),
            button_chosen: if correct { 3 } else { 1 },
            interval: 1,
            last_interval: 1,
            ease_factor: 2500,
            taken_millis: time_ms,
            review_kind: RevlogReviewKind::Review,
        };
        col.storage.add_revlog_entry(&entry, true).unwrap();
    }

    const HOUR_MS: i64 = 3_600_000;

    /// The very first run — before any exam review exists — has nothing to
    /// race, so the ghost is enabled but unavailable.
    #[test]
    fn first_ever_session_returns_unavailable_ghost() {
        let mut col = Collection::new();
        let nt = perf_notetype(&mut col);
        // Card exists but has never been reviewed.
        add_perf_card(&mut col, &nt, "q1");

        let ghost = col.mcat_ghost_pace(ghost_req()).unwrap();
        assert!(ghost.enabled);
        assert!(!ghost.available);
        assert_eq!(ghost.reason, "no_prior_session");
        assert_eq!(ghost.question_count, 0);
        assert!(ghost.questions.is_empty());
    }

    #[test]
    fn no_qualifying_session_is_unavailable() {
        let mut col = Collection::new();
        let nt = perf_notetype(&mut col);
        let cid = add_perf_card(&mut col, &nt, "q1");
        // Only two answers -> below MIN_SESSION_QUESTIONS, so nothing qualifies.
        let base = TimestampSecs::now().0 * 1000;
        log_review(&mut col, cid, base, true, 20_000);
        log_review(&mut col, cid, base + 60_000, true, 25_000);

        let ghost = col.mcat_ghost_pace(ghost_req()).unwrap();
        assert!(ghost.enabled);
        assert!(!ghost.available);
        assert_eq!(ghost.reason, "no_prior_session");
    }

    #[test]
    fn sessions_split_on_inactivity_gap() {
        let mut col = Collection::new();
        let nt = perf_notetype(&mut col);
        let cid = add_perf_card(&mut col, &nt, "q1");
        let base = TimestampSecs::now().0 * 1000 - 10 * HOUR_MS;
        // Session A: 3 answers close together.
        log_review(&mut col, cid, base, true, 20_000);
        log_review(&mut col, cid, base + 60_000, true, 20_000);
        log_review(&mut col, cid, base + 120_000, true, 20_000);
        // Session B starts 2 hours later.
        let b = base + 2 * HOUR_MS;
        log_review(&mut col, cid, b, false, 40_000);
        log_review(&mut col, cid, b + 60_000, false, 40_000);
        log_review(&mut col, cid, b + 120_000, false, 40_000);

        let answers = col.mcat_exam_answers("").unwrap();
        let sessions = derive_sessions(&answers);
        assert_eq!(sessions.len(), 2);
        assert_eq!(sessions[0].question_count(), 3);
        assert_eq!(sessions[1].question_count(), 3);
    }

    #[test]
    fn personal_best_prefers_accuracy_then_speed() {
        let mut col = Collection::new();
        let nt = perf_notetype(&mut col);
        let cid = add_perf_card(&mut col, &nt, "q1");
        let base = TimestampSecs::now().0 * 1000 - 20 * HOUR_MS;
        // Session A: 2/3 correct, fast.
        log_review(&mut col, cid, base, true, 10_000);
        log_review(&mut col, cid, base + 30_000, true, 10_000);
        log_review(&mut col, cid, base + 60_000, false, 10_000);
        // Session B (5h later): 3/3 correct but slow -> should win (accuracy).
        let b = base + 5 * HOUR_MS;
        log_review(&mut col, cid, b, true, 50_000);
        log_review(&mut col, cid, b + 60_000, true, 50_000);
        log_review(&mut col, cid, b + 120_000, true, 50_000);
        // Session C (10h later): 3/3 correct and fast -> ties B on accuracy but
        // beats it on speed, so C is the ghost.
        let c = base + 10 * HOUR_MS;
        log_review(&mut col, cid, c, true, 5_000);
        log_review(&mut col, cid, c + 60_000, true, 5_000);
        log_review(&mut col, cid, c + 120_000, true, 5_000);

        let answers = col.mcat_exam_answers("").unwrap();
        let sessions = derive_sessions(&answers);
        assert_eq!(sessions.len(), 3);
        let best = select_best(&sessions).unwrap();
        assert_eq!(best, 2, "fastest of the two perfect sessions should win");

        let ghost = col.mcat_ghost_pace(ghost_req()).unwrap();
        assert!(ghost.available);
        assert_eq!(ghost.question_count, 3);
        assert!((ghost.accuracy - 1.0).abs() < 1e-9);
        assert_eq!(ghost.total_time_ms, 15_000);
        assert_eq!(ghost.sessions_considered, 3);
    }

    #[test]
    fn pace_profile_is_cumulative() {
        let mut col = Collection::new();
        let nt = perf_notetype(&mut col);
        let cid = add_perf_card(&mut col, &nt, "q1");
        let base = TimestampSecs::now().0 * 1000 - 30 * HOUR_MS;
        // Only one qualifying session, so it is the ghost.
        log_review(&mut col, cid, base, true, 10_000);
        log_review(&mut col, cid, base + 30_000, false, 20_000);
        log_review(&mut col, cid, base + 60_000, true, 30_000);

        let ghost = col.mcat_ghost_pace(ghost_req()).unwrap();
        assert!(ghost.available);
        assert_eq!(ghost.questions.len(), 3);

        assert_eq!(ghost.questions[0].index, 1);
        assert_eq!(ghost.questions[0].cumulative_time_ms, 10_000);
        assert_eq!(ghost.questions[0].cumulative_correct, 1);
        assert!(ghost.questions[0].correct);

        assert_eq!(ghost.questions[1].cumulative_time_ms, 30_000);
        assert_eq!(ghost.questions[1].cumulative_correct, 1);
        assert!(!ghost.questions[1].correct);

        assert_eq!(ghost.questions[2].cumulative_time_ms, 60_000);
        assert_eq!(ghost.questions[2].cumulative_correct, 2);
    }

    #[test]
    fn max_questions_caps_profile_but_not_totals() {
        let mut col = Collection::new();
        let nt = perf_notetype(&mut col);
        let cid = add_perf_card(&mut col, &nt, "q1");
        let base = TimestampSecs::now().0 * 1000 - 40 * HOUR_MS;
        for i in 0..5 {
            log_review(&mut col, cid, base + i * 30_000, true, 10_000);
        }

        let mut req = ghost_req();
        req.max_questions = 2;
        let ghost = col.mcat_ghost_pace(req).unwrap();
        assert!(ghost.available);
        assert_eq!(ghost.questions.len(), 2);
        // Totals still reflect the whole session.
        assert_eq!(ghost.question_count, 5);
        assert_eq!(ghost.total_time_ms, 50_000);
    }

    #[test]
    fn disabled_by_config_reports_disabled() {
        let mut col = Collection::new();
        col.set_config(CFG_GHOST_ENABLED, &false).unwrap();
        let nt = perf_notetype(&mut col);
        let cid = add_perf_card(&mut col, &nt, "q1");
        let base = TimestampSecs::now().0 * 1000;
        for i in 0..4 {
            log_review(&mut col, cid, base + i * 30_000, true, 10_000);
        }

        let ghost = col.mcat_ghost_pace(ghost_req()).unwrap();
        assert!(!ghost.enabled);
        assert!(!ghost.available);
        assert_eq!(ghost.reason, "disabled");
    }

    #[test]
    fn non_exam_reviews_are_ignored() {
        let mut col = Collection::new();
        // A plain Basic (knowledge) card, not an exam card.
        let basic = col.basic_notetype();
        let mut note = basic.new_note();
        note.set_field(0, "k").unwrap();
        note.tags = vec!["mcat::biobiochem::metabolism".to_string()];
        col.add_note(&mut note, DeckId(1)).unwrap();
        let cid = col.storage.all_cards_of_note(note.id).unwrap()[0].id;
        let base = TimestampSecs::now().0 * 1000;
        for i in 0..5 {
            log_review(&mut col, cid, base + i * 30_000, true, 10_000);
        }

        let answers = col.mcat_exam_answers("").unwrap();
        assert!(
            answers.is_empty(),
            "knowledge reviews must not count as exam answers"
        );
        let ghost = col.mcat_ghost_pace(ghost_req()).unwrap();
        assert!(!ghost.available);
        assert_eq!(ghost.reason, "no_prior_session");
    }
}
