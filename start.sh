#!/usr/bin/env bash
[ -e src/gedcom_dna_finder_gui.py ] || {
	echo 'Application file not found.'
	exit 1
}
[ -f .venv/bin/activate ] && source .venv/bin/activate
[ -f venv/bin/activate ] && source venv/bin/activate
[ -f .venv/scripts/activate ] && source venv/scripts/activate
[ -f venv/scripts/activate ] && source venv/scripts/activate
python src/gedcom_dna_finder_gui.py
