#!/bin/bash
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
	echo 'This script is intended to be run on Linux.'
	echo "${OSTYPE} detected, exiting."
	exit 1
fi
# this is necessary to keep screen buffer up to date
# while logging to file
if [[ "$STDBUF_ACTIVE" != "1" ]]; then
        export STDBUF_ACTIVE=1
        exec stdbuf -oL "$0" "$@"
fi
output_file="gedcom-navigator-linux.zip"
git_branch="main"
while getopts "hnco:b:" opt; do
	case $opt in
	h)
		echo "Usage: $0 [-h] [-n] [-c] [-o] [-b]"
		echo "  -h  Show this help message and exit"
		echo "  -n  Dry run: build the app but skip signing (no effect on Linux)"
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
exec > >(sed 's/\x1b\[[0-9;]*m//g' | tee -a build-linux.log) 2>&1
[[ "$CLEAN" ]] && [[ -e ".venv" ]] && rm -r ".venv"
[[ -e ".venv/bin/activate" ]] || {
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
pip install -r ./dev/requirements-dev.txt || {
	echo 'Failed to install dependencies.'
	exit 1
}
echo 'Patching ctktooltip... (see https://github.com/Akascape/CTkToolTip/issues/20 for details)'
patch -d "${VIRTUAL_ENV}/lib/site-packages/" -N -p1 < ./dev/ctk_tooltip.patch || {
	echo 'Failed to patch ctktooltip, may have been applied already. Proceeding anyway...'
}
echo 'Running unit tests...'
pytest -v --tb=short --disable-warnings || {
	echo 'Unit tests failed. Exiting.'
	exit 1
}
python3 ./dev/generate_icon.py ./icons/gedcom_navigator.svg || {
	echo 'Failed to generate ICO file.'
	exit 1
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
pushd dist || exit
zip -r "../${output_file}" .
mv "../${output_file}" .
popd || exit
