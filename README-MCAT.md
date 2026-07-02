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
additions are pure Rust / TypeScript / Python with no platform-specific code,
but these MCAT changes have **not yet been exercised through an actual Windows
build**.

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
