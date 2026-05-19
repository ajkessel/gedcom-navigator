
Set-Location -Path $PSScriptRoot/..
$searchPaths = ($env:ProgramData+"\miniforge3\scripts\"),($env:localappdata+"\miniconda3\scripts\"),($env:appdata+"\miniconda3\scripts\")
$fileName = "conda.exe"
$found_file = Get-ChildItem -Path $searchPaths -Filter $fileName -ErrorAction SilentlyContinue | Select-Object -First 1
If ($found_file) {
  write-output("Found conda at "+$found_file)
  write-output("Activating base environment.")
  (& $found_file "shell.powershell" "hook") | Out-String | Where-Object{$_} | Invoke-Expression
} else {
  write-output("Conda not found. Will attempt to use locally installed Python.")
}
if ( -not ( Get-Command python -ErrorAction SilentlyContinue ) ) { 
    Write-Output "Python is not installed or not in the PATH. Please install Python and ensure it is in the PATH before running this script." 
    exit 1
}
if ( -not ( Test-Path .\venv\scripts\activate.ps1)) {
    Write-Output "Creating and activating virtual environment, and installing dependencies..."
    python -m venv .\venv --prompt "gedcom-navigator" 
    python .\dev\find_ffi_dll.py
    .\venv\Scripts\activate.ps1
    pip install -r .\dev\requirements-dev.txt
}
if ( -not ( Test-Path .\venv\scripts\activate.ps1)) {
    Write-Output "Virtual environment activation script not found. Please ensure the virtual environment is set up correctly." 
    exit 1
}
if ( -not ( Test-Path .\tests\ ) ) {
    Write-Output "Tests folder not found. Please ensure the tests are set up correctly." 
    exit 1
}
python -m pytest tests/ -v
