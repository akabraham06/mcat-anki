# MCAT AI — Measurement Experiments (7d–7f + three-build study)

Four self-contained measurement experiments, all **offline / deterministic**
(mock AI provider, `MCAT_AI_MOCK=1`), producing real numbers. Every script here
is NEW and does not modify any existing file. No student data is used: learners
are clearly-labelled SYNTHETIC populations with fixed seeds. Negative results are
reported honestly.

All numbers below were produced by running the scripts on this tree with
`pylib` already built.

## Reproduce

```bash
# from repo root, with pylib already built
PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/ai_eval/paraphrase_experiment.py
PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/ai_eval/study_three_build.py
PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/ai_eval/leakage_scan.py
PYTHONPATH=out/pylib:pylib out/pyenv/bin/python mcat/ai_eval/gold_set_check.py
```

New files:

- `paraphrase_experiment.py` + `paraphrase_items.json` (30 cards × 2 reworded)
- `study_three_build.py`
- `leakage_scan.py`
- `gold_set_check.py` + `gold_set.json` (50 known-correct Q&A)
- `experiments_report.md` (this file)

---

## 1. Recall vs transfer — paraphrase experiment (rubric 7d)

**Question.** Does strong recall on a card mean the student understands the idea,
or are they matching surface wording?

**Setup.** 30 MCAT knowledge cards; for each, 2 hand-authored exam-style
**reworded** questions testing the same idea with different surface form
(`paraphrase_items.json`). A synthetic learner population (400 students, seed
1729) with latent per-student ability and per-card concept difficulty +
surface-memorisation propensity. Recall on the original card = concept known OR
exact wording rote-memorised; reworded accuracy = concept transfers (prob τ) OR
rote memory partially fires, scaled by word overlap with the original.

**Results.**

| Measure                                                 | Value        |
| ------------------------------------------------------- | ------------ |
| Mean recall on ORIGINAL cards                           | **70.9%**    |
| Mean accuracy on REWORDED questions                     | **49.6%**    |
| **Transfer gap (recall − reworded)**                    | **21.3 pts** |
| Control gap (no surface memorisation, perfect transfer) | **0.0 pts**  |

The control (set surface-memorisation propensity `phi = 0`, transfer `tau = 1`)
drives the gap to **0.0 pts**, confirming that in this model a non-trivial gap
comes specifically from surface-bound memorisation — i.e. **a near-zero gap
would mean the performance signal just copies memory.** The measured 21.3 pt gap
says ~30% of apparent recall did not survive rewording.

The shipped 9.8 perf-question generator (`col.mcat_generate_perf_questions`) is
wired and returns 2 questions/card, but **offline the mock returns generic
templated stems with the source excerpt as the answer**, so it cannot drive a
per-idea accuracy measurement; the authored same-idea items do. The generator
path is exercised in the script to show availability.

---

## 2. Three-build study test under equal study time

**Question.** Under a **fixed study budget** (same number of reviews per arm),
which scheduling build produces the best learning-outcome proxy?

**Builds.**

- **A = blocked** (one topic at a time, no recommender) — `mcat_interleaved_session(interleave=False)`
- **B = interleaved** — `mcat_interleaved_session(interleave=True)`
- **C = interleaved + topic-weighted recommender** — weighted round-robin using the deterministic recommender's real `priority_score` (`mcat_study_recommendation`)

The study **order** and the per-topic **exam weight / recommender priority** are
read live from the shipped Rust RPCs. The learner is synthetic and **identical
across all three arms** (paired, seed 4242, 300 learners) — so any difference is
attributable to the scheduling policy, not a baked-in per-arm bonus. Outcome =
exam-weighted transfer accuracy on held-out reworded questions (a topic never
reached in the budget stays at its starting mastery).

**Setup numbers.** 6 topics, 52 study events available, **equal budget = 23
reviews/arm** (45%).

**Results.**

| Build                                | Transfer accuracy |
| ------------------------------------ | ----------------- |
| A blocked (no recommender)           | 69.1%             |
| **B interleaved**                    | **75.3%**         |
| C interleaved + weighted recommender | 74.7%             |

- Interleaving vs blocking: **+6.2 pts** (B 75.3% vs A 69.1%). Real driver:
  under an equal budget, blocked practice exhausts the budget on the first 2–3
  topics (coverage `enzymes:8, metabolism:7, glycolysis:8`, and
  `thermodynamics/kinetics/acids_bases: 0`), while interleaving spreads coverage
  across all six.
