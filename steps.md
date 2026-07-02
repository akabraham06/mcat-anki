# MCAT Anki Mastery — Build Log (steps.md)

A concise, chronological log of every meaningful step taken while building
MCAT Anki Mastery on top of Anki. Each entry records **what** changed, **which
files** were touched, **why**, and **how it was verified**. This log doubles as
the rubric's required "files you touched / how hard a future merge would be"
note.

- Exam focus: **MCAT**
- Base: fork of Anki (`ankitects/anki`), branch `mcat-mastery`
- Phase 1 = no-AI MVP (shared Rust engine, real Rust change, three separate
  scores with honest abstention, timed reviews, desktop + iOS-Simulator apps).

Legend for merge-risk on upstream files: **low** = additive/new file,
**med** = small edit to an existing file, **high** = edit to a hot upstream file.

---

## Milestone A — Foundation

### A0. Workspace + branch + log (setup)

- **What:** Re-established the agent workspace root at `/Users/alan/anki`,
  created branch `mcat-mastery` off `main`, and added this `steps.md`.
- **Files:** `steps.md` (new).
- **Why:** The rubric requires a fork that builds from source with clear
  history; the working branch isolates all MCAT changes for an easy upstream
  diff.
- **Verified:** `git status` clean on `main` before branching; `git checkout -b
mcat-mastery` succeeded (`git branch --show-current` → `mcat-mastery`).
- **Toolchain note:** Desktop build was already confirmed working in a prior
  session (`just run` launched Anki 26.05). `just`, Rust (rustup 1.92.0 pinned
  via `rust-toolchain.toml`), and `n2` are installed. `cargo`/`rustup` live at
  `/opt/homebrew/opt/rustup/bin` and `~/.cargo/bin` (added to `~/.zshrc`); shell
  commands that invoke cargo export these onto `PATH` explicitly.
- **Merge risk:** low (new file only).

### A1. Topic-mastery protobuf service (proto)

- **What:** Added a new backend RPC that returns per-topic MCAT mastery stats.
  Mirrors Anki's existing service pattern: a collection service `McatService`
  with `GetTopicMastery(TopicMasteryRequest) -> TopicMasteryList`, plus an empty
  `BackendMcatService {}` so Anki auto-generates the backend-forwarding method.
- **Files:** `proto/anki/mcat.proto` (new); `rslib/proto/src/lib.rs`
  (`protobuf!(mcat, "mcat");`); `rslib/proto/python.rs` (`import anki.mcat_pb2`
  in the generated header). The proto file is auto-discovered by
  `rslib/proto/rust.rs`'s directory glob; the module list and Python import
  header are the two explicit lists that must be edited.
- **Why:** The engine change must be exposed to every layer (Rust, Python, TS,
  and later Swift) through the shared protobuf API so all apps call identical
  code. `TopicMastery` carries the three-score inputs (coverage, recall,
  timing) the dashboard needs, kept as separate fields (no blended number).
- **Verified:** `cargo check --workspace` regenerated the descriptors + service
  traits and compiled; `just test-py` rebuilt pylib and generated
  `mcat_pb2` + the `get_topic_mastery` binding automatically.
- **Merge risk:** low (new proto file; 2 one-line additions to generator lists).

### A2. Topic-mastery aggregation in the Rust engine (rust-query)

- **What:** Implemented `Collection::topic_mastery()` plus the
  `McatService for Collection` trait impl. It searches cards into scope, loads
  cards + revlog + note tags, and aggregates per MCAT topic tag
  (`mcat::section::topic`): cards total/seen/mastered, mean FSRS recall
  probability (via `FSRS::current_retrievability_seconds`), mean response time
  and overtime rate (from `revlog.taken_millis` vs a target), last-reviewed
  time, coverage %, and a weakness score. Includes distinct-card rollups.
- **Files:** `rslib/src/mcat/mod.rs` (new, logic + tests),
  `rslib/src/mcat/service.rs` (new, trait impl), `rslib/src/lib.rs`
  (`pub mod mcat;`).
- **Why:** This is the required real Rust change. Doing the aggregation in the
  core engine (not Python) means it is fast over large histories and runs
  unchanged on mobile through the FFI bridge — the "shared engine" guarantee.
  Scores are kept separate and coverage is reported honestly so the UI can
  abstain from a readiness verdict when coverage is low.
