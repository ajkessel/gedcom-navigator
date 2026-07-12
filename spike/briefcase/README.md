# Briefcase → Mac App Store spike (deliverable c)

Validates the last unknown: **can a Toga app packaged by Briefcase be signed, sandboxed,
and accepted by App Store validation?** Run on macOS with your Apple Developer account —
this cannot run in the Linux dev sandbox.

## What the docs tell us (why this has manual steps)

Briefcase's macOS packaging is built for **Developer ID + notarization** (direct
download). It does *not* first-class **App Store** distribution: no automation for the
Apple Distribution / "3rd Party Mac Developer Application/Installer" certs, no
provisioning-profile embedding, and App Store `.pkg`s are **not** notarized. So the plan:
**Briefcase builds the sandboxed `.app`; the App Store sign/provision/validate steps stay
the same manual dance your `dev/build-mac-appstore.sh` already does** — just pointed at
Briefcase's `.app` instead of PyInstaller's output. Not a loss of capability; a swap of
the bundler.

## Prerequisites
- macOS + Xcode Command Line Tools.
- `python -m pip install briefcase` (in a venv).
- In Keychain: **3rd Party Mac Developer Application: … (4GT4UKXZ4V)** and **3rd Party Mac
  Developer Installer: … (4GT4UKXZ4V)** (aka Apple Distribution / Mac Installer
  Distribution), same Team ID.
- A provisioning profile for `com.ajkessel.gedcom-navigator`
  (`dev/gedcom-navigator.provisionprofile` or `~/Library/MobileDevice/Provisioning Profiles/`).

## Step 1 — dev sanity (no signing)
```bash
cd spike/briefcase
briefcase dev            # runs the app straight from source; confirms Toga works
```

## Step 2 — build the sandboxed .app
```bash
briefcase create macOS
briefcase build macOS
# → build/gedcom-navigator/macos/app/GEDCOM Navigator.app  (universal2, sandbox entitlements)
```

## Step 3 — App Store signing (the part Briefcase doesn't fully automate)

**First, get your EXACT signing identities** — do not hand-type the names (Briefcase
validates `--identity` against the Keychain and rejects any mismatch, e.g.
`Invalid application signing identity ...`):
```bash
security find-identity -v -p codesigning
```
This lists each cert's 40-char SHA-1 hash + common name. For App Store you need two, both
Team ID 4GT4UKXZ4V (these are the names your dev/build-mac-appstore.sh already greps):
- **app cert:** `3rd Party Mac Developer Application: …`  (newer accounts may show `Apple Distribution: …`)
- **installer cert:** `3rd Party Mac Developer Installer: …`

**Then try the Briefcase-native path** — pass the **SHA-1 hashes** (unambiguous; avoids
name-format issues) and skip notarization:
```bash
briefcase package macOS -p pkg \
  --identity <APP_CERT_SHA1> \
  --installer-identity <INSTALLER_CERT_SHA1> \
  --no-notarize
```
**Unknowns to check on-device:** (a) does Briefcase accept the App Store distribution app
identity, and (b) does the resulting `.app` contain the **provisioning profile**? Briefcase
has no documented profile-embedding step, so likely **no** — which App Store validation
rejects.

**If the profile is missing (expected), do the hybrid:** build with Briefcase (Step 2),
then reuse your existing App Store signing logic against Briefcase's `.app`:
```bash
APP="build/gedcom-navigator/macos/app/GEDCOM Navigator.app"
# Use the SHA-1 hashes from `security find-identity -v -p codesigning` (above).
# 1. embed the provisioning profile (mirrors dev/build-mac-appstore.sh)
cp dev/gedcom-navigator.provisionprofile "$APP/Contents/embedded.provisionprofile"
# 2. deep-sign with App Store entitlements + the APP cert (profile must be embedded
#    BEFORE signing), then build the installer .pkg with the INSTALLER cert:
#    (lift the exact codesign/productbuild invocation from dev/build-mac-appstore.sh)
productbuild --component "$APP" /Applications \
  --sign <INSTALLER_CERT_SHA1> \
  dist/GEDCOM-Navigator.pkg
```

## Step 4 — validate against App Store
```bash
xcrun altool --validate-app -f dist/GEDCOM-Navigator.pkg -t macos \
  -u "<apple-id>" -p "<app-specific-password>"
# then --upload-app to submit, or use the Transporter.app GUI
```
Success here = deliverable (c) proven: a Toga/Briefcase build is App-Store-acceptable.

## What to report back
1. Did `briefcase dev` / `build` produce a launchable sandboxed `.app`?
2. Did the Briefcase-native `-p pkg` path embed a provisioning profile, or did we need the
   hybrid step? (This tells us how much of `build-mac-appstore.sh` we keep vs. retire.)
3. Did `altool --validate-app` pass? Any entitlement/sandbox/profile errors are the real
   findings — paste them and we iterate.

## For the real migration (not this spike)
Point `sources` at the project (`src/`) and set `requires` to the runtime deps **minus
`custom2kinter`, plus `toga`** (cyrtranslit, hebrew, pillow, reportlab, …). Drop the
macOS-only `pyobjc-*`/`certifi` unless still needed. Version must be PEP440 (strip the
git-describe suffix from `gedcom_navigator/__init__.py`).
