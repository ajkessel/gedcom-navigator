Set-Location -Path $PSScriptRoot/..
if ( Test-Path "./venv/Scripts/Activate.ps1" ) {
    & "./venv/Scripts/Activate.ps1"
}
if ( -not ( Get-Command python -ErrorAction SilentlyContinue ) ) {
    Write-Output "Python is not installed or not in the PATH or venv. Please install Python and ensure it is in the PATH before running this script."
    exit 1
}
if ( -not ($env:virtual_env)) {
    python -m venv .\venv
    & "./venv/Scripts/Activate.ps1"
    pip install -r dev/requirements-dev.txt
}
& "./venv/Scripts/python.exe" -m pytest -m gui tests/test_gui_smoke.py @args
