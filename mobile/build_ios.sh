#!/usr/bin/env bash
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# Build the Anki engine static library for the iOS Simulator (and device) and
# package it as an XCFramework the SwiftUI companion links against.
#
# Requires full Xcode (not just Command Line Tools):
#     xcode-select -p        # must point inside Xcode.app, not CommandLineTools
#     rustup target add aarch64-apple-ios-sim aarch64-apple-ios x86_64-apple-ios
#
# Usage:  mobile/build_ios.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CRATE_DIR="$ROOT/mobile/ankiffi"
OUT="$ROOT/mobile/build"
HEADERS="$CRATE_DIR/include"
LIB="libankiffi.a"

# Build into a dedicated target dir owned by this script, NOT the shared
# workspace/sandbox target dir. A shared CARGO_TARGET_DIR cache has previously
# caused a stale libankiffi.a (built before an rslib change) to be linked into
# the app. Keeping the FFI artifacts here guarantees the xcframework reflects
# the current rslib sources. Override with ANKIFFI_TARGET_DIR if desired.
TARGET_DIR="${ANKIFFI_TARGET_DIR:-$OUT/cargo-target}"

# Simulator (Apple silicon) and device targets. Add x86_64-apple-ios for Intel
# simulators if needed.
SIM_TARGET="aarch64-apple-ios-sim"
DEVICE_TARGET="aarch64-apple-ios"

echo "==> Building static lib for $SIM_TARGET (target dir: $TARGET_DIR)"
cargo build -p anki-ffi --release --target "$SIM_TARGET" --target-dir "$TARGET_DIR"

echo "==> Building static lib for $DEVICE_TARGET (target dir: $TARGET_DIR)"
cargo build -p anki-ffi --release --target "$DEVICE_TARGET" --target-dir "$TARGET_DIR"

rm -rf "$OUT/AnkiEngine.xcframework"
mkdir -p "$OUT"

echo "==> Packaging XCFramework"
xcodebuild -create-xcframework \
  -library "$TARGET_DIR/$SIM_TARGET/release/$LIB" -headers "$HEADERS" \
  -library "$TARGET_DIR/$DEVICE_TARGET/release/$LIB" -headers "$HEADERS" \
  -output "$OUT/AnkiEngine.xcframework"

echo "==> Done: $OUT/AnkiEngine.xcframework"
echo "    Add it to the Xcode app target, then build/run in the Simulator."
