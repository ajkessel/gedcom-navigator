#!/usr/bin/env bash
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1
[[ -e ./dist/ ]] && rm -r ./dist/
[[ -e ./src/gedcom_navigator_gui.py ]] || {
	echo 'Build files not found.'
	exit 1
}
if [[ "$STDBUF_ACTIVE" != "1" ]]; then
        export STDBUF_ACTIVE=1
        exec stdbuf -oL "$0" "$@"
fi
git_branch=$(git branch --show-current)
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
	b) new_git_branch=$OPTARG ;;
	*)
		echo "Invalid option"
		exit 1
		;;
	esac
done
if [ "${git_branch}" != "main" ] && [ -z "${new_git_branch}" ]; then
	echo "Current git branch is ${git_branch}. Do you want to build from this branch? (y/n)"
	read -r answer
	if [[ "$answer" != "y" ]]; then
		echo "Exiting."
		exit 0
	fi
fi
[ -n "${new_git_branch}" ] && git_branch="${new_git_branch}"
git switch "$git_branch" || {
	echo "Failed to switch to git branch $git_branch. Exiting."
	exit 1
}
git pull || {
	echo "Failed to pull latest changes from git branch $git_branch. Exiting."
	exit 1
}
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