- **Verified:** compiles under `cargo check --workspace`; unit tests below pass.
- **Merge risk:** low (new module; single `mod` line in `lib.rs`).

### A3. Tests: Rust units + undo-safety + Python integration (rust-tests)

- **What:** 4 Rust unit tests in `rslib/src/mcat/mod.rs`
  (`counts_parsing_and_ignored_tags`, `coverage_after_review`,
  `timing_and_overtime`, `recall_and_mastery_from_memory_state`) plus an
  undo/no-corruption test (`query_is_safe_across_undo`) that runs the query,
  performs `col.undo()`, re-runs the query, and asserts `check_database()`
  reports no problems. Added `pylib/tests/test_mcat.py`, an end-to-end Python
  integration test through the protobuf boundary, and a `mcat_topic_mastery()`
  wrapper on `Collection`.
- **Files:** `rslib/src/mcat/mod.rs` (tests), `pylib/tests/test_mcat.py` (new),
  `pylib/anki/collection.py` (wrapper + `mcat_pb2` import).
- **Why:** Rubric requires proving correctness and that the engine change does
  not corrupt data or break undo.
- **Verified:** `cargo test --workspace mcat::` → 5 passed, 0 failed. Python:
  `pytest tests/test_mcat.py` → 1 passed against the freshly built pylib. The
  only failing tests in `just test-py` are the pre-existing
  `qt/tests/test_installer.py` cases (Briefcase cannot fetch the mac template
  offline) — unrelated to MCAT.
- **Merge risk:** low (new test file; small additive wrapper on `Collection`).

### A4. Clean-machine desktop installer (.dmg)

- **What:** Produced a packaged, installable macOS build so the app opens on a
  clean machine (Speedrun p.4 "An installer that runs on a clean machine";
  p.5 "A packaged desktop installer"; hard-cap at p.9 if either app doesn't run
  on a clean device). Added a `just installer` recipe.
- **Root cause of the earlier failure:** `qt/installer/mac-template` and
  `windows-template` are git submodules (`.gitmodules` →
  `ankitects/briefcase-macOS-app-template`, branch `anki`) that were never
  initialized, so Briefcase was handed a non-existent local path and fell back
  to trying to git-clone it ("Unable to clone application template"). The build
  graph already handles this: `build/configure/src/installer.rs` defines
  `installer:template:mac` (a `SyncSubmodule` action), `installer:build`, and
  `installer:package`. Running the packaged target initializes the submodule
  over the network and drives the whole pipeline.
- **Files:** `justfile` (new `installer` recipe wrapping
  `{{ ninja }} installer:package`). No source edits were needed — the tooling
  existed; it just had to be invoked with submodules available. (Submodules
  `qt/installer/mac-template` + `windows-template` are now checked out locally.)
- **How to build:** `just installer` → wheels are built, template submodules
  synced, Briefcase downloads the standalone Python + Qt runtime, and the app is
  packaged. Output: `out/installer/dist/anki-26.05-mac-apple.dmg` (~220 MB).
- **Verified (clean-machine open):**
    1. Mounted the `.dmg` → standard drag-to-`/Applications` layout with `Anki.app`.
    2. Copied `Anki.app` to a fresh `/tmp/anki-clean-test/` (not the source tree)
       and detached the image.
    3. `codesign --verify --deep --strict Anki.app` → OK (ad-hoc signed).
    4. Launched the copied app with a fresh base dir + unique
       `ANKI_SINGLE_INSTANCE_KEY`; log showed `Starting Anki 26.05...`,
       `aqt.mediasrv: Serving on http://127.0.0.1:62609`, and `Starting main
loop...` — full GUI startup, then quit cleanly.
    5. Confirmed the MCAT engine change shipped inside the bundle: `_rsbridge.so`
       (compiled Rust engine), `anki/mcat_pb2.pyc`, and `get_topic_mastery`
       present in `anki/_backend_generated.pyc`.
- **Not yet (later milestones):** code signing/notarization with a real Apple
  identity (Speedrun §13 bonus), Windows `.msi` / Linux `.tar.zst` on their host
  platforms, and the iOS build (Milestone D).
- **Merge risk:** low (one new `just` recipe; submodule checkouts only).

---

## Milestone B — MCAT study layer (taxonomy, scores, recommender, dashboard)

