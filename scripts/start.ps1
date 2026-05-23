Set-Location -Path $PSScriptRoot/..
if ( test-path "./venv/Scripts/Activate.ps1" ) {
   Write-Output "venv found, activating"
   & "./venv/Scripts/Activate.ps1"
}
if ( -not ( Get-Command python -ErrorAction SilentlyContinue ) ) { 
    Write-Output "Python is not installed or not in the PATH or venv. Please install Python and ensure it is in the PATH before running this script." 
    exit 1
}
if ( -not ($env:virtual_env)) {
    python -m venv .\venv
    & "./venv/Scripts/Activate.ps1"
    pip install -r dev/requirements.txt
}
$env:GEDCOM_NAVIGATOR_DEBUG=1
& "./venv/Scripts/python.exe" src/gedcom_navigator_gui.py
