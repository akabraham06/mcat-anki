set windows-shell := ["pwsh", "-NoLogo", "-NoProfileLoadTime", "-Command"]

mod release

# Show available commands
default:
    @just --list

# Build the project
build:
    {{ ninja }} pylib qt

# Build and run Anki in development mode
run *args:
    {{ run_script }} {{ args }}

# Build and run Anki in optimized (release) mode
run-optimized *args:
    {{ if os() == "windows" { "$env:RELEASE='1'; .\\run.bat" } else { "RELEASE=1 ./run" } }} {{ args }}

# Watch web sources and rebuild/reload Anki's web stack on change (macOS/Linux)
web-watch:
    ./tools/web-watch

# Rebuild and reload Anki's web stack without restarting (macOS/Linux)
rebuild-web:
    ./tools/rebuild-web

# Build wheels (needed for some platforms)
wheels:
    {{ ninja }} wheels

# Build a packaged desktop installer for the current platform
# (.dmg on macOS, .msi on Windows, .tar.zst on Linux). Output in out/installer/dist.
installer:
    {{ ninja }} installer:package

# Run the MCAT "AI-on vs AI-off" showcase evaluation across all Phase-2 AI
# features (9.3 generation, 9.4 checker, 9.5 explanations, 9.6 planner,
# 9.8 perf-gen). Offline & deterministic (mock provider; no network/key).
# Writes mcat/ai_eval/report.md and fails if any feature does not beat its
# no-AI baseline by the pre-registered margin.
mcat-ai-eval:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:MCAT_AI_MOCK='1'; $env:PYTHONPATH='out\\pylib'" } else { "MCAT_AI_MOCK=1 PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/ai_eval/run_eval.py

# Verify the app still produces MCAT scores with AI switched OFF: deterministic
# memory/section scores are computed from review history and the readiness score
# follows the written give-up rule, with no AI involved (offline; no network/key).
mcat-ai-verify-scoring-off:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:PYTHONPATH='out\\pylib'" } else { "PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/ai_eval/verify_scoring_ai_off.py

# Zero-config LIVE AI smoke check: with a clean env (no key), the app resolves the
# built-in hosted proxy, reports AI available, and returns a real 9.4 checker
# judgement + 9.3 source-grounded generation (every card names its source).
# Requires network and spends a small amount of the configured proxy's quota.
mcat-ai-verify-live:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:PYTHONPATH='out\\pylib'" } else { "PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/ai_eval/verify_live_ai.py

# Build custom, difficulty-tiered MCAT decks from the staged OpenStax corpus via
# the AI generate + quality-check flow. Runs offline against the deterministic
# mock provider (no network/key) and writes mcat/dist/mcat_generated.apkg. Pass
# extra args through, e.g. `just mcat-build-deck --dry-run` or
# `just mcat-build-deck --recall 6 --mcat 6 --stretch 3`.
mcat-build-deck *args:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:MCAT_AI_MOCK='1'; $env:PYTHONPATH='out\\pylib'" } else { "MCAT_AI_MOCK=1 PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/build_deck.py {{ args }}

# Run the deterministic offline tests for the MCAT card-generation pipeline
# (difficulty tiering/tagging + deck assembly; mock provider, no network/key).
mcat-build-deck-test:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:MCAT_AI_MOCK='1'; $env:PYTHONPATH='out\\pylib'" } else { "MCAT_AI_MOCK=1 PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/tests/test_build_deck.py

# One-command performance benchmark on the shared 50,000-card MCAT deck (7h):
# times the core engine actions (search, next/answer/undo, topic mastery, exam
# readiness, recommender) and reports p50/p95/worst — never a single number.
# Generates + caches the deck on first run to mcat/bench/.cache (git-ignored).
mcat-bench:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:PYTHONPATH='out\\pylib'" } else { "PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/bench/run_bench.py

# Crash-safety + offline AI-off tests (7g): SIGKILLs a review worker mid-write 20
# times and asserts zero SQLite corruption and no lost reviews after every kill,
# then confirms the app still scores deterministically with AI disabled.
mcat-crash-test:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:PYTHONPATH='out\\pylib'" } else { "PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/tests/crash_harness.py

# Sync same-card conflict test (7b): builds two collections from a shared base,
# reviews distinct cards in each (asserts the union keeps all reviews once) and
# the SAME card in both (asserts later-mtime wins), faithfully applying the merge
# rule in rslib/src/sync/collection/chunks.rs. Deterministic; no network.
mcat-sync-conflict:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:PYTHONPATH='out\\pylib'" } else { "PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/tests/sync_conflict_test.py