- **What & why:** Turned the raw per-topic aggregation from Milestone A into the
  product's core: an embedded MCAT taxonomy (the "coverage map"), three separate
  honest scores, a deterministic recommender, and a desktop dashboard.
- **Engine (Rust, `rslib/src/mcat/`):**
    - `taxonomy.json` + `taxonomy.rs`: the 4-section MCAT outline (27 topics) with
      per-topic exam weights + target answer times, `include_str!`-embedded so the
      same numbers drive desktop and mobile. Authoritative for coverage.
    - `snapshot.rs`: one pass over the collection producing every aggregate
      (per-topic recall from FSRS, perf accuracy from revlog, due counts, reviews
      today, streak). Perf cards are classified by the `MCATPerf` notetype.
    - `scores.rs`: `estimate()` (pure, unit-tested) maps ability→exam scale with an
      uncertainty band driven by coverage + evidence. Produces **Memory**,
      **Performance** and **Readiness** each with point + range + coverage +
      confidence + reasons + last-updated, plus a written-down **give-up rule**
      (no readiness score until ≥100 graded reviews and ≥50% coverage) and a
      per-section breakdown.
    - `recommender.rs`: deterministic best-next-topic = examWeight × weakness ×
      coverage-gap × due-ness, with a self-explanation and ranked candidates.
- **Proto:** extended `proto/anki/mcat.proto` with `GetExamReadiness`,
  `GetStudyRecommendation`, `GetTopicTargets` (+ messages). Wired in
  `rslib/src/mcat/service.rs`.
- **Deck data (`mcat/`):** `content.py` (33 tagged knowledge cards +
  61 exam-style questions across 26 topics) + `gen_deck.py` →
  `mcat/dist/mcat_starter.apkg`. Run: `PYTHONPATH=out/pylib python mcat/gen_deck.py`.
- **Dashboard (SvelteKit, `ts/routes/mcat/`):** `+page.ts` loads readiness +
  targets + mastery; `MCATDashboard.svelte` renders the three score cards (with
  range bars + abstention), coverage, recommender, section breakdown, transfer
  gaps, pacing, and a timed interleaved-session builder. Registered as a
  sveltekit page (`qt/aqt/mediasrv.py`) and exposed via the frontend allowlist.
- **Qt entry point:** `qt/aqt/mcat.py` dialog + Tools ▸ **MCAT Dashboard** menu
  action (`main.py`), registered in `qt/aqt/__init__.py`; loads the `mcat` page.
- **Merge risk:** low for new files; **med** for `mediasrv.py`, `main.py`,
  `__init__.py`, `webview.py`, `collection.py` (small additive edits).

## Milestone C — Bank, transfer gap, interleaving, XP

- **Performance bank:** the `MCATPerf` notetype + 61 exam-style questions (see
  Milestone B deck). Accuracy on these cards is the Performance score.
- **Transfer gap (`scores.rs`):** per topic, `memory_recall − performance_accuracy`
  — recall vs. application. Surfaced in the dashboard.
- **Interleaving (`interleaving.rs`):** `BuildInterleavedSession` RPC returns an
  ordered session, round-robin across topics (interleaved) or grouped (blocked)
  for the ablation; a logged toggle in the dashboard.
- **XP/streak (`scores.rs`):** derived from revlog (10 XP/review, levels, streak,
  badges), shown separately from the scores.
- **Tests:** `rslib/src/mcat/feature_tests.rs` (6 tests) covers estimate ranges,
  give-up abstention, recommender determinism, interleave-vs-blocked ordering,
  performance + transfer gap, and XP. All 11 mcat Rust tests pass.

## Milestone D — iOS companion (built with Xcode 16.4)

- **Environment:** full Xcode 16.4 installed and selected
  (`/Applications/Xcode-16.4.0.app`, iPhoneSimulator 18.5 SDK). Rust iOS targets
  `aarch64-apple-ios-sim` + `aarch64-apple-ios` installed.
- **C-FFI staticlib (`mobile/ankiffi/`):** `anki-ffi` crate (staticlib only —
  a cdylib crate-type forced a device-target link that failed on the missing
  compiler-rt builtin `___chkstk_darwin`; the static archive skips linking)
  over the engine — `anki_backend_open` / `anki_backend_command`
  (service+method+bytes → bytes) / `anki_free_buffer` / `anki_backend_close`,
  mirroring pylib's rsbridge. `include/ankiffi.h` C header. Builds standalone
  and its host roundtrip test passes (`cargo test -p anki-ffi`). Added to the
  workspace; depends on `tokio` with `io-util` so it links on its own for iOS.
