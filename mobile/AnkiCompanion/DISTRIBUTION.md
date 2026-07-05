# Distributing the Anki MCAT companion to a real device

The Simulator build (`xcodebuild ... -destination 'platform=iOS Simulator,...'`)
runs fine unsigned, but **you cannot install a Simulator build on a physical
iPhone/iPad**. A clean-device install requires a *code-signed* app, and code
signing requires **one external thing this repo cannot provide: your Apple
Development Team ID.**

Everything else — project generation, the device archive, and the `.ipa`
export — is automated by [`build_ipa.sh`](./build_ipa.sh) and the
`ExportOptions-*.plist` templates in this folder.

> Bundle identifier: `net.ankiweb.ankicompanion`
> Scheme: `AnkiCompanion`
> Team ID: a 10-character string like `ABCDE12345` (this is the placeholder
> used throughout — replace it with yours).

## Where to find your Team ID

* **Free (personal) team:** Xcode → **Settings → Accounts** → sign in with any
  Apple ID → select the team → the ID is shown in parentheses. Also visible in
  the target’s **Signing & Capabilities** tab once you pick the team.
* **Paid team:** <https://developer.apple.com/account> → **Membership** → *Team ID*.

Plug it in via the `DEVELOPMENT_TEAM` environment variable — never hard-code it
into `project.yml` (that file keeps a `${DEVELOPMENT_TEAM}` placeholder so a
plain `xcodegen generate` still produces a Simulator-buildable project).

---

## The three routes

| Route | Apple account | Devices | Lifespan | Best for |
|-------|---------------|---------|----------|----------|
| **A. Personal-team sideload** | Free Apple ID | Your own devices | App expires after **7 days**, must re-install | Zero cost, fastest for one grader |
| **B. Ad-hoc IPA** | **Paid** ($99/yr) | Up to 100 registered UDIDs / device type / yr | 1 year (profile) | Handing a specific grader an `.ipa` |
| **C. TestFlight** | **Paid** ($99/yr) | Any device that joins the beta | 90 days / build | Any clean device, no cable needed |

---

## Route A — Free personal-team sideload (no paid account)

The lowest-friction path for a grader with a Mac + a cable.

### A1. Straight from Xcode (recommended)

1. Generate and open the project (clean, per the xcodegen trap):
   ```bash
   cd mobile/AnkiCompanion
   rm -rf AnkiCompanion.xcodeproj build && xcodegen generate
   open AnkiCompanion.xcodeproj
   ```
2. Plug in the iPhone/iPad, trust the Mac.
3. In Xcode: select the **AnkiCompanion** target → **Signing & Capabilities** →
   check **Automatically manage signing** → pick your (free) **Team**.
   Xcode registers the device and creates a 7-day development profile.
4. Choose the device in the toolbar → **Product → Run** (⌘R).
5. On the device: **Settings → General → VPN & Device Management** → trust the
   developer profile. Launch the app.

> The app stops launching after 7 days on a free team; just re-run ⌘R to renew.

### A2. AltStore (no cable after initial setup, still free)

1. Build/export a **development** `.ipa` (see the command in Route B — it uses
   the same `development` channel and a free team works for on-device dev):
   ```bash
   cd mobile/AnkiCompanion
   DEVELOPMENT_TEAM=ABCDE12345 ./build_ipa.sh development
   # -> ../build/ipa/AnkiCompanion.ipa
   ```
2. Install [AltStore](https://altstore.io) on the target device (AltServer on a
   Mac/PC does the initial pairing).
3. In AltStore, tap **+** and pick `mobile/build/ipa/AnkiCompanion.ipa`.
   AltStore re-signs with the Apple ID you give it and refreshes the 7-day
   profile automatically while in Wi-Fi range of AltServer.

---

## Route B — Ad-hoc IPA (paid account, specific devices)

Produces an `.ipa` that installs on devices whose **UDIDs are registered** to
your team. No App Review, no TestFlight.

1. **Register the target device UDID(s)** (once per device):
   * Get the UDID: connect the device and run
     ```bash
     xcrun devicectl list devices              # shows UDIDs of attached devices
     ```
     or read it from *Finder → [device] → (click the info line under the name)*.
   * Add it at <https://developer.apple.com/account/resources/devices/list>
     → **+** → paste the UDID. (Automatic signing below will pull it into the
     profile.)
2. **Build the ad-hoc IPA:**
   ```bash
   cd mobile/AnkiCompanion
   DEVELOPMENT_TEAM=ABCDE12345 ./build_ipa.sh adhoc
   # -> ../build/ipa/AnkiCompanion.ipa
   ```