# Model-validation eval #1: calibration of the FSRS memory model (Brier / log
# loss / ECE + reliability diagram) on seeded synthetic recall data, cross-checked
# against the live engine. Offline & deterministic. Writes calibration_curve.svg.
mcat-eval-calibration:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:PYTHONPATH='out\\pylib'" } else { "PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/ai_eval/memory_calibration.py

# Model-validation eval #2: held-out accuracy of the performance model on the
# real EXAM_MCQ bank vs a majority-class baseline (seeded synthetic outcomes,
# real scheduler/engine). Offline & deterministic.
mcat-eval-performance:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:PYTHONPATH='out\\pylib'" } else { "PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/ai_eval/performance_holdout.py

# Measurement experiment 7d: recall-vs-transfer (paraphrase) gap on 30 authored
# same-idea reworded item pairs over a seeded synthetic learner, with a control
# that collapses the gap to ~0. Offline (mock provider), deterministic.
mcat-eval-paraphrase:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:MCAT_AI_MOCK='1'; $env:PYTHONPATH='out\\pylib'" } else { "MCAT_AI_MOCK=1 PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/ai_eval/paraphrase_experiment.py

# Measurement experiment: three-build study test under equal study time (blocked
# vs interleaved vs interleaved+recommender). Study order/exam weights come from
# the real Rust RPCs; reports the honest negative recommender result. Offline.
mcat-eval-study:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:MCAT_AI_MOCK='1'; $env:PYTHONPATH='out\\pylib'" } else { "MCAT_AI_MOCK=1 PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/ai_eval/study_three_build.py

# Measurement experiment 7e: train/test leakage scan — flags any held-out eval
# item that duplicates (exact or Jaccard >= 0.70) a training item, with a planted
# sanity check proving the scanner is not blind. Offline (mock provider).
mcat-eval-leakage:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:MCAT_AI_MOCK='1'; $env:PYTHONPATH='out\\pylib'" } else { "MCAT_AI_MOCK=1 PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/ai_eval/leakage_scan.py

# Measurement experiment 7f: gold-set check of the 9.4 quality checker at a
# pre-registered 0.70 cutoff — three ground-truth quality counts + block/pass
# breakdown + false-block calibration. Offline (mock provider), deterministic.
mcat-eval-goldset:
    {{ ninja }} pylib
    {{ if os() == "windows" { "$env:MCAT_AI_MOCK='1'; $env:PYTHONPATH='out\\pylib'" } else { "MCAT_AI_MOCK=1 PYTHONPATH=out/pylib" } }} {{ uv }} run python mcat/ai_eval/gold_set_check.py

# Convenience: run the whole MCAT model-validation + measurement eval suite
# (calibration, performance held-out, paraphrase, three-build study, leakage,
# gold-set). Each is offline & deterministic; see mcat/ai_eval/*.md for write-ups.
mcat-eval-all: mcat-eval-calibration mcat-eval-performance mcat-eval-paraphrase mcat-eval-study mcat-eval-leakage mcat-eval-goldset

# Build and run all checks (lint + test) - lets ninja handle dependencies
check:
    {{ ninja }} pylib qt check

# Run all tests (Rust, Python, TypeScript). Pass --coverage to enforce coverage, and --html to include HTML reports.
[arg("coverage", long="coverage", value="--coverage")]
[arg("html", long="html", value="--html")]
test coverage='' html='':
    just {{ if coverage == "--coverage" { "coverage " + html } else { "_test" } }}

# Run coverage for all test stacks. Pass --html to also generate HTML reports.
[arg("html", long="html", value="--html")]
coverage html='':
    just _coverage-rust {{ html }}
    just _coverage-py {{ html }}
    just _coverage-ts {{ html }}

# Run Rust tests. Pass --coverage to enforce Rust coverage, and --html to include an HTML report.
[arg("coverage", long="coverage", value="--coverage")]
[arg("html", long="html", value="--html")]
test-rust coverage='' html='':
    just {{ if coverage == "--coverage" { "_coverage-rust " + html } else { "_test-rust" } }}

# Run Python tests (pylib + qt). Pass --coverage to enforce coverage, and --html to include HTML reports.
[arg("coverage", long="coverage", value="--coverage")]
[arg("html", long="html", value="--html")]
test-py coverage='' html='':
    just {{ if coverage == "--coverage" { "_coverage-py " + html } else { "_test-py" } }}

