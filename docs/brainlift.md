# Brainlift — MCAT Anki Mastery

> **Personalize this.** This is a factual, repo-grounded starting point. Replace
> this note with your own voice: what _you_ learned, where you got stuck, and the
> judgement calls you'd defend in a review. The technical claims below are all
> traceable to code and to the eval reports in this repository.

## What was built

A fork of [Anki](https://apps.ankiweb.net) turned into an **MCAT readiness app**
with two front-ends over **one shared Rust engine**:

- A **desktop app** (PyQt + a Svelte dashboard over `pylib` → `rslib`).
- An **iOS companion** (SwiftUI over the same `rslib` engine via a C-FFI packaged
  as `AnkiEngine.xcframework`).

The core addition is an **MCAT mastery/readiness engine** inside Anki's Rust
layer (`rslib/src/mcat`), exposed through a new `McatService` in
`proto/anki/mcat.proto` and consumed identically by Python, TypeScript, and
Swift. It computes three honest scores (Memory, Performance, Readiness), a
best-next-topic recommender, a recall-vs-transfer gap metric, interleaving, timed
pacing, and local XP. Five AI features (`rslib/src/mcat/ai/`) assist **authoring
and coaching only** — they never feed the score.

## Why these decisions

- **Change the engine, not a plugin.** Putting MCAT logic in `rslib` means the
  desktop and phone compute _identical_ numbers for free, and sync/scheduling
  come along for the ride. The cost is a brownfield change to a mature codebase
  (see `steps.md` for upstream files touched and merge-risk notes).
- **Three scores, not one.** Recall (Memory) is necessary but not sufficient for
  an exam. Splitting out Performance (accuracy on _new_ exam-style questions) and
  Readiness (a weighted blend) makes the difference measurable — and the
  transfer-gap metric quantifies how much recall doesn't survive rewording.
- **Honesty rule / abstention.** Readiness refuses to produce a number until
  there are ≥ 100 graded reviews and ≥ 50% topic coverage; every score ships with
  a range, coverage, confidence, and reasons. Better to say "not enough data"
  than to fake precision (`rslib/src/mcat/scores.rs`).
- **AI is source-grounded and gated.** Generation requires a registered source;
  every accepted card carries a visible `Source:` citation and an
  `ai-source::<id>` tag. A quality checker blocks vague/wrong/duplicate cards
  before a student sees them. Untrusted source text is treated as data, not
  instructions (prompt-injection handling in the AI layer).
- **Zero-config AI.** The app ships pointed at a built-in hosted proxy so AI
  works with no API key typed in, and degrades gracefully to deterministic
  baselines when AI is off or unavailable.

## Key technical insights (with evidence)

- **Held-out evals beat vibes.** The card-quality gate is measured against
  keyword and TF-IDF baselines on a held-out labelled set, and the two scoring
  models are validated with proper held-out splits, not in-sample fits.
  - Memory calibration: **Brier 0.190, log loss 0.560, ECE 0.022**, with the
    predicted probability cross-checked against the live engine to `|Δ| ≈ 2.8e-4`
    (`mcat/ai_eval/model_validation_report.md`).
  - Performance held-out accuracy: **71.3% vs 59.6%** majority baseline.
  - Recall→transfer gap: **21.3 pts**, with a control that collapses it to 0.0 —
    a genuine falsification test, not a one-sided demo
    (`mcat/ai_eval/experiments_report.md`).
  - Card-quality gate: **0/20 good cards blocked, 6/6 wrong-fact and 24/24
    bad-teaching cards caught** at a pre-registered 0.70 cutoff
    (`mcat/ai_eval/report.md`).
- **Report negative results.** Under a strictly equal study budget, the
  topic-weighted recommender was **−0.6 pts vs plain interleaving** (interleaving
  itself was +6.2 pts vs blocking). Even coverage captured the benefit; targeted
  weighting hit diminishing returns. Shipping this honestly is the point.
- **Guard against leakage.** A scanner (`just mcat-eval-leakage`) confirms **0/66**
  held-out items duplicate any training item (nearest neighbour 0.44), backed by
  a planted-duplicate sanity check so the clean result is verified, not assumed.
- **Sync conflicts have a written-down rule.** Reviews are append-only (unique
  millisecond ids ⇒ never lost or double-counted); card state resolves
  last-writer-wins by modification time. The rule lives in
  `rslib/src/sync/collection/chunks.rs` (`merge_revlog:168`,
  `add_or_update_card_if_newer:182`), is documented in
  `docs/sync-conflict-rule.md`, and is exercised by `just mcat-sync-conflict`.
- **Crash-safety comes from SQLite.** A killed write is rolled back by the
  journal on reopen. `just mcat-crash-test` SIGKILLs a review worker mid-write 20
  times and asserts zero corruption and no lost reviews every time — and that the
  app still scores with AI off.
- **It scales.** On a 50,000-card deck the core actions stay fast: search ≈ 13 ms,
  next card ≈ 0.1 ms, answer/undo < 1 ms, and a full three-score recompute
  (`exam_readiness`) ≈ 0.35 s (`mcat/bench/results/bench_50000.md`).

## Where the proof lives

| Area                                           | Command                                                                                     | Report                                    |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------- |
| AI features vs no-AI baselines                 | `just mcat-ai-eval`                                                                         | `mcat/ai_eval/report.md`                  |
| Memory + performance model validation          | `just mcat-eval-calibration`, `just mcat-eval-performance`                                  | `mcat/ai_eval/model_validation_report.md` |
| Transfer, three-build study, leakage, gold-set | `just mcat-eval-paraphrase` · `mcat-eval-study` · `mcat-eval-leakage` · `mcat-eval-goldset` | `mcat/ai_eval/experiments_report.md`      |
| Engine performance at 50k cards                | `just mcat-bench`                                                                           | `mcat/bench/results/bench_50000.md`       |
| Crash safety + offline AI-off                  | `just mcat-crash-test`                                                                      | (asserts in-harness)                      |
| Sync conflict rule                             | `just mcat-sync-conflict`                                                                   | `docs/sync-conflict-rule.md`              |
| The three models, in depth                     | —                                                                                           | `docs/model-descriptions.md`              |

## Honesty caveats

The engine calls, formulas, and the AI grounding/gating are **real**. The
**learner outcomes** used in the model-validation and study experiments are
**seeded synthetic** populations with documented assumptions — there is no real
student review data in this repository. The evals therefore prove the scoring
math is correct and internally consistent against the engine; real-world model
accuracy needs logged human review history (the metric code is unchanged, only
the data source swaps). See `mcat/ai_eval/AI_NOTES.md` for what was built, why,
and what was intentionally skipped.
