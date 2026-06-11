# Building and Releasing GEDCOM Navigator

This document covers the automated GitHub Actions build pipeline and the secrets required to operate it. For local build instructions see [DEVELOPMENT.md](DEVELOPMENT.md).

## Overview

Pushing a version tag (e.g. `git tag v1.9.16 && git push origin v1.9.16`) triggers a parallel multi-platform release with all jobs and all artifacts uploaded to a GitHub release.

You can also run the workflow manually from the **Actions** tab using **Run workflow**:
- **Default** (all inputs unchecked): does nothing — check the inputs you want to run
- Check individual job inputs (`Build Linux`, `Build Windows`, etc.) to run only those
- Check `Create GitHub release` to publish artifacts to a GitHub release (requires at least the three binary builds to be checked)

This is useful for testing a single build, rebuilding PyPI, or submitting to App Store without rebuilding everything.

### Jobs

| Job | Runner | Trigger | Output |
|-----|--------|---------|--------|
| `build-linux` | ubuntu-latest | always | `gedcom-navigator-linux.zip` |
| `build-windows` | windows-latest | always | `gedcom-navigator-windows-portable.zip`, `gedcom-navigator-windows-installer.exe` |
| `build-macos` | macos-latest | always | `gedcom-navigator-mac.zip` (notarized) |
| `build-macos-appstore` | macos-latest | manual only (workflow_dispatch) | submits `.pkg` to App Store Connect |
| `build-pypi` | ubuntu-latest | tag push only | uploads wheel + sdist to PyPI |
| `release` | ubuntu-latest | tag push only | creates GitHub release, uploads all artifacts |

The three binary build jobs (Linux, Windows, macOS) run in parallel. `release` waits for all three to succeed before creating the GitHub release. `build-pypi` runs in parallel with everything else but does not gate the release.

