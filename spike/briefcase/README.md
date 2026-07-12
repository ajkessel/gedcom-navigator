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

**If the profile is missing (expected), do the hybrid** — skip `briefcase package` and
instead manually sign the `briefcase build` output, then build the `.pkg` yourself. The
sequence below is lifted verbatim from `dev/build-mac-appstore.sh` (lines ~100–183),
adapted to Briefcase's bundle layout. Run from `spike/briefcase/`:

```bash
# --- inputs -------------------------------------------------------------------
APP="$(ls -d build/gedcom-navigator/macos/app/*.app | head -1)"   # Briefcase's built bundle
MAIN_EXE="$APP/Contents/MacOS/GEDCOM Navigator"                    # = formal_name (has a space)
ENTITLEMENTS="../../dev/entitlements-appstore.plist"              # reuse the known-good plist
PROFILE="../../dev/gedcom-navigator.provisionprofile"
APP_CERT=<APP_CERT_SHA1>            # 3rd Party Mac Developer Application  (from find-identity)
INST_CERT=<INSTALLER_CERT_SHA1>     # 3rd Party Mac Developer Installer
PKG="dist/GEDCOM-Navigator.pkg"; mkdir -p dist

# --- (optional) only if bundled dylibs point at Homebrew ----------------------
# Briefcase installs wheels that usually vendor their own libs, so this is often a
# no-op — run it only if the sandboxed self-test later fails on /usr/local|/opt/homebrew:
#   ../../dev/fix-dylib-paths.sh "$APP"

# --- embed provisioning profile (must happen BEFORE signing) ------------------
cp "$PROFILE" "$APP/Contents/embedded.provisionprofile"
chmod -R a+rX "$APP"                                   # App Store error 90255 guard
xattr -rd com.apple.quarantine "$APP" 2>/dev/null || true
xattr -c "$APP/Contents/embedded.provisionprofile"

# --- sign bottom-up (‑‑deep breaks on Python .so, so sign nested items first) -
# every .so/.dylib and any file literally named "Python" (the framework binary):
find "$APP" -type f \( -name "*.so" -o -name "*.dylib" -o -name "Python" \) -print0 \
  | while IFS= read -r -d '' f; do codesign --force --sign "$APP_CERT" "$f"; done
# every other executable, with the hardened runtime:
find "$APP" -type f -perm +111 -exec codesign --force --options runtime --sign "$APP_CERT" {} \;
# main executable + whole bundle, WITH the sandbox entitlements (only these two need it):
codesign --force --verbose --sign "$APP_CERT" --entitlements "$ENTITLEMENTS" "$MAIN_EXE"
codesign --force --verbose --sign "$APP_CERT" --entitlements "$ENTITLEMENTS" "$APP"

# --- sandboxed smoke test (mirrors the script's --self-test gate) -------------
"$MAIN_EXE" &   # confirm the signed, sandboxed bundle launches; Ctrl-C / kill after

# --- build the App Store installer .pkg with the INSTALLER cert ---------------
productbuild --component "$APP" /Applications --sign "$INST_CERT" "$PKG"
```

## Step 4 — validate / upload to App Store
Uses the App Store Connect API key your script reads from `~/.appstoreconnect/`
(`apikey.txt`, `apiissuer.txt`, `appid.txt`). Validate first:
```bash
API_KEY=$(cat ~/.appstoreconnect/apikey.txt); API_ISSUER=$(cat ~/.appstoreconnect/apiissuer.txt)
xcrun altool --validate-app -f dist/GEDCOM-Navigator.pkg --type osx \
  --apiKey "$API_KEY" --apiIssuer "$API_ISSUER"
```
Then upload (the exact form from `build-mac-appstore.sh`):
```bash
xcrun altool --upload-package dist/GEDCOM-Navigator.pkg --type osx \
  --apiKey "$API_KEY" --apiIssuer "$API_ISSUER" \
  --apple-id "$(cat ~/.appstoreconnect/appid.txt)" \
  --bundle-id "com.ajkessel.gedcom-navigator" \
  --bundle-version 1.9.18 --bundle-short-version-string 1.9.18
```
A clean `--validate-app` = deliverable (c) proven: a Toga/Briefcase build is
App-Store-acceptable. (Transporter.app is the GUI equivalent if you prefer.)

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