# Run TypeScript/Svelte Vitest tests. Pass --coverage to enforce coverage, and --html to include an HTML report.
[arg("coverage", long="coverage", value="--coverage")]
[arg("html", long="html", value="--html")]
test-ts coverage='' html='':
    just {{ if coverage == "--coverage" { "_coverage-ts " + html } else { "_test-ts" } }}

# Run Playwright end-to-end tests. Pass --ui to open the interactive UI.
[arg("ui", long="ui", value="--ui")]
test-e2e ui='': _install-playwright-browsers
    {{ ninja }} pyenv ts:generated pylib qt
    {{ playwright_env }} {{ yarn }} test:e2e {{ ui }}

[private]
_test:
    {{ ninja }} check:rust_test check:pytest check:vitest

[private]
_test-rust:
    {{ ninja }} check:rust_test

[private]
_test-py:
    {{ ninja }} check:pytest

[private]
_test-ts:
    {{ ninja }} check:vitest

[private]
_coverage-rust html='':
    {{ if os_family() == "windows" { "tools\\coverage\\coverage-rust" } else { "tools/coverage/coverage-rust" } }} {{ html }}

[private]
_coverage-py html='':
    {{ ninja }} pylib qt
    just _coverage-py-pylib {{ html }}
    just _coverage-py-qt {{ html }}

[private]
_coverage-py-pylib html='':
    {{ if os_family() == "windows" { "tools\\coverage\\coverage-py" } else { "tools/coverage/coverage-py" } }} pylib {{ html }}

[private]
_coverage-py-qt html='':
    {{ if os_family() == "windows" { "tools\\coverage\\coverage-py" } else { "tools/coverage/coverage-py" } }} qt {{ html }}

[private]
_coverage-ts html='':
    {{ ninja }} node_modules ts:generated
    {{ if os_family() == "windows" { "tools\\coverage\\coverage-ts" } else { "tools/coverage/coverage-ts" } }} {{ html }}

[private]
_install-playwright-browsers:
    {{ ninja }} node_modules
    {{ playwright_env }} {{ yarn }} playwright install chromium

# Check formatting (fast, no build needed)
fmt:
    {{ ninja }} check:format

# Fix formatting
fix-fmt:
    {{ ninja }} format

# Run linting and type checking (requires build outputs)
lint:
    {{ ninja }} \
        check:clippy \
        check:mypy \
        check:ruff \
        check:eslint \
        check:svelte \
        check:typescript

# Fix auto-fixable lint issues (ruff + eslint)
fix-lint:
    {{ ninja }} fix:ruff fix:eslint

# Run minilints (copyright, contributors, licenses)
minilints:
    {{ ninja }} check:minilints

# Fix minilints (update licenses.json)
fix-minilints:
    {{ ninja }} fix:minilints

# Sync translation files
ftl-sync:
    {{ ninja }} ftl-sync

# Deprecate translation strings
ftl-deprecate:
    {{ ninja }} ftl-deprecate

# Build documentation site
docs:
    {{ uv }} run --group docs sphinx-build -b html docs out/docs/html
    @echo "Docs built at out/docs/html/index.html"

# Build and serve documentation site
docs-serve:
    {{ uv }} run --group docs sphinx-autobuild docs out/docs/html --host 127.0.0.1 --port 8000

# Build Rust API docs
docs-rust:
    cargo doc --open

# Dispatch CI workflow on a given branch or tag
ci branch:
    gh workflow run ci.yml --ref {{ branch }}

# Run Complexipy in regression-only mode
complexipy-diff:
    {{ ninja }} check:complexipy-diff

# Remove build outputs from out/ (pass keep-env to keep node_modules/pyenv); macOS/Linux
clean *args:
    ./tools/clean {{ args }}

# Helpers to get the right commands for the platform

ninja := if os() == "windows" { "tools\\ninja" } else { "./ninja" }
run_script := if os() == "windows" { ".\\run.bat" } else { "./run" }
playwright_env := if os() == "windows" { "set PLAYWRIGHT_BROWSERS_PATH=out\\playwright-browsers&&" } else { "PLAYWRIGHT_BROWSERS_PATH=out/playwright-browsers" }
yarn := if os() == "windows" { "out\\extracted\\node\\yarn.cmd" } else { "out/extracted/node/bin/yarn" }
uv := env("UV_BINARY", if os() == "windows" { "out\\extracted\\uv\\uv" } else { "out/extracted/uv/uv" })
export UV_PROJECT_ENVIRONMENT := if os() == "windows" { "out\\pyenv" } else { "out/pyenv" }
