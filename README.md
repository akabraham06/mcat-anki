# MCAT Anki Mastery

**Exam: MCAT** (scored 472–528; four sections each scored 118–132).

A desktop study app and an iOS companion, **built on a fork of [Anki](https://apps.ankiweb.net)** and sharing **one Rust engine**. It goes beyond flashcard memory to answer three separate questions, each with an honest uncertainty range:

1. **Memory** — can you recall a fact right now? (built on Anki's FSRS)
2. **Performance** — can you answer a _new, exam-style_ question that uses it?
3. **Readiness** — what MCAT score would you get today, and how sure are we?

The app follows an **honesty rule**: it refuses to show a readiness score until it has enough evidence (a written-down give-up rule), and every score ships with its point estimate, likely range, exam coverage, confidence, last-updated time, and the reasons behind it.

> **Setup & run in a hurry?** See [`README-MCAT.md`](./README-MCAT.md) for concise, verified instructions (macOS installer + building/running desktop and iOS from source).

> This is an AGPL-3.0-or-later fork of Anki, with credit to Ankitects Pty Ltd and contributors. See [License](#license).

---

## Two apps, one engine

|         | Desktop (main app)                         | iOS companion                                                     |
| ------- | ------------------------------------------ | ----------------------------------------------------------------- |
| Runtime | PyQt + web frontend over `pylib` → `rslib` | SwiftUI over `rslib` via a C‑FFI (`mobile/ankiffi`)               |
| Purpose | Full review + MCAT dashboard               | Review-on-the-go + readiness check                                |
| Engine  | **Same Rust `rslib` engine**               | **Same Rust `rslib` engine** (linked as `AnkiEngine.xcframework`) |

The MCAT logic lives in the Rust engine (`rslib/src/mcat`), so both apps compute **identical** scores. The engine is exposed through a new protobuf `McatService`, consumed by Python, TypeScript (the dashboard), and Swift (the companion).

### The Rust change

The core change is a new **MCAT mastery / readiness engine inside Anki's Rust layer** (`rslib/src/mcat`), exposed via a new `McatService` in `proto/anki/mcat.proto`. It adds: a taxonomy-driven coverage map, the three scores with abstention, a deterministic best-next-topic recommender, a recall-vs-paraphrase transfer-gap metric, interleaving, timed pacing, and local XP. A full chronological implementation log, the list of upstream files touched, and merge-risk notes are in **[`steps.md`](./steps.md)**.

---

## Desktop app — setup & run

Requirements: the standard Anki toolchain (managed by `just`). Run `just --list` to see all recipes.

### Option A — run the packaged installer (recommended; how the app is meant to be opened)

A macOS installer is produced at `out/installer/dist/`:

```bash
just installer          # builds out/installer/dist/anki-<ver>-mac-apple.dmg
open out/installer/dist/anki-26.05-mac-apple.dmg
```

Then drag **Anki** into **Applications** and launch it (first launch: right‑click → **Open** to bypass Gatekeeper, as the build is not notarized).

### Option A2 — download prebuilt installers for macOS **and** Windows (no build needed)

A secrets-free GitHub Actions workflow builds unsigned installers for every
desktop platform from the current branch:

- **Actions → "Build Installers (unsigned)" → Run workflow** (or
  `gh workflow run build-installers.yml --ref <branch>`), then download the
  artifacts: `installer-macos` (`.dmg`, Apple Silicon), `installer-macos-intel`
  (`.dmg`, Intel), `installer-windows` (`.msi`, x64), `installer-linux`
  (`.tar.zst`).
- First launch of an unsigned build: **macOS** → right‑click → **Open**;
  **Windows** → SmartScreen **"More info" → "Run anyway"**.

See [`README-MCAT.md`](./README-MCAT.md#clean-installers-for-both-macos-and-windows-recommended)
for the full walkthrough.

### Option B — build from source and run (development)

```bash
just run                # builds pylib + qt + web, then launches Anki
```

For live web reloading during development, run `just web-watch` in a second terminal.

### Open the MCAT dashboard

In the running desktop app: **Tools → MCAT Dashboard**. It shows the three scores with ranges, the section breakdown, the best-next-topic recommendation, transfer gaps, the pacing table, and the interleaved-session builder.

### Load the starter deck

A starter deck (33 knowledge cards + 61 exam-style performance questions, pre-tagged to the MCAT taxonomy) is generated at `mcat/dist/mcat_starter.apkg`:

```bash
python mcat/gen_deck.py           # regenerate mcat/dist/mcat_starter.apkg
```

Import it via **File → Import** in the desktop app to populate the dashboard.

---

## iOS companion — setup & run (Xcode)

The companion runs the **same Rust engine** on iOS through a C‑FFI static library packaged as an XCFramework.

### Prerequisites

- **Full Xcode** (not just Command Line Tools). This project was built and verified with **Xcode 16.4**.
- **iOS Simulator runtime that matches your Xcode.** Xcode 16.4 ships the iOS **18.5** SDK, so install the **18.5** runtime — a newer runtime (e.g. 18.6) will fail to boot on Xcode 16.4:

  ```bash
  xcodebuild -downloadPlatform iOS -buildVersion 18.5
  ```

- Helper tools:

  ```bash
  brew install xcodegen protobuf swift-protobuf
  rustup target add aarch64-apple-ios-sim aarch64-apple-ios
  ```

### Build steps

Run from the repo root:

```bash
# 1. Cross-compile the Rust engine for iOS and package the XCFramework.
#    (Use the repo's own target dir so paths resolve.)
CARGO_TARGET_DIR="$PWD/target" bash mobile/build_ios.sh
#    -> mobile/build/AnkiEngine.xcframework

# 2. Generate the Swift protobuf types the companion uses.
PROTOC="$(which protoc)" bash mobile/AnkiCompanion/gen_swift_proto.sh
#    -> mobile/AnkiCompanion/Generated/anki/*.pb.swift

# 3. Generate the Xcode project.
cd mobile/AnkiCompanion && xcodegen generate
#    -> mobile/AnkiCompanion/AnkiCompanion.xcodeproj
```

If you regenerate the backend/protos, re-run `mobile/AnkiCompanion/patch_service_indices.sh` to keep the service indices in `AnkiBackend.swift` in sync, then re-run steps 2–3.

### Run

- **From Xcode:** `open mobile/AnkiCompanion/AnkiCompanion.xcodeproj`, pick an **iPhone simulator on iOS 18.5**, and press **Run**.
- **From the command line:**

  ```bash
  # Build for the simulator
  cd mobile/AnkiCompanion
  xcodebuild -project AnkiCompanion.xcodeproj -scheme AnkiCompanion \
    -destination 'platform=iOS Simulator,name=iPhone 16' \
    -configuration Debug -derivedDataPath build/DerivedData \
    CODE_SIGNING_ALLOWED=NO build

  # Boot a device, install, launch
  DEV=$(xcrun simctl create MCAT "com.apple.CoreSimulator.SimDeviceType.iPhone-16" "com.apple.CoreSimulator.SimRuntime.iOS-18-5")
  xcrun simctl boot "$DEV"; open -a Simulator
  xcrun simctl install "$DEV" build/DerivedData/Build/Products/Debug-iphonesimulator/AnkiCompanion.app
  xcrun simctl launch "$DEV" net.ankiweb.ankicompanion
  ```

The app opens to the **MCAT Readiness** screen (three score cards, best-next-topic recommendation, and progress). On an empty collection every score correctly shows “No score yet” (the give-up rule in action).

> **Performance note:** the iOS Simulator emulates a full iOS device and is memory-hungry. On an 8 GB Mac it will be slow; close other apps or run on a physical iPhone for a smooth experience.

---

## Sync (desktop ↔ mobile)

You do **not** need a custom sign-in system. Card decks and progress sync through **Anki's built-in account sync**, and because both apps link the same Rust engine, the sync client is already compiled into each — the "sign-in" is simply your sync account.

### 1. Pick a server

- **AnkiWeb (recommended):** the free hosted sync server. Sign in with an [AnkiWeb](https://ankiweb.net) account and leave the endpoint empty.
- **Self-hosted:** run a sync server and point both apps at it via the `endpoint` field (use `SetCustomCertificate` for a self-signed cert).

### 2. Desktop (built in)

**Tools → Sync** (or the sync button) → sign in with your account. This uploads/downloads your collection. Nothing to build.

### 3. iOS companion

The shared engine exposes the sync RPCs through the FFI (backend **sync service**, methods `SyncLogin` → `SyncCollection` → `FullUploadOrDownload`). To sync the companion:

1. Sign in with `SyncLogin(username, password)` → returns a `SyncAuth { hkey, endpoint }`.
2. Store **only the `hkey` token** in the iOS **Keychain** (never the password).
3. Call `SyncCollection(auth)`; handle the `required` result (`NO_CHANGES` / `NORMAL_SYNC` / `FULL_DOWNLOAD` / `FULL_UPLOAD`). The first sync on a fresh device is typically a **full download**.

The collection must live at a stable, writable path (the app's `Documents` directory) so sync can mutate it in place.

### 4. End to end

Desktop: sign in → **Sync** (uploads your MCAT decks). Phone: sign in with the **same account** → sync (first sync full-downloads the collection). After that, reviews and progress reconcile both ways through the server.

> **Security:** persist the `hkey` token, not the password. If self-hosting, both clients must trust the server certificate and share the same `endpoint`.

---

## Features

- **MCAT taxonomy** — 4 sections, 27 weighted topics with target answer times, embedded in the engine (`rslib/src/mcat/taxonomy.json`).
- **Three scores** — memory, performance, readiness; each with point estimate, range, coverage, confidence, and reasons.
- **Honest abstention** — no readiness score until ≥ 100 graded reviews and ≥ 50% topic coverage.
- **Best-next-topic recommender** — deterministic priority = exam‑weight × weakness × coverage‑gap × due‑ness.
- **Transfer-gap metric** — mean recall vs. exam-style accuracy per topic (`MCATPerf` note type).
- **Interleaving** — round-robin vs. blocked session builder with a toggle for ablation.
- **Timed pacing** — per-topic target seconds with overtime tracking.
- **Local XP / streaks** — offline gamification.

---

## AI features & evaluation

Five AI features (in `rslib/src/mcat/ai/`) assist **authoring and coaching**. Each one must beat the exact no-AI path it would otherwise fall back to, or it doesn't ship:

| PRD | Feature                             | Beats (no-AI baseline)                                                                                                    |
| --- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 9.4 | **Card-quality gate**               | naive length/keyword rule — catches vague / trivial / circular / unsupported / duplicate cards before a student sees them |
| 9.3 | **Source-grounded generation**      | flat template extractor — produces recall → exam → stretch difficulty tiers, grounded in a named source                   |
| 9.5 | **Missed-question explanations**    | one generic static hint — explains why the right answer is right and your choice was wrong, cited to the source           |
| 9.6 | **Study planner**                   | deterministic recommender — turns measured review data into a few concrete, timed, cited steps                            |
| 9.8 | **Performance-question generation** | verbatim card reuse — writes novel application questions that transfer                                                    |

Two guarantees run through all of them:

- **Every AI output traces back to a named source.** Generation requires a registered source; each accepted card carries a visible `Source: …` citation **and** a machine-readable `ai-source::<id>` tag.
- **AI never feeds the score.** Readiness / Memory / Performance stay fully deterministic (`rslib/src/mcat/scores.rs`); with AI off the app still scores.

**Zero user setup:** the app ships pointed at a built-in hosted proxy (real key held server-side), so AI works with **no API key typed in**. It degrades gracefully to the baselines above if AI is off or unavailable.

### Evaluation (runs before any card reaches a student)

A deterministic, offline evaluation (`just mcat-ai-eval`, mock provider — no network/key) checks each feature against its baseline and gates generated cards at a **cutoff of 0.70 set before testing**. On a **held-out set of 50 labelled cards** (20 good, 30 deliberately bad):

| Method                 | Accuracy | Wrong-answer rate (bad cards shown) |
| ---------------------- | -------- | ----------------------------------- |
| **AI quality gate**    | **100%** | **0%**                              |
| Keyword search         | 86%      | 24%                                 |
| Vector search (TF-IDF) | 84%      | 23%                                 |

All **5/5** features beat their no-AI baseline by a pre-registered margin. Full write-up: [`mcat/ai_eval/report.md`](./mcat/ai_eval/report.md).

### Reproduce / demo

```bash
just mcat-ai-eval                  # offline: AI-on vs AI-off + held-out gate vs keyword/vector
just mcat-ai-verify-scoring-off    # offline: app still scores with AI OFF (+ give-up rule)
just mcat-ai-verify-live           # live: zero-config proxy + real checker + source-grounded gen
bash mcat/ai_eval/walkthrough.sh   # all of the above, narrated per requirement
```

- **What/why/skipped note:** [`mcat/ai_eval/AI_NOTES.md`](./mcat/ai_eval/AI_NOTES.md)
- **Recording script (for a demo video):** [`mcat/ai_eval/RECORDING_SCRIPT.md`](./mcat/ai_eval/RECORDING_SCRIPT.md)
- **Supplying credentials / hosting the proxy:** see [`README-MCAT.md`](./README-MCAT.md#ai-features-optional) and [`mcat/proxy/README.md`](./mcat/proxy/README.md)

## Testing

```bash
just test-rust      # Rust engine tests (incl. rslib/src/mcat/*)
just test-py        # Python integration tests (pylib/tests/test_mcat.py)
just check          # format + full build + all checks/lints
```

## Repository layout (MCAT additions)

```
rslib/src/mcat/           # Rust MCAT engine (taxonomy, snapshot, scores, recommender, interleaving)
proto/anki/mcat.proto     # McatService + messages
pylib/anki/collection.py  # Python wrappers for the MCAT RPCs
ts/routes/mcat/           # SvelteKit MCAT dashboard
qt/aqt/mcat.py            # Qt dialog hosting the dashboard (Tools -> MCAT Dashboard)
mcat/                     # starter-deck generator + mcat_starter.apkg
mobile/ankiffi/           # C-FFI static library over the engine
mobile/AnkiCompanion/     # SwiftUI iOS companion + XcodeGen project
steps.md                  # implementation log + files touched + merge risk
```

---

## License

This project is a fork of Anki and is licensed **AGPL-3.0-or-later**, with credit to **Ankitects Pty Ltd and contributors**. Some parts of Anki are under BSD-3-Clause. See [LICENSE](./LICENSE).

Upstream Anki: <https://apps.ankiweb.net> · developer docs: <https://dev-docs.ankiweb.net>
