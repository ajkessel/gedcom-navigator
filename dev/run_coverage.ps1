Set-Location -Path $PSScriptRoot/..
python -m pytest `
    --cov=src `
    --cov-report=term-missing `
    --cov-report=html:test-artifacts/coverage-html `
    tests/
