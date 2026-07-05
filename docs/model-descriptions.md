# The three MCAT models

The MCAT dashboard reports **three separate scores** — Memory, Performance, and
Readiness — each with a point estimate, an honest range, exam coverage,
confidence, and the reasons behind it. All three are computed **deterministically
in the Rust engine** (`rslib/src/mcat/scores.rs`); no AI is involved in scoring,
so the numbers are identical on desktop and iOS and are reproducible on any
device. This document describes what each model actually computes, grounded in
the code, and states honestly what has and hasn't been validated.

The exam scale is **472–528** for the overall scores and **118–132** per section
(from `rslib/src/mcat/taxonomy.json` → `score_scale`).

---

## 1. Memory model — "can you recall a fact right now?"

**What it is.** The Memory score is the mean per-card **FSRS retrievability** —
the engine's estimate of the probability you still remember a card at this
instant. Anki's FSRS computes retrievability with the forgetting curve
(`rslib/src/mcat/snapshot.rs` via `fsrs::current_retrievability`):

```
R = (1 + FACTOR · elapsed_days / stability) ^ (−DECAY)
FACTOR = 0.9 ^ (1 / −DECAY) − 1
DECAY  = 0.1542            # FSRS-6 default for a default deck
```

The engine averages `R` over every reviewed knowledge card:

```
memory_fraction = Σ recall / count of reviewed cards        (scores.rs:138)
Memory point    = 472 + memory_fraction · (528 − 472)
```

**Range / confidence.** Every score is passed through one `estimate()` function
(`scores.rs:32`) that turns coverage and evidence into an uncertainty band:

```
uncertainty = clamp( 0.5·(1 − coverage) + 1/√(evidence + 1),  0.03, 0.6 )
margin      = uncertainty · (scale_max − scale_min)
low, high   = point ∓ margin   (clamped to the scale)
confidence  = high  (< 0.12) | medium (< 0.30) | low
```

So the more of the exam you've covered and the more reviews you've logged, the
tighter the band — the range is a genuine function of evidence, not decoration.

**Abstention.** With no reviewed knowledge cards the model returns
`available = false` with an explicit reason instead of a fake number
(`scores.rs:173`).

**Validation.** `just mcat-eval-calibration` measures whether that probability is
calibrated on a seeded synthetic recall process, after first cross-checking that
the closed form above **equals the live engine's**
`mcat_topic_mastery().average_recall_probability` to `max |Δ| ≈ 2.8e-4`. On the
held-out split it reports **Brier 0.190, log loss 0.560, ECE 0.022** (slightly
over-confident at high predicted recall, as designed by the synthetic ground
truth). Full write-up: `mcat/ai_eval/model_validation_report.md`.

---

## 2. Performance model — "can you answer a new exam-style question?"

**What it is.** The Performance score is the engine's accuracy on exam-style
(performance) questions — any card tagged `mcat::exam`, or a `MCATPerf`
note. Per topic (`rslib/src/mcat/snapshot.rs`, `scores.rs:184`):

```
performance_accuracy = perf_correct / perf_reviews     # button_chosen ≥ 3 = correct
performance_fraction = Σ perf_correct / Σ perf_reviews
Performance point    = 472 + performance_fraction · (528 − 472)
```

It uses the same `estimate()` band as Memory, but driven by **performance
coverage** (the exam-weighted fraction of topics with at least one answered
exam question, `perf_coverage`, `scores.rs:439`) and the number of performance
reviews as evidence. With no exam-style answers it **abstains**.

A companion **transfer-gap** metric (`scores.rs:478`) reports, per topic,
`memory_recall − performance_accuracy` — how much apparent recall does **not**
survive being asked as a fresh question.

