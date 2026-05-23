#!/usr/bin/env bash
Set-Location -Path $PSScriptRoot/..
Get-Content .env | Foreach-Object {
    $name, $value = $_.split('=', 2)
    if ($name -and $value) {
        Set-Item "env:$($name.Trim())" $value.Trim()
    }
}
if ( -not ( get-path './dev/translate-po-deepl.py' -ErrorAction SilentlyContinue ) ) {
    Write-Output 'dev/translate-po-deepl.py not found. Exiting.'
    exit 1
}
if ( -not ( get-path 'venv/scripts/activate' -ErrorAction SilentlyContinue ) ) {
    Write-Output 'Creating virtual environment...'
    python3 -m venv venv --prompt "gedcom-navigator" || {
        Write-Output 'Failed to create virtual environment.'
        exit 1
    }
}
& venv/scripts/activate || {
    Write-Output 'Failed to activate virtual environment.'
    exit 1
}
try {
    pybabel extract -o locales/gedcom_navigator.pot src/
} catch {
    Write-Output "Failed to extract strings with pybabel."
    exit 1
}
python ./dev/translate-po-deepl.py --input ./locales/gedcom_navigator.pot --outdir locales --langs de es fr he --prefer-official
get-item locales/*.po | ForEach-Object {
  if ( -not ($_.BaseName -like "*_*") ) {
    Write-Output "Skipping non-language PO file: $($_.FullName)"
  } else {
  Write-Output "Moving translation: $($_.FullName)"
    $lang = $_.BaseName -replace '.*_', ''
    $destDir = "locales/$lang/LC_MESSAGES"
    if ( -not ( Test-Path $destDir ) ) {
        New-Item -ItemType Directory -Path $destDir | Out-Null
    }
    Move-Item -Force -Path $_.FullName -Destination "$DestDir/gedcom_navigator.po"
  }
}
