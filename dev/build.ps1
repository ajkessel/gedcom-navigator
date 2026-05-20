#Requires -version 5.1
param ( [Parameter(Mandatory = $false, HelpMessage = "clean build")][switch]$clean)
# optional configuration for signing executables
# create self-signed certificate with powershell script like the following:
# New-SelfSignedCertificate -Type CodeSigningCert -Subject "gedcom-navigator" -CertStoreLocation Cert:\CurrentUser\My
Set-Location -Path $PSScriptRoot/..
Start-Transcript -Path "build-windows.log" -Append
try {
    Write-Output("Starting build process for Windows...")
    Get-Date
    $searchPaths = ($env:ProgramData + "\miniforge3\scripts\"), ($env:localappdata + "\miniconda3\scripts\"), ($env:appdata + "\miniconda3\scripts\")
    $fileName = "conda.exe"
    $found_file = Get-ChildItem -Path $searchPaths -Filter $fileName -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found_file) {
        Write-Output("Found conda at " + $found_file)
        Write-Output("Activating base environment.")
        (& $found_file "shell.powershell" "hook") | Out-String | Where-Object { $_ } | Invoke-Expression
    }
    else {
        Write-Output("Conda not found. Will attempt to use locally installed Python.")
    }
    $signTool = 'C:\Program Files (x86)\Windows Kits\10\App Certification Kit\SignTool.exe'
    $certName = 'gedcom-navigator'
    if ( -not ( Get-Command python -ErrorAction SilentlyContinue ) ) { 
        Write-Output "Python is not installed or not in the PATH. Please install Python and ensure it is in the PATH before running this script." 
        exit 1
    }
    if ( $clean -and ( Test-Path .\venv ) ) {
        Write-Output "Clean build selected, re-creating venv from scratch."
        Remove-Item -Force -Recurse .\venv
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
    Write-Output "Applying ctktooltip patch... (see https://github.com/Akascape/CTkToolTip/issues/20 for details)"
    git apply --unsafe-paths -p1 --directory=$ENV:VIRTUAL_ENV/lib/site-packages ./dev/ctk_tooltip.patch || {
        Write-Output "Failed to apply ctktooltip patch, may have been applied already. Proceeding anyway..."
    }
    git pull
    & ".\venv\Scripts\activate.ps1"
    Remove-Item -Recurse -Force -Path dist\
    New-Item -ItemType Directory -Path dist -Force | Out-Null

    # Generate plain-text LICENSE.txt for Inno Setup (stripping markdown)
    $licenseMd = Get-Content ".\docs\LICENSE.md" -Raw
    $licenseTxt = $licenseMd -replace '^##+\s+', '' -replace '\[([^\]]+)\]\(([^\)]+)\)', '$1 ($2)'
    $licenseTxt | Out-File -FilePath ".\dist\LICENSE.txt" -Encoding utf8

    python .\dev\generate_icon.py .\icons\family_tree.png
    pyinstaller --noconfirm .\dev\gedcom_navigator_gui.spec
    pyinstaller --noconfirm .\dev\gedcom_navigator_cli.spec

    # Build Inno Setup installer if iscc.exe is available
    $iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    if (-not $iscc) {
        $isccPaths = "C:\Program Files (x86)\Inno Setup 6\iscc.exe", 
        "C:\Program Files\Inno Setup 6\iscc.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\iscc.exe"
        foreach ($p in $isccPaths) {
            if (Test-Path $p) {
                $iscc = $p
                break
            }
        }
    }

    if ($iscc) {
        Write-Output "Inno Setup found at $iscc. Building installer..."
        $initFile = Get-Content ".\gedcom_navigator\__init__.py" -Raw
        if ($initFile -match '__version__\s*=\s*["'']([^"'']+)["'']') {
            $version = $Matches[1]
            Write-Output "Building installer for version $version"
            & $iscc /dMyAppVersion=$version ".\dev\gedcom-navigator.iss"
        }
    }

    # Build MSIX package if makeappx.exe is available
    $makeappx = Get-Command makeappx.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    if (-not $makeappx) {
        $sdkPaths = Get-ChildItem -Path "C:\Program Files (x86)\Windows Kits\10\bin" -Filter "makeappx.exe" -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.FullName -like "*x64*" }
        if ($sdkPaths) {
            $makeappx = $sdkPaths[0].FullName
        }
    }

    if ($makeappx) {
        Write-Output "MakeAppx found at $makeappx. Building MSIX package..."
        $initFile = Get-Content ".\gedcom_navigator\__init__.py" -Raw
        if ($initFile -match '__version__\s*=\s*["'']([^"'']+)["'']') {
            $version = $Matches[1]
            $fourDigitVersion = "$version.0"
            Write-Output "Building MSIX for version $fourDigitVersion"
            
            # Prepare staging directory
            $stagingDir = ".\dist\msix_staging"
            if (Test-Path $stagingDir) { Remove-Item -Recurse -Force $stagingDir }
            New-Item -ItemType Directory -Path $stagingDir | Out-Null
            New-Item -ItemType Directory -Path "$stagingDir\Assets" | Out-Null

            # Generate Assets
            python .\dev\generate_msix_assets.py .\icons\family_tree.png "$stagingDir\Assets"

            # Copy Executable (using the one-file EXE for simplicity)
            Copy-Item ".\dist\gedcom-navigator.exe" "$stagingDir\gedcom-navigator.exe"

            # Fill Manifest
            $manifestTemplate = Get-Content ".\dev\AppxManifest.xml.template" -Raw
            $manifest = $manifestTemplate.Replace("{VERSION}", $fourDigitVersion)
            $manifest | Out-File -FilePath "$stagingDir\AppxManifest.xml" -Encoding utf8

            # Pack
            & $makeappx pack /d "$stagingDir" /p ".\dist\gedcom-navigator.msix" /o
            Write-Output "MSIX package created: .\dist\gedcom-navigator.msix"
            
            if (Test-Path $stagingDir) { Remove-Item -Recurse -Force $stagingDir }
        }
    }

    if ( ( Get-ChildItem -Path Cert:\CurrentUser\My | Where-Object { $_.Subject -like ("CN=" + $certName) } ) -and ( Test-Path $SignTool ) ) {
        & $SignTool sign /n $certName /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ".\dist\gedcom_navigator_cli.exe" 
        & $SignTool sign /n $certName /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ".\dist\gedcom-navigator.exe" 
        if (Test-Path ".\dist\gedcom-navigator-setup.exe") {
            & $SignTool sign /n $certName /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ".\dist\gedcom-navigator-setup.exe" 
        }
    }
    Compress-Archive -Path dist\* -DestinationPath .\dist\gedcom-navigator-windows-portable.zip -Force
    if (Test-Path ".\dev\Output\gedcom-navigator-setup.exe") {
        Move-Item -Force ".\dev\Output\gedcom-navigator-setup.exe" ".\dist\gedcom-navigator-windows-installer.exe"
        Remove-Item -Recurse -Force ".\dev\Output"
    }
}
finally {
    Stop-Transcript
}