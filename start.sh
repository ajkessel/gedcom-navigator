#!/usr/bin/env bash
[ -e src/gedcom_dna_finder_gui.py ] || {
	echo 'Application file not found.'
	exit 1
}
[ -f .venv/bin/activate ] && source .venv/bin/activate
[ -f venv/bin/activate ] && source venv/bin/activate
[ -f .venv/scripts/activate ] && source venv/scripts/activate
[ -f venv/scripts/activate ] && source venv/scripts/activate
[ -z "${VIRTUAL_ENV}" ] && {
  python3 -m venv .venv || exit 1
  source .venv/bin/activate || exit 1
  pip install -r ./dev/requirements.txt || exit 1
}
python src/gedcom_dna_finder_gui.py
