#!/usr/bin/env bash
[ -d .venv ] && source .venv/bin/activate
[ -d venv ] && source venv/bin/activate
python src/gedcom_dna_finder_gui.py
