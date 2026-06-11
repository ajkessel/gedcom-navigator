#!/bin/bash
if [[ "$OSTYPE" != "darwin"* ]]; then
	echo 'This script is intended to be run on macOS.'
	exit 1
fi
# this is necessary to keep screen buffer up to date
# while logging to file
if [[ -z "${CI:-}" && "$STDBUF_ACTIVE" != "1" ]]; then
        export STDBUF_ACTIVE=1
        exec stdbuf -oL "$0" "$@"
fi
git_branch="main"
while getopts "hnb:" opt; do
	case $opt in
	h)
		echo "Usage: $0 [-h] [-n] [-b]"
		echo "  -b  Specify git branch to build (default: main)"
		exit 0
		;;
	n) DRY=true ;;
	b) git_branch=$OPTARG ;;
	*)
		echo "Invalid option"
		exit 1
		;;
	esac
done
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.."
[[ -z "${CI:-}" ]] && exec > >(sed 's/\x1b\[[0-9;]*m//g' | tee -a build-mac-appstore.log) 2>&1
if [[ -z "${CI:-}" ]]; then
	git switch "${git_branch}" || {
		echo "Error: could not switch to ${git_branch}. Aborting."
		exit 1
	}
fi
VERSION=$(grep __version__ gedcom_navigator/__init__.py | grep -o '[0-9]\+\.[0-9]\+\(\.[0-9]\+\)\+')
x=0
if grep -s xcrun build-mac-appstore.log | grep -qF "${VERSION}"; then
	echo "Prior build for ${VERSION} found in build-mac-app-store.log; do you need to bump version?"
	echo "Clear build-mac-app-store.log if you want to re-submit with ${VERSION}."
	exit 1
fi
echo '--------------------------------'
echo "Building app version ${VERSION} for Mac App Store on $(date)."
echo '--------------------------------'
if nm -pa /Library/Frameworks/Python.framework/Versions/Current/Frameworks/Tk.framework/Versions/Current/Tk | grep -iq _nswindowdidorder; then
	echo "Error, forbidden symbol _NSWindowDidOrderOnScreenNotification exists in Tk framework. This will trigger App Store rejection."
	echo "Patch available at https://github.com/ajkessel/fix-tk-for-appstore "
	exit 1
fi
echo "_NSWindowDidOrderOnScreenNotification appears clear from Tk framework, thus avoiding potential App Store rejection."
[[ -z "${CI:-}" ]] && security unlock-keychain -p "$(cat ~/.config/p)" ~/Library/Keychains/login.keychain-db
if [[ ! -e 'dist/gedcom-navigator.app' ]]; then
	echo 'Built app not found, building now.'
	./dev/build.sh -b "${git_branch}"
fi
# Search in CI keychain if set, otherwise search all keychains
KEYCHAIN_ARG=""
if [[ -n "${KEYCHAIN_PATH:-}" ]]; then
	KEYCHAIN_ARG="'${KEYCHAIN_PATH}'"
	echo "Searching for certificates in ${KEYCHAIN_PATH}"
fi

AS_APP_CERT=$(eval "security find-identity -v -p codesigning ${KEYCHAIN_ARG}" 2>/dev/null |
	grep "3rd Party Mac Developer Application" |
	grep -Eo '[0-9A-Z]{40}' | head -1)
AS_INST_CERT=$(eval "security find-identity -v ${KEYCHAIN_ARG}" 2>/dev/null |
	grep "3rd Party Mac Developer Installer" |
	grep -Eo '[0-9A-Z]{40}' | head -1)

