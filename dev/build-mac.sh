#!/bin/bash
if [[ "$OSTYPE" != "darwin"* ]]; then
	echo "This script is intended to be run on macOS."
	echo "${OSTYPE} detected, exiting."
	exit 1
fi
if [[ -z "${CI:-}" && "$STDBUF_ACTIVE" != "1" ]]; then
        export STDBUF_ACTIVE=1
        exec stdbuf -oL "$0" "$@"
fi
output_file="gedcom-navigator-mac.zip"
git_branch="main"
while getopts "hnco:b:" opt; do
	case $opt in
	h)
		echo "Usage: $0 [-h] [-n] [-c] [-o] [-b]"
		echo "  -h  Show this help message and exit"
		echo "  -n  Dry run: build the app but skip notarization, stapling, and cross-arch universal build steps"
		echo "  -c  Clean build: remove virtual environment and pyenv versions before building"
		echo "  -o  Specify output file name (default: gedcom-navigator-mac.zip)"
		echo "  -b  Specify git branch to build (default: main)"
		exit 0
		;;
	n) DRY=true ;;
	c) CLEAN=true ;;
	o) output_file=$OPTARG ;;
	b) git_branch=$OPTARG ;;
	*)
		echo "Invalid option"
		exit 1
		;;
	esac
done
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1
[[ -z "${CI:-}" ]] && exec > >(sed 's/\x1b\[[0-9;]*m//g' | tee -a build-mac.log) 2>&1
python3 dev/update_version.py
echo 'Building for macOS...'
[[ "$CLEAN" ]] && {
	echo 'Warning: this will delete the current .venv and any .pyenv in your home folder.'
	read -t 5 -n 1 -s -r -p "Press any key to continue or q to exit (waiting 5s)..." x
	[ "${x}" == "q" ] && exit 1
	rm -r ./.venv "${HOME}/.pyenv"
}
if [[ -z "${CI:-}" ]]; then
	if [[ -e "${HOME}/.config/p" ]]; then
		echo 'Local keychain password found, unlocking keychain...'
		security unlock-keychain -p "$(cat "${HOME}"/.config/p)" "${HOME}/Library/Keychains/login.keychain-db"
	else
		echo 'Password file not found at ~/.config/p, skipping automatic keychain unlock.'
		security unlock-keychain "${HOME}/Library/Keychains/login.keychain-db"
	fi
fi
export PATH="/usr/local/bin:$PATH"
if command -v brew >/dev/null 2>&1; then
	brew_prefix=$(brew --prefix python)
	export PATH="$brew_prefix/libexec/bin:$PATH"
else
	echo 'homebrew not found, we will still try to build but this script has not been tested on MacOS without brew.'
fi

# preference is for universal2 python from python.org
# alternatively, set up pyenv environment
if [ -e "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14" ]; then
	export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin/:${PATH}"
elif [ -e "/Library/Frameworks/Python.framework/Versions/current/bin/python3" ]; then
	export PATH="/Library/Frameworks/Python.framework/Versions/current/bin/:${PATH}"
else
	echo 'Python from python.org not found, attempting to set up pyenv...'
	command -v pyenv || {
		echo 'pyenv missing, attempting to install from homebrew...'
		brew install pyenv
	}
	export PYENV_ROOT="$HOME/.pyenv"
	[[ -e "${PYENV_ROOT}/shims/python3.14" ]] || {
		echo 'Installing pyenv for python 3.14'
		mkdir -p "${PYENV_ROOT}"
		eval "$(pyenv init -)"
		pyenv install 3.14
		pyenv global 3.14
	}
	eval "$(pyenv init -)"
fi
./dev/generate-icns.sh ./icons/gedcom_navigator.svg || {
	echo 'Failed to generate ICNS file.'
	exit 1
}
[[ -e .venv/bin/activate ]] || {
	echo 'Creating virtual environment...'
	python3 -m venv .venv --prompt "gedcom-navigator" || {
		echo 'Failed to create virtual environment.'
		exit 1
	}
}
# shellcheck disable=SC1091
source .venv/bin/activate || {
	echo 'Failed to activate virtual environment.'
	exit 1
}
# It's necessary to build from source and disable default-const-init-var-unsafe due to recent xcode changes
# issue filed at https://github.com/ronaldoussoren/pyobjc/issues/673
if clang --version | grep -q ' version 21'; then
	echo 'Detected Xcode 26/CLang 21, adding -Wno-error=default-const-init-var-unsafe to CFLAGS.'
	export myflags="-Wno-error=default-const-init-var-unsafe"
else
	echo 'Xcode less than 15, skipping -Wno-error=default-const-init-var-unsafe.'
fi
# pip download --platform requires all four override flags together; mixing them
# produces generic 'none-none' tags that match no compiled wheel.  Query PyPI's
# JSON API directly to find and fetch the universal2 Pillow wheel, then install
# it with --force-reinstall so the main deps pass below leaves it alone.
python3 - << 'PYEOF'
import json, os, subprocess, sys, urllib.request

cp = f"cp{sys.version_info.major}{sys.version_info.minor}"
print(f"Fetching universal2 Pillow wheel for {cp} from PyPI...")
with urllib.request.urlopen("https://pypi.org/pypi/pillow/json") as r:
    data = json.loads(r.read())
latest = data["info"]["version"]
url = name = None
for f in data["releases"].get(latest, []):
    fn = f["filename"]
    if "universal2" in fn and cp in fn and fn.endswith(".whl"):
        url, name = f["url"], fn
        break
