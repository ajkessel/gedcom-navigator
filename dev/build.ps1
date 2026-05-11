# optional configuration for signing executables
# create self-signed certificate with powershell script like the following:
# New-SelfSignedCertificate -Type CodeSigningCert -Subject "gedcom-dna-finder" -CertStoreLocation Cert:\CurrentUser\My
# TODO - add argument for clean build
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
$signTool = 'C:\Program Files (x86)\Windows Kits\10\App Certification Kit\SignTool.exe'
$certName = 'gedcom-dna-finder'
Set-Location -Path $PSScriptRoot/..
if ( -not ( Get-Command python -ErrorAction SilentlyContinue ) ) { 
    Write-Output "Python is not installed or not in the PATH. Please install Python and ensure it is in the PATH before running this script." 
    exit 1
}
if ( -not ( Test-Path .\venv\scripts\activate.ps1)) {
    Write-Output "Creating and activating virtual environment, and installing dependencies..."
    python -m venv .\venv --prompt "gedcom-dna-finder" 
    python .\dev\find_ffi_dll.py
    .\venv\Scripts\activate.ps1
    pip install -r .\dev\requirements-dev.txt
}
if ( -not ( Test-Path .\venv\scripts\activate.ps1)) {
    Write-Output "Virtual environment activation script not found. Please ensure the virtual environment is set up correctly." 
    exit 1
}
git pull
& ".\venv\Scripts\activate.ps1"
Remove-Item -Recurse -Force -Path dist\
python .\dev\generate_icon.py .\icons\family_tree.png
pyinstaller --noconfirm .\dev\gedcom_dna_finder_gui.spec
pyinstaller --noconfirm .\dev\gedcom_dna_finder_cli.spec
if ( ( Get-ChildItem -Path Cert:\CurrentUser\My | Where-Object { $_.Subject -like ("CN=" + $certName) } ) -and ( Test-Path $SignTool ) ) {
    & $SignTool sign /n $certName /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ".\dist\gedcom_dna_finder_cli.exe" 
    & $SignTool sign /n $certName /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ".\dist\gedcom-dna-finder.exe" 
}
Compress-Archive -Path dist\* -DestinationPath .\dist\gedcom-dna-finder-windows.zip -Force
