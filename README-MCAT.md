# Anki MCAT — Setup & Run

Concise, verified instructions for running the packaged macOS app and for
building/running from source (desktop and iOS). For the full project overview,
architecture, and feature list, see [`README.md`](./README.md).

## What this is

A fork of Anki (upstream [`ankitects/anki`](https://github.com/ankitects/anki))
with an added **MCAT readiness layer**:

- a **Rust scoring engine** that computes memory, performance, and readiness
  scores — each reported with an honest score range and governed by a
  give-up / abstention rule (no readiness score until there is enough evidence);
- a **desktop MCAT home/dashboard** plus a timed exam-style review loop; and
- an **iOS companion app** (`mobile/AnkiCompanion`) that reviews the same
  collection, kept in sync over AnkiWeb.

Both the desktop app and the iOS companion share the same Rust engine, so they
compute identical scores.

## Running the macOS installer

- The built installer is `out/installer/dist/anki-26.05-mac-apple.dmg`. Opening
  it produces **"Anki MCAT.app"**.
- **Apple Silicon (arm64) only.** The binary is single-arch arm64 and will
  **not** run on Intel Macs. Intel would need a separate universal / x86_64
  build.
- The app is **ad-hoc signed and NOT notarized** (`Signature=adhoc`,
  `TeamIdentifier=not set`). macOS Gatekeeper will therefore block it on any
  machine other than the one that built it. To run it on another Apple Silicon
  Mac, use **one** of the following:
  1. **Right-click the app → Open**, then confirm **Open** in the dialog
     (first launch only); or
  2. In Terminal, clear the quarantine attribute:

     ```bash
     xattr -dr com.apple.quarantine "/Applications/Anki MCAT.app"
     ```

     (adjust the path to wherever the app is installed); or
  3. After the first blocked attempt, go to **System Settings → Privacy &
     Security** and click **"Open Anyway"**.

> For a seamless double-click experience on any clean Mac, the app would need
> Developer ID signing + Apple notarization (which requires a paid Apple
> Developer account). That has **not** been done.

## Clean installers for both macOS and Windows (recommended)

You do **not** need a Windows machine (or a paid signing certificate) to get a
clean installer for each platform. The repo ships a secrets-free GitHub Actions
workflow that builds **all** desktop installers from the current branch, with
every local change included:

**`.github/workflows/build-installers.yml`** — "Build Installers (unsigned)".

1. Push the branch to your GitHub fork (Actions must be enabled on the fork).
2. In the fork: **Actions → "Build Installers (unsigned)" → Run workflow**, and
   pick the branch. (Or from the CLI: `gh workflow run build-installers.yml --ref <branch>`.)
3. When the run finishes, download the per-platform artifacts from the run page:
   - `installer-macos` — `.dmg`, Apple Silicon
   - `installer-macos-intel` — `.dmg`, Intel
   - `installer-windows` — `.msi`, x64
   - `installer-linux` — `.tar.zst`

This reuses the exact build steps as the official `release.yml` but **skips all
code-signing, notarization, and publishing**, so it needs no Apple/Azure
secrets and no special `release` environment. The artifacts are therefore
**unsigned** — see the bypass steps below.

> The stock `release.yml` can also produce these same unsigned artifacts if you
> dispatch it with its defaults (`sign=false`, no draft/PyPI); the dedicated
> workflow above just removes the release-only version/PyPI inputs so there's
> nothing to get wrong.

**Launching an unsigned build:**

- **macOS:** same Gatekeeper bypass as above (right-click → Open, or
  `xattr -dr com.apple.quarantine "/Applications/Anki MCAT.app"`).
- **Windows:** SmartScreen will warn on an unsigned `.msi`. Click **"More
  info" → "Run anyway"** to proceed (first launch only).

**Local single-platform build.** On your own machine you can also build the
installer for _that_ platform directly:

```bash
just installer     # .dmg on macOS, .msi on Windows, .tar.zst on Linux
```

Output lands in `out/installer/dist/`. (This is the current-platform-only path;
use the CI workflow above to get the other platforms.)

## Building the desktop app from source (macOS, Windows, or Linux)

**Prerequisites**

- `git`
- `rustup` — the repo pins Rust **1.92.0** via `rust-toolchain.toml`
- `just`
- a C toolchain (on macOS: **Xcode Command Line Tools**)

Python (**3.13.13**, via `uv`), plus node / yarn / uv / protoc, are
auto-downloaded by the build system.

**Common commands**

```bash
just run            # build + launch in development mode
just run-optimized  # release-optimized dev run
just check          # format + full build + all checks/tests
just installer      # build an installer for the current platform
```

**Cross-platform note.** The build system supports macOS, Windows, and Linux
(Windows uses pwsh + native-tls; other platforms use rustls). The MCAT
additions are pure Rust / TypeScript / Python with no platform-specific code.
The Windows installer is produced on a Windows CI runner via the
[Build Installers workflow](#clean-installers-for-both-macos-and-windows-recommended)
above; it has not been hand-tested on Windows hardware, but it is built from the
same sources through the same Briefcase packaging path as the official release.

## Building & running the iOS app (macOS only)

iOS builds require a Mac with **full Xcode** (not just the Command Line Tools),
and **cannot** be built or run on Windows.

1. Point `xcode-select` at the full Xcode:

   ```bash
   xcode-select -s /Applications/Xcode.app
   ```

2. Add the Rust iOS targets:

   ```bash
   rustup target add aarch64-apple-ios aarch64-apple-ios-sim
   ```

3. Build the Rust engine framework:

   ```bash
   ./mobile/build_ios.sh
   ```

   This produces `mobile/build/AnkiEngine.xcframework`, which is **not
   committed** and must be rebuilt on each machine.

4. Generate the Xcode project with xcodegen (do **not** rely on opening a stale
   committed project):

   ```bash
   brew install xcodegen
   (cd mobile/AnkiCompanion && xcodegen generate)
   ```

5. Open `mobile/AnkiCompanion/AnkiCompanion.xcodeproj` in Xcode, pick an iPhone
   simulator (or a device), and **Run**. For a **real device** you must set
   your own Apple **Development Team** under **Signing & Capabilities** (the
   simulator needs no signing).

SwiftProtobuf resolves automatically via the committed `Package.resolved`.

## Sync (desktop ↔ mobile)

Both the desktop and the iOS app sync to **AnkiWeb** (the hub). Sign in to the
**same AnkiWeb account** on both. Leave the **Custom Sync Server** field blank
to use AnkiWeb.

Reviews and changes propagate device → AnkiWeb → other device on each sync —
this is **not** real-time; each side must sync.

> **Media note:** media sync is currently **disabled** on mobile, so
> images/audio are not transferred to the phone yet. Card text, scheduling, and
> reviews are.

## AI features (optional)

The MCAT AI features (card generation, quality checker, missed-question
explanations, study planner, perf-question generation) call an
OpenAI-compatible endpoint. They are **optional and degrade gracefully** — with
no/invalid key the app falls back to deterministic behavior and the reviewer
keeps working.

There are three ways to supply credentials:

1. **Per-user, in-app (default).** Each user pastes their own key into
   **AI Settings**; it's stored (masked) in their collection, never in the repo.
2. **Your own machine.** Set `OPENAI_API_KEY` (or `MCAT_AI_API_KEY`) in the
   environment that launches the app (`export OPENAI_API_KEY=... && just run`).
   GUI-launched apps don't inherit a shell's env, so this suits dev use.
3. **Zero user input via a hosted proxy (recommended for distribution).** You
   host a small proxy that holds the real OpenAI key server-side; the app ships
   pre-pointed at it with a low-privilege app token. Deploy the ready-made proxy
   in [`mcat/proxy/`](./mcat/proxy/README.md), then build with it baked in:

   ```bash
   MCAT_AI_PROXY_URL="https://<your-site>/v1" \
   MCAT_AI_PROXY_TOKEN="<your app token>" \
   just installer
   ```

   No key is ever placed in the app binary or the repo. See
   [`mcat/proxy/README.md`](./mcat/proxy/README.md) for deploy steps and the
   important **spend-cap / abuse-protection** notes.

> Never commit an API key. OpenAI auto-revokes keys pushed to public repos.