**App Store builds:** The `build-macos-appstore` job uses a pre-built patched Python from [fix-tk-for-appstore](https://github.com/ajkessel/fix-tk-for-appstore/releases) that has the forbidden App Store symbol removed from Tk. The job is available via manual `workflow_dispatch` with `Build and submit to Mac App Store` checked.

On a manual `workflow_dispatch` run only the three binary build jobs execute (no release, no App Store submission, no PyPI upload), which is safe for testing.

---

## Secrets

All secrets are set in **GitHub → Settings → Secrets and variables → Actions → Secrets**.

### macOS Developer ID signing

These are used to sign and notarize the direct-download macOS build.

---

#### `APPLE_DEVELOPER_CERT_P12`

A base64-encoded PKCS#12 file containing your **Developer ID Application** certificate and its private key.

**How to obtain:**

1. Open **Keychain Access** on your Mac.
2. Under **My Certificates**, find the certificate named *Developer ID Application: Your Name (TEAMID)*.
3. Right-click it → **Export** → choose `.p12` format → set an export password (remember this for `APPLE_DEVELOPER_CERT_PASSWORD`).
4. Base64-encode the exported file and copy to clipboard:
   ```bash
   base64 -i ~/Downloads/DeveloperIDApplication.p12 | pbcopy
   ```
5. Go to GitHub → Settings → Secrets and variables → Actions → New repository secret.
6. Name: `APPLE_DEVELOPER_CERT_P12`
7. Paste the value (should start with `MIIJrwIBA` or similar) → Save.

If you don't have a Developer ID Application certificate, request one at [developer.apple.com/account/resources/certificates](https://developer.apple.com/account/resources/certificates/add) under **Software** → **Developer ID Application**.

---

#### `APPLE_DEVELOPER_CERT_PASSWORD`

The export password you set when exporting the `.p12` above. This is **not** your macOS login password or Apple ID password — it is only the password used to protect the exported certificate file.

---

#### `APPLE_NOTARIZATION_APPLE_ID`

Your Apple ID email address (e.g. `you@example.com`). This is the account that owns the Developer ID certificate.

---

#### `APPLE_NOTARIZATION_PASSWORD`

An **app-specific password** for your Apple ID, used by `notarytool` to submit builds for notarization.

**How to obtain:**

1. Go to [appleid.apple.com](https://appleid.apple.com) and sign in.
2. Under **Sign-In and Security → App-Specific Passwords**, click **Generate an app-specific password**.
3. Give it a name like `notarytool-ci` and copy the generated password (format: `xxxx-xxxx-xxxx-xxxx`).

Do not use your regular Apple ID password here — Apple will reject it.

---

#### `APPLE_NOTARIZATION_TEAM_ID`

Your Apple Developer **Team ID** (a 10-character alphanumeric string, e.g. `4GT4UKXZ4V`).

**How to find it:**

- Sign in at [developer.apple.com/account](https://developer.apple.com/account) and look under **Membership Details → Team ID**.
- Or: in Keychain Access, the Team ID is the part in parentheses at the end of the certificate name: *Developer ID Application: Your Name (**TEAMID**)*.

---

### macOS App Store submission

These are used only by the `build-macos-appstore` job. If you do not distribute through the Mac App Store, these secrets can be left unset and the job will fail gracefully (it is not gated by the main release).

---

#### `APPLE_APPSTORE_CERT_P12`

Base64-encoded PKCS#12 for the **3rd Party Mac Developer Application** certificate.

**How to obtain:**

1. Open **Keychain Access** on your Mac and find the certificate named *3rd Party Mac Developer Application: Your Name (TEAMID)*.
2. Right-click it → **Export** → choose `.p12` format → set an export password.
3. Base64-encode the `.p12` file:
   ```bash
   base64 -i "3rd Party Mac Developer Application.p12" | pbcopy
   ```
4. Paste the output into the GitHub secret. The secret should start with `MIIJrwIBA` or similar.

(Request the cert at [developer.apple.com/account/resources/certificates](https://developer.apple.com/account/resources/certificates/add) under **Software → Mac App Distribution** if you don't have one.)

---

#### `APPLE_APPSTORE_CERT_PASSWORD`

Export password for the App Store application `.p12`.

---

#### `APPLE_APPSTORE_INSTALLER_CERT_P12`

Base64-encoded PKCS#12 for the **3rd Party Mac Developer Installer** certificate.

**How to obtain:**

1. Open **Keychain Access** and find *3rd Party Mac Developer Installer: Your Name (TEAMID)*.
2. Right-click → **Export** → `.p12` format → set an export password → save.
3. Base64-encode and copy:
   ```bash
   base64 -i "3rd Party Mac Developer Installer.p12" | pbcopy
   ```
4. Paste into GitHub secret `APPLE_APPSTORE_INSTALLER_CERT_P12`.

(Request at [developer.apple.com/account/resources/certificates](https://developer.apple.com/account/resources/certificates/add) under **Software → Mac Installer Distribution** if missing.)

---

#### `APPLE_APPSTORE_INSTALLER_CERT_PASSWORD`

Export password for the App Store installer `.p12`.

---

#### `APPLE_APPSTORE_PROVISIONING_PROFILE`

Base64-encoded `.provisionprofile` file for the app.

**How to obtain:**

1. Go to [developer.apple.com/account/resources/profiles](https://developer.apple.com/account/resources/profiles/add).
2. Select **Mac App Store → Mac App Distribution**.
3. Choose your App ID (`com.ajkessel.gedcom-navigator`) and your Mac App Distribution certificate.
4. Download the generated `.provisionprofile` file.
5. Base64-encode it:
   ```bash
   base64 -i gedcom-navigator.provisionprofile | pbcopy
   ```

---

#### `APP_STORE_CONNECT_KEY_ID`

The key ID of an **App Store Connect API key** (an alphanumeric string like `ABC123DEF4`).

**How to obtain:** See `APP_STORE_CONNECT_API_KEY` below.

---

#### `APP_STORE_CONNECT_ISSUER_ID`

The issuer ID associated with your App Store Connect API key (a UUID, e.g. `57246542-96fe-1a63-e053-0824d011072a`).

**How to obtain:** See `APP_STORE_CONNECT_API_KEY` below.

---

#### `APP_STORE_CONNECT_API_KEY`

The contents of the `.p8` private key file for your App Store Connect API key.

**How to obtain:**

1. In [App Store Connect](https://appstoreconnect.apple.com/access/integrations/api), go to **Users and Access → Integrations → App Store Connect API**.
2. Click **+** to generate a new key. Give it the **Developer** role (sufficient for package uploads).
3. Download the `.p8` file — **you can only download it once**.
4. Copy the file contents (it starts with `-----BEGIN PRIVATE KEY-----`).
5. Note the **Key ID** and **Issuer ID** shown on the same page.

Set the `.p8` file contents as `APP_STORE_CONNECT_API_KEY`, the Key ID as `APP_STORE_CONNECT_KEY_ID`, and the Issuer ID as `APP_STORE_CONNECT_ISSUER_ID`.

---

#### `APP_STORE_CONNECT_APP_ID`

The bundle identifier for the app: `com.ajkessel.gedcom-navigator`.

---

### Windows code signing

These are used by the `build-windows` job for **Azure Trusted Signing**. If none of the three are set, the build will fall back to a self-signed local certificate (produces unsigned-looking binaries but still produces a working installer).

---

#### `AZURE_CLIENT_ID`

The **Client ID** (also called Application ID) of the Azure service principal used for signing.

**How to obtain:**

1. In the [Azure portal](https://portal.azure.com), go to **Microsoft Entra ID → App registrations → New registration**.
2. Give it a name (e.g. `gedcom-navigator-signing`), leave other settings as default, and register.
3. Copy the **Application (client) ID** — this is `AZURE_CLIENT_ID`.

---

#### `AZURE_CLIENT_SECRET`

A client secret for the service principal above.

**How to obtain:**

1. In the app registration, go to **Certificates & secrets → Client secrets → New client secret**.
2. Set an expiry and click **Add**.
3. Copy the **Value** immediately — it is only shown once.

---

#### `AZURE_TENANT_ID`

The **Tenant ID** (Directory ID) of your Azure Active Directory.

**How to obtain:** In the Azure portal, go to **Microsoft Entra ID → Overview**. The **Tenant ID** is shown at the top.

**Granting signing permissions:**

After creating the service principal, it must be assigned the **Artifact Signing Certificate Profile Signer** role on the Trusted Signing account. Run once:

```bash
SCOPE=$(az resource list \
  --resource-type Microsoft.CodeSigning/codeSigningAccounts \
  --query "[?name=='GEDCOM-Navigator'].id | [0]" -o tsv)

az role assignment create \
  --assignee <AZURE_CLIENT_ID> \
  --role "Artifact Signing Certificate Profile Signer" \
  --scope "$SCOPE"
```

Role assignments can take up to 30 minutes to propagate.

---

### PyPI

---

#### `PYPI_TOKEN`

An API token for your PyPI account, used by `twine` to upload the wheel and source distribution.

**How to obtain:**

1. Sign in at [pypi.org](https://pypi.org) and go to **Account Settings → API tokens → Add API token**.
2. Scope the token to the `gedcom-navigator` project (or leave it account-scoped for the first upload).
3. Copy the token (starts with `pypi-`).

---

## Local builds

The existing local build scripts continue to work unchanged alongside the CI workflow. See [DEVELOPMENT.md](DEVELOPMENT.md) for `dev/build.sh`, `dev/build.ps1`, and the multi-platform `dev/build-and-release.sh` orchestrator.

**Linux system dependencies:** If building on Linux locally, install `python3-tk` (provides the `tkinter` module required by tests):
```bash
sudo apt-get install python3-tk python3-dev libcairo2-dev
```

## Exporting certificates as base64

A quick reference for the base64 export step required by several secrets above:

```bash
# macOS/Linux
base64 -i path/to/file.p12 | pbcopy      # macOS — copies to clipboard
base64 -i path/to/file.p12               # Linux — prints to stdout

# PowerShell (Windows)
[Convert]::ToBase64String([IO.File]::ReadAllBytes("path\to\file.p12"))
```

Paste the resulting string (no line breaks needed — GitHub handles it) directly into the secret value field.

## Troubleshooting

### "Unable to decode the provided data" on App Store build

This means the base64-encoded P12 secret is invalid. Check:

1. **Did you base64-encode the actual `.p12` file?** Not the filename, not a screenshot — the binary `.p12` file itself.
   ```bash
   # ✓ Correct
   base64 -i ~/Downloads/certificate.p12
   
   # ✗ Wrong (encodes the text "certificate.p12", not the file)
   echo "certificate.p12" | base64
   ```

2. **Is the secret complete?** The base64 output should be a single long string starting with `MIIJrwIBA` or similar. If it's short or empty, the export failed.

3. **Did you use the correct export password?** When exporting from Keychain, you set an export password (different from your Mac login password). Use that same password for the `APPLE_*_CERT_PASSWORD` secret.

4. **Verify locally before pushing secrets:**
   ```bash
   # Decode and check file type
   echo "YOUR_BASE64_SECRET_HERE" | base64 -D > test.p12
   file test.p12  # Should show: "data" or similar (binary format)
   openssl pkcs12 -in test.p12 -password pass:YOUR_EXPORT_PASSWORD -noout  # Should succeed
   rm test.p12
   ```

If the `openssl` command fails, the P12 is invalid or the password is wrong. Re-export from Keychain and try again.

## App Store Builds in GitHub Actions

The `build-macos-appstore` job is fully automated using a pre-built patched Python downloaded from [https://github.com/ajkessel/fix-tk-for-appstore/releases](https://github.com/ajkessel/fix-tk-for-appstore/releases).

**How it works:**
1. The workflow downloads the pre-built patched Python tarball
2. Extracts it to `/Library/Frameworks/Python.framework`
3. Verifies that the Tk framework no longer contains the forbidden `_NSWindowDidOrderOnScreenNotification` symbol
4. Builds and submits the app to App Store Connect

**To use it:** On tag push or manual `workflow_dispatch`, check the `Build and submit to Mac App Store` input to include the App Store job in your release.

**Updating the patched Python version:** If you release a new version of patched Python in the [fix-tk-for-appstore](https://github.com/ajkessel/fix-tk-for-appstore/releases) repo, update the download URL in `.github/workflows/release.yml`:

```yaml
PYTHON_URL="https://github.com/ajkessel/fix-tk-for-appstore/releases/download/VERSION/patched-python-VERSION-macos-universal2.tar.gz"
```