if [[ -n "${AS_APP_CERT}" && -n "${AS_INST_CERT}" ]]; then
	echo "Building App Store package..."
	APP_SRC="dist/gedcom-navigator.app"
	APP_AS="dist/gedcom-navigator-appstore.app"
	PKG="dist/gedcom-navigator.pkg"

	# Work from a clean copy so the notarised Developer-ID build is untouched
	rm -rf "${APP_AS}"
	cp -R "${APP_SRC}" "${APP_AS}"

	# Rewrite absolute Homebrew dylib paths to @rpath on our own copy rather than
	# trusting that build-mac.sh already did so.  The source dist may have been
	# built by any means (or left half-built if an earlier build-mac.sh rewrite
	# failed), and the App Sandbox blocks /usr/local|/opt/homebrew, so an
	# unrewritten dylib silently breaks graph image copy/save.  install_name_tool
	# invalidates signatures, but everything below is re-signed anyway.
	./dev/fix-dylib-paths.sh "${APP_AS}" || {
		echo 'Failed to rewrite bundled dylib paths for App Store build.'
		exit 1
	}

	# Embed provisioning profile (required for TestFlight eligibility).
	PROVISION_PROFILE="${HOME}/Library/MobileDevice/Provisioning Profiles/gedcom-navigator.provisionprofile"
	if [[ ! -f "${PROVISION_PROFILE}" ]]; then
		PROVISION_PROFILE="$(dirname "$0")/gedcom-navigator.provisionprofile"
	fi
	if [[ ! -f "${PROVISION_PROFILE}" ]]; then
		PROVISION_PROFILE="dev/gedcom-navigator.provisionprofile"
	fi
	if [[ -f "${PROVISION_PROFILE}" ]]; then
		cp "${PROVISION_PROFILE}" "${APP_AS}/Contents/embedded.provisionprofile"
		echo "Embedded provisioning profile from: ${PROVISION_PROFILE}"
	else
		echo "WARNING: No provisioning profile found; app will not be TestFlight-eligible."
		echo "  Place gedcom-navigator.provisionprofile in ~/Library/MobileDevice/Provisioning Profiles/ or dev/"
	fi
	#
	# Ensure all files are readable by non-root users (App Store error 90255).
	chmod -R a+rX "${APP_AS}"
	# Ensure no files are quarantined
	xattr -rd com.apple.quarantine "${APP_AS}"
	[ -e "${APP_AS}/Contents/embedded.provisionprofile" ] && xattr -c "${APP_AS}/Contents/embedded.provisionprofile"

	# Re-sign bottom-up with the App Store identity.
	# --deep triggers errSecInternalComponent on Python .so extension modules,
	# so sign nested components individually first, then the executable, then
	# the bundle. The sandbox entitlement only needs to be on the main executable.
	while IFS= read -r -d '' f; do
		codesign --force --sign "${AS_APP_CERT}" "$f" || {
			echo "App Store code-signing failed on: $f"
			exit 1
		}
	done < <(find "${APP_AS}" -type f \( -name "*.so" -o -name "*.dylib" -o -name 'Python' \) -print0)

	find "${APP_AS}" -type f -perm +111 -exec codesign --force --options runtime --sign "${AS_APP_CERT}" {} \;

	echo "Signing provisioning profile."
	codesign --force --verbose \
		--sign "${AS_APP_CERT}" \
		--entitlements "./dev/entitlements-appstore.plist" \
		"${APP_AS}/Contents/embedded.provisionprofile" || {
		echo "App Store code-signing of provision profile failed."
		exit 1
	}

	echo "Signing entitlements."
	codesign --force --verbose \
		--sign "${AS_APP_CERT}" \
		--entitlements "./dev/entitlements-appstore.plist" \
		"${APP_AS}/Contents/MacOS/gedcom-navigator" || {
		echo "App Store code-signing of main executable failed."
		exit 1
	}

	codesign --force --verbose \
		--sign "${AS_APP_CERT}" \
		--entitlements "./dev/entitlements-appstore.plist" \
		"${APP_AS}" || {
		echo "App Store code-signing of bundle failed."
		exit 1
	}

	# Run the headless self-test against the now-signed, sandboxed bundle.
	# The sandbox entitlement is embedded and signed, so this process runs under
	# the App Sandbox and catches sandbox-only failures (e.g. a dylib still
	# pointing at /usr/local) before the package is ever uploaded.
	echo "Running sandboxed self-test..."
	"${APP_AS}/Contents/MacOS/gedcom-navigator" --self-test || {
		echo "Sandboxed self-test FAILED; refusing to build/upload package."
		echo "  Usually a bundled dylib still references an absolute Homebrew"
		echo "  path (/usr/local or /opt/homebrew). See dev/fix-dylib-paths.sh."
		exit 1
	}

	productbuild \
		--component "${APP_AS}" /Applications \
		--sign "${AS_INST_CERT}" \
		"${PKG}" || {
		echo "productbuild failed."
		exit 1
	}

	[ "${DRY}" ] || rm -rf "${APP_AS}"
	echo "App Store package created: ${PKG}"
else
	echo "No App Store signing certificates found; skipping pkg creation."
	[[ -z "${AS_APP_CERT}" ]] && echo "  Missing: 3rd Party Mac Developer Application"
	[[ -z "${AS_INST_CERT}" ]] && echo "  Missing: 3rd Party Mac Developer Installer"
	exit 1
fi
echo "Submitting App Store package to app store..."
apiKey=$(cat "${HOME}/.appstoreconnect/apikey.txt")
apiIssuer=$(cat "${HOME}/.appstoreconnect/apiissuer.txt")
appid=$(cat "${HOME}/.appstoreconnect/appid.txt")
[ -z "${apiKey}" ] || [ -z "${apiIssuer}" ] || [ -z "${VERSION}" ] || [ -z "${appid}" ] && {
	echo "Need apiKey, apiIssuer, version, and appid to be set for app store upload."
	exit 1
}
[ "${DRY}" ] || { 
  xcrun altool --upload-package "dist/gedcom-navigator.pkg" \
             --type osx \
             --apiKey "${apiKey}" \
             --apiIssuer "${apiIssuer}" \
             --apple-id "${appid}" \
             --bundle-id "com.ajkessel.gedcom-navigator" \
             --bundle-version "${VERSION}" \
             --bundle-short-version-string "${VERSION}"

}