**Validation.** `just mcat-eval-performance` splits the **real** starter-deck
`EXAM_MCQ` bank (59 questions across 23 topics) into train/held-out, drives real
graded reviews through the real scheduler, then predicts held-out questions from
each topic's engine-measured accuracy. Result: **71.3% held-out accuracy vs a
59.6% majority-class baseline** (Brier 0.185, ECE 0.027). The paraphrase
experiment (`just mcat-eval-paraphrase`) separately measures a **21.3 pt**
recall→transfer gap (recall 70.9% vs reworded 49.6%), with a control that
collapses the gap to 0.0 pts — confirming a non-trivial gap comes specifically
from surface-bound memorisation, not from the performance signal merely copying
memory.

---

## 3. Readiness — "what MCAT score would you get today, and how sure are we?"

**What it is.** Readiness blends retention, application accuracy, and pacing into
one estimate on the 472–528 scale (`scores.rs:246`):

```
readiness_fraction = 0.35 · memory_fraction        (READINESS_MEMORY_WEIGHT)
                   + 0.50 · performance_fraction    (READINESS_PERFORMANCE_WEIGHT)
                   + 0.15 · speed_factor            (READINESS_SPEED_WEIGHT)
Readiness point    = 472 + readiness_fraction · (528 − 472)
```

- **Performance is weighted highest** because it is closest to the real exam.
- **Speed** is an honest, separately-reported sub-signal:
  `speed_factor = 1 − overtime_rate`, where overtime is the fraction of timed
  exam questions answered slower than the per-topic target. With no timing
  evidence it defaults to 1.0, so pacing never silently penalises
  (`scores.rs:229`).
- The **range/confidence** come from the same `estimate()` function, using
  `min(coverage, perf_coverage)` and the total graded-review count as evidence.

**The give-up (abstention) rule.** Readiness refuses to produce a number until it
has enough evidence (`scores.rs:15`, `scores.rs:247`):

```
readiness available  ⇔  graded_reviews ≥ 100
                    AND  overall coverage ≥ 50%
                    AND  Memory and Performance are both available
```

Otherwise it returns `available = false` and says exactly what's missing (e.g.
"Only 63 of 100 required graded reviews."). This is surfaced to every client as a
`GiveUpRule` message, so the UI can show the rule verbatim.

**The best-next-topic recommender.** Alongside the scores, a deterministic
recommender (`rslib/src/mcat/recommender.rs`) ranks topics by

```
priority = weight_norm · weakness · (0.5 + 0.5 · coverage_gap) · (1 + due_cards)
```

(exam-weight × weakness × coverage-gap × due-ness), fully explainable and
reproducible — it is the honest no-AI baseline the AI study planner must beat.
Note the honest negative result from `just mcat-eval-study`: under a strictly
**equal study budget**, adding topic-weighting on top of plain interleaving was
**−0.6 pts** (interleaving vs blocking was +6.2 pts). Even coverage captured the
gain; weighting hit diminishing returns.

---

## Honesty note — what is real vs synthetic

- **Real:** the FSRS retrievability formula, the per-topic accuracy definition,
  the readiness blend/weights, the give-up rule, the recommender priority, and
  the engine calls are the **actual shipping computations**. The performance
  eval's questions/topics are the real starter-deck content, and its reviews are
  driven through the real scheduler. The memory eval verifies its predicted
  probabilities against the live engine (`|Δ| ≈ 2.8e-4`).
- **Synthetic:** the **outcomes** (did a learner recall a card / answer a
  question correctly). There is no real student review data in this repository,
  so both model-validation evals and the paraphrase/three-build experiments draw
  outcomes from **seeded generative models with documented assumptions** (e.g.
  stability optimism ×0.90, σ 0.55; per-topic ability ∈ [0.30, 0.95]). Swapping
  in logged review history would reuse the metric code unchanged.

These evaluations validate that the scoring **math is correct and internally
consistent against the engine**, not the real-world accuracy of the models on
human memory. See `mcat/ai_eval/model_validation_report.md` and
`mcat/ai_eval/experiments_report.md` for the full protocols and numbers, and
`mcat/bench/results/bench_50000.md` for the engine performance of these scores at
50k cards (topic mastery ≈ 0.37 s, exam readiness ≈ 0.35 s per full recompute).
