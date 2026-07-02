#!/usr/bin/env bash
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# Keep the Service indices in AnkiBackend.swift in sync with the generated Rust
# backend. Service indices are assigned at build time, so this reads them back
# out of out/pylib/anki/_backend_generated.py and rewrites the Swift enum.
#
# Usage (after a build):  mobile/AnkiCompanion/patch_service_indices.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GEN="$ROOT/out/pylib/anki/_backend_generated.py"
SWIFT="$ROOT/mobile/AnkiCompanion/AnkiBackend.swift"

[ -f "$GEN" ] || { echo "error: $GEN not found; build first (e.g. just check)"; exit 1; }

# Pull the service index from a representative *_raw method of each service.
# Portable (no gawk): find the def line, then the first _run_command after it.
index_for() {
    grep -A6 "def $1(" "$GEN" \
        | grep -m1 "_run_command(" \
        | sed -E 's/.*_run_command\(([0-9]+),.*/\1/'
}

COLLECTION=$(index_for "open_collection_raw")
MCAT=$(index_for "get_exam_readiness_raw")

[ -n "$COLLECTION" ] && [ -n "$MCAT" ] || {
    echo "error: could not extract service indices (backend regenerated?)"; exit 1
}

echo "collection = $COLLECTION, mcat = $MCAT"

# Rewrite the two enum lines in place.
/usr/bin/sed -i '' -E \
    -e "s/(case collection = )[0-9]+/\1$COLLECTION/" \
    -e "s/(case mcat = )[0-9]+/\1$MCAT/" \
    "$SWIFT"

echo "==> Patched $SWIFT"
