# MCAT AI — What I built, why, and what I skipped

A short, honest note on the AI in this MCAT study app. Every claim here is
backed by a command you can run yourself (see `mcat/ai_eval/walkthrough.sh` or
the "Reproduce" line at the bottom).

## What I built (and why)

Five AI features, each of which has to **beat the exact no-AI path the app
falls back to** — otherwise it doesn't earn its place. All five run through one
backend module (`rslib/src/mcat/ai/`) and one hosted proxy, so there is a single
place that controls provenance, grounding, and the on/off switch.

| PRD | Feature                             | Why AI (vs the no-AI baseline it replaces)                                                                                                                                                  |
| --- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 9.4 | **Card-quality gate**               | A learned rubric catches vague / trivial / circular / unsupported / duplicate cards that a length+keyword rule cannot. This is the gate that decides what a student is even allowed to see. |
| 9.3 | **Source-grounded generation**      | Produces cards across a deliberate difficulty range (recall → exam → stretch) grounded in a named source, instead of a flat template extractor.                                             |
| 9.5 | **Missed-question explanations**    | Explains _why the right answer is right and your choice was wrong_, cited to the source, instead of one generic static hint. Display-only.                                                  |
| 9.6 | **Study planner**                   | Turns measured app evidence into a few concrete, timed, cited next steps, instead of a single deterministic "weakest topic" nudge.                                                          |
| 9.8 | **Performance-question generation** | Writes novel application questions that transfer, instead of re-showing the original card stem (which just re-tests recall).                                                                |

## The safety rules I designed around

1. **Every AI output traces back to a named source.** Generation _requires_ a
   registered source (`mcat_register_ai_source`); it cannot run on thin air. Each
   accepted card carries a human-readable `Source: <name> — <section>` line on
   its back **and** a machine-readable `ai-source::<source_id>` tag that resolves
   to the exact registered excerpt. Explanations carry a `source_citation`. The
   9.4 checker has an explicit `source_supported` category. (See
   `rslib/src/mcat/ai/generate.rs` and `proto/anki/mcat.proto`.)
2. **AI never feeds the score.** Readiness / Memory / Performance are computed
   deterministically from review history in `rslib/src/mcat/scores.rs`. AI
   output is content and coaching only. With AI switched off the app still scores
   (just without the AI content) — verifiable with `just mcat-ai-verify-scoring-off`.
3. **A pre-registered acceptance cutoff.** The checker cutoff is **0.70**, set
   _before_ testing (`DEFAULT_CHECKER_CUTOFF` in `rslib/src/mcat/ai/mod.rs`). Only
   cards that clear the gate at 0.70 become eligible for review.
4. **Graceful degradation, always.** If AI is disabled or unavailable, each
   feature falls back to its real baseline (naive checker, deterministic
   recommender, generic hint, verbatim reuse). Nothing breaks; the score is
   unaffected.
5. **Zero user input for the key.** The app ships with a built-in hosted proxy
   default, so a student never types an API key. The proxy holds the real key
   server-side; the app carries only a low-privilege, revocable app token.

## The evaluation I ran before any student sees a card

Deterministic, offline (mock provider — no network/key) so it is reproducible in
CI. Full detail in `mcat/ai_eval/report.md`.

- **AI-on vs AI-off:** all **5/5** features beat their no-AI baseline by a
  pre-registered margin.
- **Pre-student quality gate on a held-out set** (50 labelled candidate cards:
  20 good, 30 deliberately bad), scored at the 0.70 cutoff, compared head-to-head
  against the two simpler methods an AI-free system would use:

  | Method                 | Accuracy | Wrong-answer rate (bad cards shown) |
  | ---------------------- | -------- | ----------------------------------- |
  | **AI quality gate**    | **100%** | **0%**                              |
  | Keyword search         | 86%      | 24%                                 |
  | Vector search (TF-IDF) | 84%      | 23%                                 |

  The AI gate admits **0** bad cards; keyword/vector search cannot detect
  triviality, circularity, vagueness, source-vocabulary factual errors, or
  train/test duplicates, so they leak those to students.

## What I skipped (and why)

- **Live, at-scale LLM-as-judge faithfulness scoring.** The offline eval
  validates the _system_ advantage (pipeline, gating, grounding, degradation)
  deterministically. Measuring free-text faithfulness magnitudes at scale needs a
  live key and an LLM judge; I wired the same metrics to run live
  (`MCAT_AI_MOCK=0`) but did not run a large paid sweep.
- **A real semantic vector index.** The vector baseline is TF-IDF cosine over the
  source, which is enough to show the gate beats naive retrieval. A production
  embedding index (e.g. for large-corpus retrieval) is future work, not needed
  for the gate comparison.
- **Fine-tuning / a custom model.** Off-the-shelf `gpt-4o-mini` through the proxy
  was sufficient; the rubric, grounding, and gate live in our code, not the model.
- **On-device / mobile AI.** The mobile app intentionally surfaces **no AI** — it
  focuses on sync + deterministic scores. AI is a desktop authoring/coaching tool.
- **Model fallback / multi-provider routing.** One proxy, one model. The config
  layer supports overrides, but I did not build automatic provider failover.

## Reproduce

```bash
just mcat-ai-eval                  # offline: AI-on vs AI-off + held-out gate vs keyword/vector
just mcat-ai-verify-scoring-off    # offline: app still scores with AI OFF (+ give-up rule)
just mcat-ai-verify-live           # live: zero-config proxy + real checker + source-grounded gen
bash mcat/ai_eval/walkthrough.sh   # all of the above, narrated per requirement
```
