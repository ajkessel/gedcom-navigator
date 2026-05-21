#!/usr/bin/env bash
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1
[ -e src/gedcom_navigator_gui.py ] || {
	echo 'Application file not found.'
	exit 1
}
[ -z "${VIRTUAL_ENV}" ] && {
	[ -f .venv/bin/activate ] && source .venv/bin/activate
	[ -f venv/bin/activate ] && source venv/bin/activate
	[ -f .venv/scripts/activate ] && source venv/scripts/activate
	[ -f venv/scripts/activate ] && source venv/scripts/activate
}
[ -z "${VIRTUAL_ENV}" ] && {
	python3 -m venv .venv || exit 1
	source .venv/bin/activate || exit 1
	pip install -r ./dev/requirements.txt || exit 1
}
python src/gedcom_navigator_gui.py
