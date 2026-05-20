if ( -not ( Get-Command python -ErrorAction SilentlyContinue ) ) { 
    Write-Output "Python is not installed or not in the PATH. Please install Python and ensure it is in the PATH before running this script." 
    exit 1
}
if ( test-path "./venv/scripts/activate" ) {
   & "./venv/scripts/activate"
}
if ( -not ($env:virtual_env)) {
    python -m venv .\venv
    & "./venv/scripts/activate"
    pip install -r dev/requirements.txt
}
python src/gedcom_navigator_gui.py