- **XCFramework built:** `mobile/build_ios.sh` cross-compiled the engine for both
  iOS targets and produced `mobile/build/AnkiEngine.xcframework` (run with
  `CARGO_TARGET_DIR=/Users/alan/anki/target` so paths match the stable target dir).
- **Swift companion (`mobile/AnkiCompanion/`):** `AnkiBackend.swift` (C interop +
  typed SwiftProtobuf wrappers), `CollectionStore.swift` (opens engine +
  collection), `ContentView.swift` (SwiftUI three-score readiness view),
  `AnkiCompanionApp.swift`, and `gen_swift_proto.sh` (SwiftProtobuf codegen).
- **Swift protobuf types generated** → `mobile/AnkiCompanion/Generated/anki/*.pb.swift`
  via `gen_swift_proto.sh` (Homebrew `protoc` + `protoc-gen-swift`).
- **Xcode project generated** → `mobile/AnkiCompanion/AnkiCompanion.xcodeproj`
  via `xcodegen generate` from `project.yml`. The SwiftProtobuf SPM package
  resolves; the app target links the `AnkiEngine.xcframework`.
- **Merge risk:** low (all new files + one workspace-members line).

### Building/running the companion in the Simulator

Done on this machine (Xcode 16.4):

- Tooling installed: `xcodegen`, `swift-protobuf` (protoc-gen-swift), `xcodes`.
- iOS Rust targets added; `AnkiEngine.xcframework` built.
- Swift protobuf types generated (expose `Anki_Mcat_ExamReadiness`,
  `Anki_Backend_BackendInit`, `Anki_Collection_OpenCollectionRequest`, etc.).
- Service indices baked into `AnkiBackend.swift` (collection = 3, mcat = 41) via
  `patch_service_indices.sh`.
- Xcode project generated; SwiftProtobuf package resolves.

Notes / gotchas hit while running:

- Xcode 16 ships without a bundled iOS simulator **runtime** — it must be
  downloaded once (`xcodebuild -downloadPlatform iOS`, ~8.9 GB) before any iOS
  destination (even a build-only generic simulator) resolves. The download can
  reset partway on a flaky link; re-run until it completes (it resumes near the
  end). **Important:** the runtime version must match Xcode's SDK — for Xcode
  16.4 that is **iOS 18.5 (22F77)** (`xcodebuild -downloadPlatform iOS
-buildVersion 18.5`). An 18.6 (22G86) runtime is too new for Xcode 16.4 and
  hangs forever on first-boot data-migration; see the launch section below.
- `gen_swift_proto.sh` must generate **all** `proto/anki/*.proto` (backend.proto
  pulls in the whole service surface — links, sync, etc.); generating a subset
  leaves types like `Anki_Links_HelpPageLinkRequest` unresolved.
- After regenerating protos, re-run `xcodegen generate` so the new
  `Generated/anki/*.pb.swift` files are added to the project. `project.yml`
  excludes `build/` and `*.xcodeproj` so build output isn't swept into sources
  (which caused "Unexpected duplicate tasks").
- **App builds + links successfully** for `arm64` iphonesimulator
  (`BUILD SUCCEEDED`, links SwiftProtobuf + `-lankiffi`), and the
  `AnkiCompanion.app` binary is produced.

