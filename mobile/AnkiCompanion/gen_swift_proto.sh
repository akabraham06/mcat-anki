#!/usr/bin/env bash
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# Generate SwiftProtobuf message types from the shared .proto files, into
# mobile/AnkiCompanion/Generated. Requires protoc + protoc-gen-swift:
#     brew install swift-protobuf        # provides protoc-gen-swift
# and a protoc (the repo ships one at out/extracted/protoc/bin/protoc).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/mobile/AnkiCompanion/Generated"
PROTOC="${PROTOC:-$ROOT/out/extracted/protoc/bin/protoc}"

mkdir -p "$OUT"

# Generate all anki protos: backend.proto pulls in the full service surface, so
# generating the whole set guarantees every referenced type resolves in Swift.
PROTOS=()
for f in "$ROOT"/proto/anki/*.proto; do
  PROTOS+=("anki/$(basename "$f")")
done

"$PROTOC" \
  --proto_path="$ROOT/proto" \
  --swift_out="$OUT" \
  --swift_opt=Visibility=Public \
  "${PROTOS[@]}"

echo "==> Generated Swift protobuf types in $OUT"