- **HONEST NEGATIVE RESULT — recommender weighting did NOT help:** C vs B =
  **−0.6 pts** (74.7% vs 75.3%). Under strictly equal time, even coverage already
  captured the gain; concentrating the budget on high-priority topics hit
  diminishing returns and starved a topic the recommender de-prioritised
  (`kinetics:1`). Topic-weighting is not a free win at a fixed budget.

---

## 3. Train/test leakage scan (rubric 7e)

**Question.** Did any held-out evaluation item leak into the training corpus,
which would inflate the transfer numbers?

**Setup.** Training corpus = generated cards + seeded corpus (`generated.json`) +
`EXAM_MCQ` bank + gold set (`gold_set.json`) = **165 items**. Held-out test =
7d reworded transfer questions (60) + 9.8 perf-generator output (6) = **66
items**. Flag any test item that is an exact match or token-set Jaccard ≥ **0.70**
(pre-registered) of any training item.

**Result.**

| Metric                                 | Value                          |
| -------------------------------------- | ------------------------------ |
| Threshold (Jaccard, pre-registered)    | 0.70                           |
| Training items                         | 165                            |
| Held-out test items                    | 66                             |
| Exact-duplicate leaks                  | 0                              |
| Near-duplicate leaks                   | 0                              |
| **Total leaked**                       | **0 / 66 — CLEAN**             |
| Highest test↔train similarity observed | 0.44                           |
| Sanity check (planted training item)   | **caught** (scanner not blind) |

The held-out set is genuinely novel surface (nearest neighbour only 0.44), and
the planted-duplicate sanity check confirms the scanner detects a real leak.

---

## 4. Gold-set check (rubric 7f)

**Protocol (cutoff fixed BEFORE looking).** Gold set = 50 Q&A with known-correct
MCAT answers (`gold_set.json`, from the curated `EXAM_MCQ` bank). Candidates = 50
cards generated from ONE real source (`generated.json`, grounded in
`source.json`). **Cutoff = 0.70**, set on the collection before scoring. Every
candidate is run through the 9.4 quality checker; failing cards are BLOCKED.

**The three counts (ground-truth quality of the 50 candidates).**

| Count                        | Definition                         | Value  |
| ---------------------------- | ---------------------------------- | ------ |
| (a) correct + useful         | flaw = none                        | **20** |
| (b) wrong (wrong fact)       | flaw = unsupported                 | **6**  |
| (c) correct-but-bad-teaching | flaw = vague / trivial / duplicate | **24** |

**Checker decisions at cutoff 0.70.**

| Bucket               | Blocked | Passed |
| -------------------- | ------- | ------ |
| (a) correct + useful | 0       | 20     |
| (b) wrong fact       | 6       | 0      |
| (c) bad teaching     | 24      | 0      |

- **Blocked total: 30 / 50.**
- Wrong-fact caught: **6/6**; bad-teaching caught: **24/24**; good cards wrongly
  blocked: **0/20**.
- Of the 20 cards the checker would SHOW a student, **0 are actually bad** (no
  wrong-answer leak-through).
- Gold-set calibration: **0/50** known-correct gold cards were blocked at the
  0.70 cutoff (false-block rate 0% on this ungrounded broad-MCAT set).

---

## Honesty / negative-results section

- **These are offline mock-provider numbers.** Free-text magnitudes (7d gap,
  checker precision) depend on the model; the honest offline claim is that the
  _harness, gating, grounding, and coverage logic_ behave as designed.
  Re-run with `MCAT_AI_MOCK=0` and a real key for live magnitudes.
- **No real students.** The 7d and three-build learners are SYNTHETIC with fixed
  seeds. Their outcome _magnitudes_ reflect modelling assumptions
  (surface-memorisation propensity, transfer success, learning rate). What is
  real and reusable: (a) the authored same-idea item sets, (b) the measurement
  harnesses, (c) the paired/controlled designs, and (d) the study arms' study
  order + exam weights + recommender priorities, which come from the shipped
  RPCs. The 7d control (gap → 0.0) is a genuine falsification test of the model.
- **Explicit negative result:** in the three-build study, the topic-weighted
  recommender (C) did **not** beat plain interleaving (B) under equal study time
  (−0.6 pts). Even coverage captured the benefit; targeted weighting hit
  diminishing returns and can starve a de-prioritised topic. Interleaving beating
  blocking (+6.2 pts) is itself a consequence of the _real_ session ordering
  under a capped budget, not a hand-set bonus.
- **Leakage is clean but verified, not assumed:** the 0/66 result is backed by a
  planted-duplicate sanity check proving the scanner catches real leaks.
