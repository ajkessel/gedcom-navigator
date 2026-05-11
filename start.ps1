& "venv/scripts/activate"
if ( -not ($env:virtual_env)) {
    python3 -m venv .\venv
    & "venv/scripts/activate"
    pip install -r dev/requirements.txt
}
python src/gedcom_dna_finder_gui.py
