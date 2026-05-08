#!/bin/bash
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
	echo 'This script is intended to be run on Linux.'
	exit 1
fi
output_file="gedcom-dna-finder-linux.zip"
while getopts "hnco:" opt; do
	case $opt in
	h)
		echo "Usage: $0 [-h] [-c] [-o]"
		exit 0
		;;
	c) CLEAN=true ;;
	o) output_file=$OPTARG ;;
	*)
		echo "Invalid option"
		exit 1
		;;
	esac
done
[[ "$CLEAN" ]] && [[ -e ".venv" ]] && rm -r ".venv"
[[ -e ".venv/bin/activate" ]] || {
	echo 'Creating virtual environment...'
	python3 -m venv .venv --prompt "gedcom-dna-finder" || {
		echo 'Failed to create virtual environment.'
		exit 1
	}
}
# shellcheck disable=SC1091
source .venv/bin/activate || {
	echo 'Failed to activate virtual environment.'
	exit 1
}
pip install -r ./dev/requirements.txt || {
	echo 'Failed to install dependencies.'
	exit 1
}
echo 'Running unit tests...'
pytest -v --tb=short --disable-warnings || {
	echo 'Unit tests failed. Exiting.'
	exit 1
}
python3 ./dev/generate_icon.py ./icons/family_tree.png || {
	echo 'Failed to generate ICO file.'
	exit 1
}
pyinstaller --noconfirm ./dev/gedcom_dna_finder_cli.spec || {
	echo 'pyinstaller failed to build CLI.'
	exit 1
}
pyinstaller --noconfirm ./dev/gedcom_dna_finder_gui.spec || {
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
