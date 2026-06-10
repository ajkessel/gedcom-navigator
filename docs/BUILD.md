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
| `build-macos-appstore` | macos-latest | tag push only | submits `.pkg` to App Store Connect |
| `build-pypi` | ubuntu-latest | tag push only | uploads wheel + sdist to PyPI |
| `release` | ubuntu-latest | tag push only | creates GitHub release, uploads all artifacts |

The three binary build jobs run in parallel. `release` waits for all three to succeed before creating the GitHub release. `build-macos-appstore` and `build-pypi` run in parallel with everything else but do not gate the release.

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
3. Right-click it → **Export** → choose `.p12` format.
4. Set an export password (this becomes `APPLE_DEVELOPER_CERT_PASSWORD`).
5. Base64-encode the file:
   ```bash
   base64 -i DeveloperIDApplication.p12 | pbcopy
   ```
6. Paste the copied text as the secret value.

If you do not have a Developer ID Application certificate, request one at [developer.apple.com/account/resources/certificates](https://developer.apple.com/account/resources/certificates/add) under **Software** → **Developer ID Application**.

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

**How to obtain:** Same export process as the Developer ID cert above, but select the certificate named *3rd Party Mac Developer Application: Your Name (TEAMID)*. Request one at [developer.apple.com/account/resources/certificates](https://developer.apple.com/account/resources/certificates/add) under **Software → Mac App Distribution** if you do not have one.

---

#### `APPLE_APPSTORE_CERT_PASSWORD`

Export password for the App Store application `.p12`.

---

#### `APPLE_APPSTORE_INSTALLER_CERT_P12`

Base64-encoded PKCS#12 for the **3rd Party Mac Developer Installer** certificate.

**How to obtain:** Export *3rd Party Mac Developer Installer: Your Name (TEAMID)* from Keychain Access. Request one at the certificates page under **Software → Mac Installer Distribution**.

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
