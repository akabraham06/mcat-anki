# MCAT card-generation pipeline

Turns openly-licensed source content into custom, difficulty-tiered MCAT
flashcard decks, guided by the embedded MCAT content outline (the taxonomy) and
spanning a **wide difficulty range**.

## What's here

| Path                          | Purpose                                                                           |
| ----------------------------- | --------------------------------------------------------------------------------- |
| `build_deck.py`               | **The dynamic card-generation pipeline** (this deliverable).                      |
| `sources/openstax/`           | Staged OpenStax corpus (56 sources, CC BY-NC-SA 4.0) mapped to the taxonomy.      |
| `sources/register_sources.py` | Registers the corpus into a live collection.                                      |
| `content.py` / `gen_deck.py`  | The hand-authored starter deck (learning + exam + CARS).                          |
| `ai_eval/`                    | Offline evaluations: AI features, model validation, and measurement experiments.  |
| `bench/`                      | 50k-card engine benchmark (`run_bench.py`; deck cache in `.cache/`, git-ignored). |
| `tests/test_build_deck.py`    | Deterministic offline tests for the pipeline.                                     |
| `tests/crash_harness.py`      | Crash-safety + offline AI-off harness (`just mcat-crash-test`).                   |
| `tests/sync_conflict_test.py` | Sync same-card conflict merge simulation (`just mcat-sync-conflict`).             |
| `dist/`                       | Built `.apkg` output.                                                             |

## How it works

For each taxonomy topic (`rslib/src/mcat/taxonomy.json` — the authoritative
"MCAT outline"), the pipeline:

1. pulls the topic's registered OpenStax excerpt(s),
2. calls the existing Phase-2 AI generator (`GenerateCards`) **once per
   difficulty tier**, feeding the taxonomy topic into the prompt so questions
   match MCAT-style scope per topic rather than generic trivia,
3. runs every candidate through the existing 9.4 quality checker (inside
   `GenerateCards`: source-grounding, duplicate, taxonomy-tag, and the model's
   factual / vagueness / triviality categories) — nothing is auto-added,
4. accepts the passing cards (`AcceptGeneratedCards`) into a deck, tagging each
   with its `mcat::section::topic` tag **and** a `difficulty::<tier>` tag.

It reuses the existing RPCs (and their Python wrappers in
`pylib/anki/collection.py`) rather than a parallel path.

## Wide difficulty distribution

Every card is generated at, and tagged with, one of three tiers:

| Tier      | Tag                   | Meaning                                                                            |
| --------- | --------------------- | ---------------------------------------------------------------------------------- |
| `recall`  | `difficulty::recall`  | basic recall / definition                                                          |
| `mcat`    | `difficulty::mcat`    | exam-level application / reasoning (the standard MCAT band)                        |
| `stretch` | `difficulty::stretch` | **harder than the real MCAT** — multi-concept integration, edge cases, wider scope |

The per-topic target distribution is explicit and configurable — defaults to
`recall=4, mcat=4, stretch=2` (covering the middle band while still hitting both
ends). Override with `--recall/--mcat/--stretch` or `MCAT_DIST`. The requested
tier is authoritative: it steers the generation prompt (see `tier_guidance` in
`rslib/src/mcat/ai/generate.rs`) and labels every accepted card, so the deck
spans a measurable, filterable range.

## Running

```bash
# Offline sample deck — deterministic mock provider, no network/key:
just mcat-build-deck                       # -> mcat/dist/mcat_generated.apkg
just mcat-build-deck --dry-run             # plan only, write nothing
just mcat-build-deck --recall 6 --mcat 6 --stretch 3

# Deterministic offline pipeline tests:
just mcat-build-deck-test
```

## Evaluations, benchmarks & safety tests

Grounded, one-command proofs (all offline & deterministic; synthetic seeded
learners for outcomes, real formulas/engine calls — see each report's honesty
note):

```bash
just mcat-eval-all          # calibration + performance + paraphrase + study + leakage + gold-set
just mcat-bench             # 50k-card engine benchmark (p50/p95/worst)
just mcat-crash-test        # 20 mid-write SIGKILLs: zero corruption + AI-off still scores
just mcat-sync-conflict     # same-card conflict merge rule (chunks.rs) simulation
```

Reports live in `ai_eval/` (`report.md`, `model_validation_report.md`,
`experiments_report.md`) and `bench/results/`; see also `docs/model-descriptions.md`,
`docs/brainlift.md`, and `docs/sync-conflict-rule.md` at the repo root.

By default the build runs in a **private temporary collection** and exports an
`.apkg`, so it never opens the live SQLite database and is safe to run with the
desktop app open or closed. Pass `--collection PATH` (run with the **app
closed** — single-writer SQLite) to write into a real collection instead; that
mode is made idempotent by first removing this pipeline's previously generated
notes. The mock provider is deterministic, so re-running reproduces the same
deck without accumulating duplicates.

## Live vs. offline generation

- **Offline (default in tooling):** with `MCAT_AI_MOCK=1` the deterministic mock
  AI client produces tiered, source-grounded cards with no network and no key.
  This validates the whole pipeline and produces a sample deck. The mock text is
  intentionally simple filler — real card quality comes from a live model.
- **Live:** point the AI config at a provider with a **valid key** (AI settings,
  or `OPENAI_API_KEY` / `MCAT_AI_*` env vars) and unset `MCAT_AI_MOCK`. **Live
  generation is currently pending a valid key** — the configured OpenAI key was
  returning `401` at build time. When the key is invalid/absent, generation
  reports `ai_available=false` with a reason and the pipeline degrades
  gracefully (clear message, no crash, exit code 2) instead of producing cards.

## Sources & licensing

All grounding content is **OpenStax (CC BY-NC-SA 4.0)** — attribution,
NonCommercial and ShareAlike apply, and each source carries its own attribution
string (embedded in the grounding excerpt). See `sources/openstax/README.md` for
full provenance. Any additional source **must be openly licensed** with recorded
provenance/license.

### Khan Academy is NOT used

Khan Academy content is deliberately excluded: their Terms of Service prohibit
scraping, so it is never fetched or used as a source here. The pipeline relies
solely on the staged OpenStax corpus. The four **CARS** taxonomy topics have no
factual textbook basis (they are reading-reasoning skills), so no OpenStax
source maps to them and the pipeline skips them — CARS practice is served by the
hand-authored passages in `content.py` instead.
