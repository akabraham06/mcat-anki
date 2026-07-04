# MCAT AI — “AI-on vs AI-off” Showcase Evaluation

Deterministic evaluation via the offline mock provider (no network/key). Each Phase-2 AI feature is compared head-to-head against the exact no-AI path the app falls back to, so the AI features have to *earn* their place. Offline results validate the system advantage (pipeline, quality-gating, source-grounding, graceful degradation); free-text magnitudes are best confirmed with a live key using these same metrics.

## Summary — does AI beat no-AI?

| PRD | Feature | Metric | Without AI | With AI | Δ | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| 9.4 | Card quality checker | decision accuracy on gold set | 73% | 99% | +26 pts | ✅ AI wins |
| 9.3 | Source-grounded generation | distinct difficulty tiers covered (recall/mcat/stretch) | 1 tiers | 3 tiers | +2 tiers | ✅ AI wins |
| 9.6 | Study planner | actionable, evidence-cited plan steps | 1 steps | 3 steps | +2 steps | ✅ AI wins |
| 9.5 | Missed-question explanations | grounded explanation components (rubric /5) | 1/5 | 5/5 | +4/5 | ✅ AI wins |
| 9.8 | Perf-question generation | share of questions that transfer (novel surface, no leakage) | 0% | 100% | +100 pts | ✅ AI wins |

**5/5 AI features beat their no-AI baseline by the pre-registered margin.**

> Baselines are the real fallbacks, not straw men: the checker's naive length/keyword rule, the deterministic best-next-topic recommender, a generic review hint, and verbatim card reuse. When AI is disabled or unavailable, the app degrades to exactly these baselines — nothing breaks, and none of the AI output ever feeds the readiness score.

## Pre-student quality gate (runs before any card is shown)

Before a generated card can reach a student it must clear the AI quality gate at the checker cutoff **0.70** (set before testing, `DEFAULT_CHECKER_CUTOFF`). We evaluate that gate on a **held-out set of 50 labelled candidate cards** (20 genuinely good, 30 deliberately bad: wrong/vague/trivial/unsupported/duplicate), all generated from one real source. The gate is compared head-to-head against the two simpler methods an AI-free system would use — **keyword search** and **vector search (TF-IDF cosine)** over the same source — each shown at its own accuracy-maximising operating point (the retrieval baselines' best case).

| Method | Accuracy | Wrong-answer rate (bad cards shown) | Cards shown | Bad shown | Operating point |
| --- | --- | --- | --- | --- | --- |
| AI quality gate | 100% | 0% (0/20) | 20 | 0 | cutoff 0.70 |
| Keyword search | 86% | 24% (6/25) | 25 | 6 | score ≥ 0.44 |
| Vector search (TF-IDF) | 84% | 23% (5/22) | 22 | 5 | score ≥ 0.56 |

**✅ gate beats both simpler methods.** The AI gate scores **100%** accuracy and lets through **0%** bad cards; keyword/vector search cannot see triviality/circularity, vagueness, source-vocabulary factual errors, or train/test duplicates, so they wave those through to students.

> This is a *gate*, not a report card: only cards the AI gate accepts at the 0.70 cutoff become eligible for review, and none of the AI output ever feeds the readiness score.

## Per-feature detail

### 9.4 — Card quality checker

- **Metric:** decision accuracy on gold set
- **Without AI (naive length/keyword rule):** 73%
- **With AI:** 99%  (+26 pts, need ≥ 10%)
- **Verdict:** PASS
- Gold set: 50 known-correct human cards + 50 labelled candidates.
- Wrong/unsupported caught: 6; vague/trivial caught: 18; duplicates flagged: 6.

### 9.3 — Source-grounded generation

- **Metric:** distinct difficulty tiers covered (recall/mcat/stretch)
- **Without AI (naive template extractor (flat difficulty)):** 1 tiers
- **With AI:** 3 tiers  (+2 tiers, need ≥ 1.0 tiers)
- **Verdict:** PASS
- AI difficulty spread (your 'difficulty should vary greatly' requirement): mcat:3, recall:3, stretch:3.
- Quality gate (offline surface check): AI 9/9 vs naive 9/9 passed — both clear the surface gate offline, so the honest offline differentiator is the deliberate difficulty range; the *factual-grounding* quality gap needs a live key to measure.
- Accepted AI cards are tagged difficulty::<tier> so decks span basic recall → exam-level → harder-than-MCAT stretch.

### 9.6 — Study planner

- **Metric:** actionable, evidence-cited plan steps
- **Without AI (deterministic recommender):** 1 steps
- **With AI:** 3 steps  (+2 steps, need ≥ 1.0 steps)
- **Verdict:** PASS
- AI plan: 3 timed steps, 3 citing measured app evidence; summary present: True.
- Targeting parity (AI focuses the recommender's weak topic 'Enzymes and Kinetics'): True.
- Degrades to the exact deterministic recommender when AI is off (used_fallback path); the plan never feeds the readiness score.

### 9.5 — Missed-question explanations

- **Metric:** grounded explanation components (rubric /5)
- **Without AI (generic static hint):** 1/5
- **With AI:** 5/5  (+4/5, need ≥ 2.0/5)
- **Verdict:** PASS
- Rubric: why-correct, why-your-choice-wrong, faithfulness to the chosen answer, source citation, concrete review action.
- Explanations are display-only and never used as scoring evidence (PRD safety); the reviewer still works with AI off (you get the generic nudge).
- Live faithfulness is best measured with a real key + LLM-as-judge; offline checks structural grounding.

### 9.8 — Perf-question generation

- **Metric:** share of questions that transfer (novel surface, no leakage)
- **Without AI (verbatim card reuse):** 0%
- **With AI:** 100%  (+100 pts, need ≥ 50%)
- **Verdict:** PASS
- AI produced 2 application questions; 2 had novel surface + passed the leakage/near-duplicate check.
- Verbatim reuse leaks the original stem (0% transfer) — it re-tests recall, not application.

## Reproduce

```bash
just mcat-ai-eval          # offline, deterministic (mock provider)
```

For live numbers, configure a real key in the app (or env) and run with `MCAT_AI_MOCK=0`; the same metrics apply.
