Set-Location -Path $PSScriptRoot/..
if ( test-path "./venv/scripts/activate" ) {
   Write-Output "venv found, activating"
   & "./venv/scripts/activate"
}
if ( -not ( Get-Command python -ErrorAction SilentlyContinue ) ) { 
    Write-Output "Python is not installed or not in the PATH or venv. Please install Python and ensure it is in the PATH before running this script." 
    exit 1
}
if ( -not ($env:virtual_env)) {
    python -m venv .\venv
    & "./venv/scripts/activate"
    pip install -r dev/requirements.txt
}
$env:GEDCOM_NAVIGATOR_GRAPH_DEBUG=1
python src/gedcom_navigator_gui.py
