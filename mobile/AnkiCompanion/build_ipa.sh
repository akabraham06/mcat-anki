#!/usr/bin/env bash
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# Build a DISTRIBUTABLE, code-signed .ipa of the Anki MCAT companion for a
# real iPhone/iPad (not the Simulator).
#
# It:
#   1. regenerates the Xcode project cleanly (avoiding the xcodegen
#      INFOPLIST_FILE trap by keeping all build output under ../build),
#   2. archives for a generic iOS device with your signing settings, then
#   3. exports an .ipa using one of the ExportOptions-*.plist templates.
#
# Usage:
#   DEVELOPMENT_TEAM=ABCDE12345 ./build_ipa.sh <adhoc|app-store|development>
#
#   adhoc        -> ExportOptions-adhoc.plist        (registered-UDID testing)
#   app-store    -> ExportOptions-appstore.plist     (upload to TestFlight)
#   development  -> ExportOptions-development.plist   (sideload / your devices)
#
# Environment:
#   DEVELOPMENT_TEAM   (REQUIRED) your 10-char Apple Team ID.
#   CODE_SIGN_STYLE    (optional) Automatic (default) or Manual.
#
# The only thing you MUST supply is DEVELOPMENT_TEAM — everything else is
# wired up here. See DISTRIBUTION.md for the full walkthrough.
set -euo pipefail

# --- locate ourselves --------------------------------------------------------
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"    # mobile/AnkiCompanion
BUILD_DIR="$(cd "$SRC_DIR/.." && pwd)/build" # mobile/build  (OUTSIDE source root)
cd "$SRC_DIR"

SCHEME="AnkiCompanion"
ARCHIVE_PATH="$BUILD_DIR/AnkiCompanion.xcarchive"
DERIVED="$BUILD_DIR/DerivedData"
PACKAGES="$BUILD_DIR/SourcePackages"
EXPORT_DIR="$BUILD_DIR/ipa"

# --- parse the distribution channel arg -------------------------------------
CHANNEL="${1:-}"
case "$CHANNEL" in
  adhoc)        EXPORT_PLIST="ExportOptions-adhoc.plist" ;;
  app-store)    EXPORT_PLIST="ExportOptions-appstore.plist" ;;
  development)  EXPORT_PLIST="ExportOptions-development.plist" ;;
  *)
    cat >&2 <<EOF
error: missing/invalid distribution channel.

  usage: DEVELOPMENT_TEAM=ABCDE12345 $0 <adhoc|app-store|development>

    adhoc        registered-UDID testing IPA
    app-store    IPA for upload to App Store Connect / TestFlight
    development  sideload / personal-device IPA
EOF
    exit 2
    ;;
esac

# --- signing preflight -------------------------------------------------------
if [[ -z "${DEVELOPMENT_TEAM:-}" ]]; then
  cat >&2 <<'EOF'
error: DEVELOPMENT_TEAM is not set.

A real, installable .ipa MUST be code-signed, which requires your Apple
Development Team ID (10 chars, e.g. ABCDE12345). Find it at:
  * https://developer.apple.com/account  ->  Membership details, or
  * Xcode > Settings > Accounts > (your team) > the ID in parentheses.

Then re-run, e.g.:
  DEVELOPMENT_TEAM=ABCDE12345 ./build_ipa.sh development

(This is the one unavoidable external dependency — see DISTRIBUTION.md.)
EOF
  exit 1
fi

CODE_SIGN_STYLE="${CODE_SIGN_STYLE:-Automatic}"

if [[ ! -f "$EXPORT_PLIST" ]]; then
  echo "error: export options template '$EXPORT_PLIST' not found in $SRC_DIR" >&2
  exit 1
fi

# --- 1. regenerate the project cleanly (honor the INFOPLIST_FILE trap) -------
# xcodegen wires INFOPLIST_FILE to any Info.plist under the source root, so we
# must never let build artifacts land here. Nuke the generated project + any
# stray local build dir, then regenerate.
echo "==> Regenerating Xcode project (clean)"
rm -rf "$SRC_DIR/AnkiCompanion.xcodeproj" "$SRC_DIR/build"
xcodegen generate

# --- 2. archive for a generic iOS device ------------------------------------
echo "==> Archiving for device (team=$DEVELOPMENT_TEAM, style=$CODE_SIGN_STYLE)"
rm -rf "$ARCHIVE_PATH"
xcodebuild archive \
  -project "$SRC_DIR/AnkiCompanion.xcodeproj" \
  -scheme "$SCHEME" \
  -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE_PATH" \
  -derivedDataPath "$DERIVED" \
  -clonedSourcePackagesDirPath "$PACKAGES" \
  -allowProvisioningUpdates \
  DEVELOPMENT_TEAM="$DEVELOPMENT_TEAM" \
  CODE_SIGN_STYLE="$CODE_SIGN_STYLE"

# --- 3. export the .ipa ------------------------------------------------------
# xcodebuild does not expand variables inside ExportOptions.plist, so bake the
# team id into a throwaway copy.
RESOLVED_PLIST="$BUILD_DIR/$(basename "${EXPORT_PLIST%.plist}")-resolved.plist"
sed "s/__DEVELOPMENT_TEAM__/$DEVELOPMENT_TEAM/g" "$EXPORT_PLIST" > "$RESOLVED_PLIST"

echo "==> Exporting .ipa ($CHANNEL) via $EXPORT_PLIST"
rm -rf "$EXPORT_DIR"
xcodebuild -exportArchive \
  -archivePath "$ARCHIVE_PATH" \
  -exportOptionsPlist "$RESOLVED_PLIST" \
  -exportPath "$EXPORT_DIR" \
  -allowProvisioningUpdates

echo
echo "==> Done. IPA(s):"
ls -1 "$EXPORT_DIR"/*.ipa 2>/dev/null || {
  echo "   (no .ipa found — check the xcodebuild output above)" >&2
  exit 1
}
