#!/usr/bin/env bash
[ -f .venv/bin/activate ] && source .venv/bin/activate
[ -f venv/bin/activate ] && source venv/bin/activate
[ -f .venv/scripts/activate ] && source venv/scripts/activate
[ -f venv/scripts/activate ] && source venv/scripts/activate
python src/gedcom_dna_finder_gui.py