if not url:
    print(f"ERROR: no universal2 Pillow {latest} wheel for {cp}", file=sys.stderr)
    sys.exit(1)
print(f"Downloading {name}...")
path = f"/tmp/{name}"
urllib.request.urlretrieve(url, path)
subprocess.check_call([sys.executable, "-m", "pip", "install",
                       path, "--no-deps", "--force-reinstall"])
os.unlink(path)
PYEOF
[ $? -eq 0 ] || { echo 'Failed to install universal2 Pillow wheel.'; exit 1; }
env CFLAGS="${myflags:-}" ARCHFLAGS="-arch arm64 -arch x86_64" pip install -r ./dev/requirements-dev.txt --no-binary pyobjc-core,pyobjc-framework-Cocoa,pyobjc-framework-CoreServices || {
	echo 'Failed to install dependencies.'
	exit 1
}
echo 'Patching ctktooltip... (see https://github.com/Akascape/CTkToolTip/issues/20 for details)'
patch -d "${VIRTUAL_ENV}/lib/site-packages/" -N -p1 <./dev/ctk_tooltip.patch || {
	echo 'Failed to patch ctktooltip, may have been applied already. Proceeding anyway...'
}
echo 'Running unit tests...'
pytest -v --tb=short --disable-warnings || {
	echo 'Unit tests failed. Exiting.'
	exit 1
}
python3 ./dev/generate_icon.py ./icons/gedcom_navigator.svg || {
	echo 'Warning: Failed to generate ICO file (cairosvg not available). Continuing anyway — ICO is not needed on macOS.'
}
# dry-run mode does not need to compile universal2 binary
[ "${DRY}" ] && {
	target_arch=$(uname -m)
	export target_arch
}
pyinstaller --noconfirm ./dev/gedcom_navigator_cli.spec || {
	echo 'pyinstaller failed to build CLI.'
	exit 1
}
pyinstaller --noconfirm ./dev/gedcom_navigator_gui.spec || {
	echo 'pyinstaller failed to build GUI.'
	exit 1
}
[ -d "dist" ] || {
	echo 'Cannot find dist build folder.'
	exit 1
}
# Rewrite absolute Homebrew dylib paths (e.g. libxcb -> /usr/local/.../libXau)
# to @rpath so the bundled copies load under the App Sandbox.  Must run before
# signing/notarization, as install_name_tool invalidates signatures.
./dev/fix-dylib-paths.sh "dist/gedcom-navigator.app" || {
	echo 'Failed to rewrite bundled dylib paths.'
	# Remove the half-built bundle so a later App Store build cannot silently
	# pick up a dist that still references absolute Homebrew paths.
	rm -rf "dist/gedcom-navigator.app"
	exit 1
}
# install_name_tool invalidates the signatures PyInstaller applied, so re-sign
# the rewritten Mach-O files and re-seal the bundle (hardened runtime +
# entitlements) before notarization, which rejects invalidly-signed code.
DEV_ID=$(security find-identity -v -p codesigning 2>/dev/null |
	grep "Developer ID Application" | grep -Eo '[0-9A-Z]{40}' | head -1)
if [ -n "${DEV_ID}" ]; then
	echo 'Re-signing dylibs invalidated by path rewrite...'
	resign_failed=0
	while IFS= read -r -d '' f; do
		codesign --force --timestamp --options runtime --sign "${DEV_ID}" "$f" || resign_failed=1
	done < <(find "dist/gedcom-navigator.app/Contents/Frameworks" \
		\( -name "*.dylib" -o -name "*.so" \) -print0)
	[ "${resign_failed}" = "0" ] || {
		echo 'Re-signing of rewritten dylibs failed.'
		exit 1
	}
	codesign --force --timestamp --options runtime \
		--entitlements ./dev/entitlements.plist \
		--sign "${DEV_ID}" "dist/gedcom-navigator.app" || {
		echo 'Re-signing of app bundle failed.'
		exit 1
	}
else
	echo 'No Developer ID Application identity found; cannot re-sign after dylib rewrite.'
	[ "$DRY" ] || exit 1
fi
[ "$DRY" ] && exit 0
ditto -c -k --sequesterRsrc --keepParent "dist/gedcom-navigator.app" "${output_file}" || {
	echo 'Cannot build zip file.'
	exit 1
}
if [[ -n "${APPLE_NOTARIZATION_APPLE_ID:-}" ]]; then
	echo 'Setting up notarytool credentials from environment...'
	xcrun notarytool store-credentials notarytool-profile \
		--apple-id "${APPLE_NOTARIZATION_APPLE_ID}" \
		--password "${APPLE_NOTARIZATION_PASSWORD}" \
		--team-id "${APPLE_NOTARIZATION_TEAM_ID}" || {
		echo 'Failed to store notarytool credentials.'
		exit 1
	}
fi
xcrun notarytool submit "${output_file}" --keychain-profile "notarytool-profile" --wait || {
	echo 'Notarytool failed.'
	exit 1
}
xcrun stapler staple ./dist/gedcom-navigator.app || {
	echo 'Stapler failed.'
	exit 1
}
rm "${output_file}"
ditto -c -k --sequesterRsrc --keepParent "dist/gedcom-navigator.app" "${output_file}" || {
	echo 'Cannot build notarized zip file.'
	exit 1
}
mv "${output_file}" dist/
