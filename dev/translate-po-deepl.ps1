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
$exitCode = $LASTEXITCODE
if ($exitCode -eq 3) {
    Write-Error 'ERROR: Translation completed but placeholder tokens were not properly restored.'
    Write-Error 'Check the WARNING lines above. The .po files may contain corrupt entries.'
    exit 1
} elseif ($exitCode -ne 0) {
    Write-Error 'Translation failed. Is API key set in .env?'
    exit 1
}

# Secondary check: scan output files for any remaining unrestored tokens (⟦NNNN⟧)
$tokenErrors = 0
Get-Item locales/*.po -ErrorAction SilentlyContinue | ForEach-Object {
    $content = Get-Content $_.FullName -Raw -Encoding UTF8
    if ($content -match '⟦') {
        Write-Error "ERROR: $($_.FullName) contains unrestored placeholder tokens — translation is corrupt."
        $tokenErrors++
    }
}
if ($tokenErrors -gt 0) {
    Write-Error "ERROR: $tokenErrors file(s) have corrupt translations. Aborting."
    exit 1
}

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