3. **Install on the device** (any one of):
   * Cable, modern:
     ```bash
     xcrun devicectl device install app \
       --device <UDID> ../build/ipa/AnkiCompanion.ipa
     ```
   * **Apple Configurator** (drag the `.ipa` onto the device), or
   * **OTA**: host the `.ipa` + a `manifest.plist` on HTTPS and open an
     `itms-services://?action=download-manifest&url=...` link on the device.

If a device isn’t in the profile, install fails — re-add its UDID and rebuild.

---

## Route C — TestFlight (paid account, any clean device)

The most “clean device” friendly route: testers install the TestFlight app and
tap **Install** — no cable, no UDID.

### C0. One-time App Store Connect setup

1. Paid membership active at <https://developer.apple.com/account>.
2. Create the app record at <https://appstoreconnect.apple.com> → **Apps → +** →
   **New App**, using bundle id `net.ankiweb.ankicompanion`.
3. Create an **App Store Connect API key** (Users and Access → **Integrations /
   Keys** → **App Store Connect API** → **+**). Download the `.p8` **once** and
   note the **Key ID** and **Issuer ID** — these drive the notarytool/altool
   upload below without interactive login.

### C1. Build the App Store IPA

```bash
cd mobile/AnkiCompanion
DEVELOPMENT_TEAM=ABCDE12345 ./build_ipa.sh app-store
# -> ../build/ipa/AnkiCompanion.ipa
```

### C2. Upload the build

Pick whichever you prefer; all three upload the same `.ipa`.

* **`xcrun altool`** (scriptable):
  ```bash
  xcrun altool --upload-app -f ../build/ipa/AnkiCompanion.ipa -t ios \
    --apiKey <KEY_ID> --apiIssuer <ISSUER_ID>
  # (place AuthKey_<KEY_ID>.p8 in ~/.appstoreconnect/private_keys/)
  ```
* **`xcrun notarytool`** — note: `notarytool` is for *notarizing Mac apps*, not
  for iOS App Store uploads. For iOS, use `altool` (above) or Transporter
  (below). It’s listed here only to clarify the distinction.
* **Transporter.app** (Mac App Store, GUI): sign in, **+ ADD APP**, select the
  `.ipa`, **Deliver**.

You can also skip `build_ipa.sh` and do archive+upload in one shot from Xcode:
**Product → Archive → Distribute App → App Store Connect → Upload**.

### C3. Ship to testers

1. In App Store Connect → your app → **TestFlight**, wait for the build to
   finish **Processing**.
2. **Internal testers** (up to 100 people on your team) get it immediately.
   **External testers/public link** require a short **Beta App Review**.
3. Testers install the **TestFlight** app and tap **Install**. Works on any
   clean device.

---

## Verification status (done without an Apple account)

These were confirmed on Xcode 16.4 after the `project.yml` signing changes:

* **Project still generates** cleanly with `xcodegen generate`.
* **Simulator build still succeeds:**
  ```bash
  cd mobile/AnkiCompanion
  rm -rf AnkiCompanion.xcodeproj build && xcodegen generate
  xcodebuild -project AnkiCompanion.xcodeproj -scheme AnkiCompanion \
    -destination 'platform=iOS Simulator,id=72FE9334-1948-4312-A084-761493961507' \
    -derivedDataPath ../build/DerivedData \
    -clonedSourcePackagesDirPath ../build/SourcePackages build
  # ** BUILD SUCCEEDED **
  ```
* **Device archive step works end-to-end** (proving the pipeline up to signing
  is sound), using `CODE_SIGNING_ALLOWED=NO` to stand in for a real team:
  ```bash
  cd mobile/AnkiCompanion
  rm -rf AnkiCompanion.xcodeproj build && xcodegen generate
  xcodebuild archive -project AnkiCompanion.xcodeproj -scheme AnkiCompanion \
    -destination 'generic/platform=iOS' \
    -archivePath ../build/AnkiCompanion.xcarchive \
    -derivedDataPath ../build/DerivedData \
    -clonedSourcePackagesDirPath ../build/SourcePackages \
    CODE_SIGNING_ALLOWED=NO
  # ** ARCHIVE SUCCEEDED **  -> ../build/AnkiCompanion.xcarchive
  #    (Products/Applications/AnkiCompanion.app is an arm64 *device* binary)
  ```

## The one remaining step (needs YOU)

Producing a real, installable `.ipa` for a clean device is impossible without
your **Apple Development Team ID** — that is the single unavoidable external
dependency. Once you have it, the exact command is:

```bash
cd mobile/AnkiCompanion
DEVELOPMENT_TEAM=ABCDE12345 ./build_ipa.sh development   # or: adhoc | app-store
```

Then follow the matching route (A/B/C) above to get it onto the device.