Status of launching in the Simulator on this machine: **RUNNING — verified with
a live screenshot.** The MCAT companion boots in the iOS Simulator and renders
its "MCAT Readiness" UI (three score cards — Readiness / Memory / Performance,
all "No score yet" on an empty collection — plus "Study Next: Enzymes and
Kinetics", and a "Level 1 · 0 XP / 0-day streak" progress row). Screenshot saved
at `/tmp/sim_app.png` (`/tmp/sim_app2.png` = fully rendered).

**Root cause of the earlier boot failure (corrected):** the blocker was NOT
disk space — it was a **runtime/Xcode version mismatch**. The only installed
simulator runtime was **iOS 18.6 (22G86)**, which is _newer_ than Xcode 16.4
supports (its native iphonesimulator SDK is 18.5). Every 18.6 boot hung forever
on data-migration, never built the dyld shared cache, and `simctl
launch`/`spawn` hung — SpringBoard never came up.

**The fix that worked:**

1. `xcrun simctl shutdown all`; deleted the stale MCAT/MCAT2 devices.
2. Deleted the incompatible runtime:
   `xcrun simctl runtime delete 048D7364-6992-455C-A32C-10F6FC548D05`
   (the 18.6 disk-image UUID) + `xcrun simctl delete unavailable` → reclaimed
   ~12 GB (10 GB → 22 GB free).
3. Downloaded the matching runtime:
   `xcodebuild -downloadPlatform iOS -buildVersion 18.5` → installed
   **iOS 18.5 (22F77)**, ~8.86 GB. (This CLI path worked; no Xcode GUI /
   Apple ID needed.)
4. Created a fresh device on 18.5:
   `xcrun simctl create "MCAT-185" com.apple.CoreSimulator.SimDeviceType.iPhone-16 com.apple.CoreSimulator.SimRuntime.iOS-18-5`
   → device `3A88877F-F314-438E-BE02-DD005F468C47`.
5. `xcrun simctl boot <dev>`; `open -a Simulator`;
   `xcrun simctl bootstatus <dev> -b`. On 18.5 the data-migration **progressed
   through its migrators and completed cleanly** (~20 min, first boot builds the
   dyld cache; empty dyld stderr = healthy) — unlike 18.6 which stalled forever.
6. `xcrun simctl install <dev> .../Debug-iphonesimulator/AnkiCompanion.app`
   (rc=0). First `launch` failed with "Unknown application display identifier"
   because SpringBoard/LaunchServices hadn't registered the app yet on first
   boot; **uninstall + reinstall** once SpringBoard was fully up registered it
   (`simctl listapps` then showed it), and
   `xcrun simctl launch <dev> net.ankiweb.ankicompanion` returned a pid.
7. `xcrun simctl io <dev> screenshot /tmp/sim_app.png` confirmed the UI.

Final free disk: **14 GB** (228 GB volume). Runtime now installed:
`iOS 18.5 (18.5 - 22F77)`.

Or in the IDE: `open mobile/AnkiCompanion/AnkiCompanion.xcodeproj`, pick an
iPhone Simulator (on the 18.5 runtime), Run.

Re-run `patch_service_indices.sh` and `gen_swift_proto.sh` after any proto/backend
regen. Files: `mobile/AnkiCompanion/project.yml` (XcodeGen spec),
`mobile/ankiffi/include/module.modulemap`, `patch_service_indices.sh`.

---

## Phase 2 — AI Implementation

Phase 2 adds AI features 9.3, 9.4, 9.5, 9.6, 9.8 and the 9.9 safety
requirements. Feature 9.7 (difficulty/tagging assistant) is intentionally out of
scope. Everything is gated: with AI off / offline / erroring / rate-limited,
every RPC returns a typed "unavailable" result and callers fall back to
deterministic behaviour, so **review, dashboard, scores and sync keep working**.

Legend for merge-risk unchanged (**low/med/high**).

### P2.0 Shared foundation — AI client, config, sources, safety

- **What:** New provider-agnostic, OpenAI-compatible Chat Completions client
  plus the shared plumbing every feature builds on:
    - `AiClient` trait + `OpenAiClient` (reqwest, blocking call driven from a
      dedicated current-thread tokio runtime so it is safe to call from the
      synchronous `Collection`), `MockAiClient` (deterministic, offline; selected
      by `MCAT_AI_MOCK` env or `mcat.ai.mock` config) — used by all Rust unit
      tests, the Python integration tests and the eval harness with **no network
      and no key**.
    - Typed errors: `Unconfigured / Offline / Http / RateLimited / Malformed`.
    - Config resolution order: collection keys (`mcat.ai.base_url`,
      `mcat.ai.model`, `mcat.ai.api_key`, `mcat.ai.checker_cutoff`,
      `mcat.ai.enabled`) → env (`MCAT_AI_BASE_URL`, `MCAT_AI_MODEL`,
      `MCAT_AI_API_KEY`, then `OPENAI_API_KEY`). Defaults:
      `https://api.openai.com/v1`, `gpt-4o-mini`, cutoff `0.7`. Local/keyless
      endpoints (e.g. Ollama `http://localhost:11434/v1`) count as available.
      The api key is **masked on read** and never committed.
    - `complete_json()` helper: prompts for strict JSON, extracts/validates it,
      and **retries once** on malformed output before erroring.
    - Source registry (config-backed): `AiSource {id,name,section,excerpt}`.
      Generation is **rejected without a valid registered source** (9.3/9.9
      fake-source defence).
    - Prompt-injection defence: source text is sanitised (embedded instructions
      neutralised), length-capped, wrapped in a `<<<MCAT_SOURCE>>>` fence and the
      model is told to treat it as **data only** (9.9).
- **Files:** `rslib/src/mcat/ai/{mod,client,prompt,sources,checker,generate,
explain,planner,perfgen,mock,tests}.rs` (new), `rslib/src/mcat/mod.rs` (med:
  add `ai` module), `proto/anki/mcat.proto` (med: new messages + 13 RPCs),
  `rslib/src/mcat/service.rs` (med: implement the RPCs),
  `qt/aqt/mediasrv.py` (med: allowlist — all AI RPCs for the backend, read-only
  ones for the webview), `pylib/anki/collection.py` (med: Python wrappers).
- **Why:** Single-owner shared layer so features stay coherent and the gating /
  safety story is enforced in one place.
- **Verified:** `cargo clippy --tests` clean; Rust unit tests (below) green.
- **Merge-risk:** `mcat.proto` / `service.rs` / `mediasrv.py` / `collection.py`
  are additive within existing MCAT sections (**med**); the `ai/` tree is all
  new (**low**).

### P2.1 (9.3) Source-grounded card generation

- **What:** `GenerateCards(source_id, count, topic_hint)` → a **review queue** of
  candidates (never auto-added). Each card carries source name + section,
  question, answer, topic tag, difficulty, the grounding excerpt (inspectable
  trace) and a full 9.4 quality report. Statuses: Blocked / NeedsReview /
  Accepted / Rejected / Duplicate. `AcceptGeneratedCards` turns chosen
  candidates into **real notes** tagged to the taxonomy topic + `ai-generated`,
  in the MCAT deck (so they sync to mobile).
- **Files:** `rslib/src/mcat/ai/generate.rs` (new).
- **AI-off:** returns `ai_available=false` + reason; no source ⇒ rejected.
- **Verified:** Rust `generation_*` tests; Python `test_generation_*`.

### P2.2 (9.4) AI card-quality checker + gold-set eval

- **What:** 9-category gate (factually correct, useful, clear question, clear
  answer, not vague, not duplicate, not too trivial, properly tagged,
  source-supported) → each pass/fail + score + reason, an overall score and a
  **configurable cutoff (default 0.7, stored in `mcat.ai.checker_cutoff`, set
  before testing)**. Hard-fail categories (`factually_correct`, `not_duplicate`,
  `source_supported`, `not_vague`, `not_too_trivial`) block unconditionally.
  `source_supported` is N/A (passes) when no source excerpt is supplied.
  Deterministic duplicate detection via normalised-token Jaccard similarity.
- **Gold set + harness:** `mcat/ai_eval/` — `source.json`, `generated.json`
  (50 labelled generated cards + a 6-card corpus for dupe detection),
  `run_eval.py`, and `just mcat-ai-eval` (offline via `MCAT_AI_MOCK`). Evaluates
  50 known-good human cards + 50 generated cards vs. a **naive length/keyword
  baseline** and writes `mcat/ai_eval/report.md`, failing if the checker does
  not beat the baseline.
- **Result:** **checker 99.0% vs. baseline 73.0%** accuracy on 100 cards.
- **Files:** `rslib/src/mcat/ai/checker.rs`, `mcat/ai_eval/*` (new), `justfile`
  (med: `mcat-ai-eval` recipe).

### P2.3 (9.5) AI explanations for missed questions

- **What:** `ExplainMiss(card_id, chosen_answer?)` → why-correct, why-your-
  choice-wrong, source citation, related topic, suggested review action. Source-
  grounded; **never used as scoring evidence.** Wired into the desktop reviewer:
  an "Explain this (AI)" button appears on the answer side of MCAT cards when AI
  is available; failure shows a friendly note and **never blocks review**.
- **Files:** `rslib/src/mcat/ai/explain.rs` (new), `qt/aqt/reviewer.py` (med:
  `mcat_explain` bridge cmd + lazy fetch dialog; `_linkHandler` refactored to a
  small `_mcat_link_handler` to stay under the complexity gate).

### P2.4 (9.6) AI study planner

- **What:** `GetAiStudyPlan` → ordered `{action, minutes, reason, evidence}`
  items + a summary + the app evidence it cites (topic mastery, coverage,
  attempts, timing, misses…, reused from `snapshot.rs`/`scores.rs`). **AI cites
  measured data and cannot invent readiness.** The response always carries the
  **deterministic recommender as `fallback`**, and `used_fallback` is set when AI
  is off/unavailable. Surfaced on the dashboard as an "AI Study Plan" card with a
  "data behind this plan" disclosure; the status pill shows AI ready/off.
- **Files:** `rslib/src/mcat/ai/planner.rs` (new), `ts/routes/mcat/+page.ts`
  (med: load status+plan), `ts/routes/mcat/MCATDashboard.svelte` (med: pill +
  plan card), `ts/routes/mcat/+page.svelte` (med: pass props).

### P2.5 (9.8) AI-assisted performance-question generation

- **What:** `GeneratePerfQuestions(card_id)` → 2 paraphrased application
  questions per card, each with explanation, difficulty, source trace, linked
  topic, a quality report, **and a leakage / near-duplicate check** vs. existing
  training/test questions. `AcceptPerfQuestions` creates `MCATPerf`-style notes
  labelled `ai-generated` (distinct from human-authored) so they join the
  interleaving/perf bank.
- **Files:** `rslib/src/mcat/ai/perfgen.rs` (new).

### P2.6 (9.9) Safety — cross-cutting

Wrong facts (checker) · fake sources (registered-source requirement) · prompt
injection (sanitise + fence + data-only) · duplicates (dupe check) · trivial
cards (checker) · broken output (JSON schema + retry) · outage (typed error +
fallback) · rate limits (backoff) · offline (feature-detect; UI hides/disables
AI actions, status pill). Rust `safety_*` tests simulate malformed output, rate
limits and outages and assert **core scoring still works with AI unavailable**.

### P2.7 Qt AI Card Studio + settings

- **What:** New "MCAT AI Card Studio" window (Tools menu): AI status pill, AI
  Settings dialog (base URL / model / key / cutoff / enable — key stored in
  config, never hardcoded), register/select/inspect source, generate, a per-card
  review queue with status, category breakdown and source trace, and
  accept-checked → MCAT deck. Generation is disabled when AI is unavailable.
- **Files:** `qt/aqt/mcat_ai.py` (new), `qt/aqt/__init__.py` (med: dialog
  registration), `qt/aqt/main.py` (med: menu action).

### P2.8 Tests, tooling & housekeeping

- **What:** Python integration tests through the protobuf boundary
  (`pylib/tests/test_mcat_ai.py`: status/config round-trip, source-gated
  generation + accept, checker block/pass + cutoff, evidence-grounded plan,
  explain + perf-gen; all offline via `MCAT_AI_MOCK`). Fixed a pre-existing
  installer test that hardcoded `Anki.app` so it resolves the fork's renamed
  `Anki MCAT.app` bundle. Added the author to `CONTRIBUTORS` (required by the
  minilints contributor check).
- **Files:** `pylib/tests/test_mcat_ai.py` (new), `qt/tools/build_installer.py`
  (med), `CONTRIBUTORS` (low), `rslib/src/mcat/ai/tests.rs` (new).

### Configuring a real provider

No API key is committed. To use a real provider, open **Tools → MCAT AI Card
Studio → AI Settings…** and set base URL / model / key (or export
`MCAT_AI_API_KEY` / `OPENAI_API_KEY`). For a fully local setup, point base URL at
`http://localhost:11434/v1` (Ollama) — no key required.

### Deferred

- Mobile (iOS) AI UI. The accepted notes already sync to the companion via the
  existing sync; only the desktop drives generation/acceptance in Phase 2.

### Verified (Phase 2)

`just check` green. Rust AI unit tests + Python `test_mcat_ai.py` pass;
`just mcat-ai-eval` reports checker 99.0% vs. baseline 73.0%.
