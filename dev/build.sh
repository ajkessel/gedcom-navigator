#!/usr/bin/env bash
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1
[[ -e ./dist/ ]] && rm -r ./dist/
[[ -e ./src/gedcom_navigator_gui.py ]] || {
	echo 'Build files not found.'
	exit 1
}
git pull
if command -v msgfmt &>/dev/null; then
	echo 'Compiling translations...'
	find locales -iname "*.po" | while read -r po_file; do
		printf 'Compiling %s...\n' "$po_file"
		mo_file="${po_file%.po}.mo"
		msgfmt -v --use-fuzzy --output-file="${mo_file}" "${po_file}"
	done
else
	echo 'msgfmt not found, skipping translation compilation.'
fi
if [[ $(uname) == "Linux" ]]; then
	echo 'Building for Linux...'
	dev/build-linux.sh "$@"
elif [[ $(uname) == "Darwin" ]]; then
	echo 'Building for macOS...'
	dev/build-mac.sh "$@"
else
	echo 'Platform not recognized. Use build.ps1 for building natively on Windows. Exiting.'
	exit 1
fi
