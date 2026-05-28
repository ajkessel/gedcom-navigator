#Requires -version 5.1
Set-Location -Path $PSScriptRoot/..
Start-Transcript -Path "build-winget.log" -Append
$ErrorActionPreference = 'Stop'
$initFile = Get-Content ".\gedcom_navigator\__init__.py" -Raw
if ($initFile -match '__version__\s*=\s*["'']([^"'']+)["'']') {
   $version = $Matches[1]
   $fourDigitVersion = "$version.0"
}
if ( -not ( $version -and $fourDigitVersion ) ) {
   Write-Output "Version not found, exiting."
   exit 1
}
# Fill and commit Winget Manifest
$installersha256 = Get-FileHash ".\dist\gedcom-navigator-windows-installer.exe" -Algorithm SHA256 | Select-Object -ExpandProperty Hash
if ( -not ( $installersha256 ) ) {
   Write-Output "Installer SHA256 not found; skipping Winget manifest generation."
   exit 1
}
Write-Output "Generating Winget manifests..."
Get-ChildItem -Path .\dev\winget\*.template | ForEach-Object {
   $manifestTemplate = Get-Content $_.FullName -Raw        
   $manifest = $manifestTemplate.Replace("{VERSION}", $fourDigitVersion)
   $manifest = $manifest.Replace("{VERSIONX}", $version)
   $manifest = $manifest.Replace("{INSTALLERSHA256}", $installersha256)
   $manifest | Out-File -FilePath ".\dist\$($_.BaseName).yaml" -Encoding utf8
   Write-Output ("Generated .\dist\$($_.BaseName).yaml")
}
if ( Test-Path -Path "..\winget-pkgs" ) {
   Write-Output "Found local Winget Github manifests directory, copying new manifests... (remember to create pull request for branch $fourDigitVersion)"
   Set-Location -Path "..\winget-pkgs\manifests\a\AdamKessel\GEDCOMNavigator"
   git switch master
   gh repo sync --force
   git pull
   git branch $fourDigitVersion
   git switch $fourDigitVersion 
   New-Item -ItemType Directory -Path "$fourDigitVersion" -Force
   Copy-Item -Path "$PSScriptRoot/../dist/*.yaml" -Destination "$fourDigitVersion" -Force
   git add "$fourDigitVersion"/*.yaml
   git commit -m "Update Winget manifests for version $fourDigitVersion"
   git push --set-upstream origin $fourDigitVersion
   git switch master
   Set-Location -Path $PSScriptRoot/..
}