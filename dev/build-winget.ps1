#Requires -version 5.1
Set-Location -Path $PSScriptRoot/..
Start-Transcript -Path "build-winget.log" -Append
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
   Remove-Item -Path "..\winget-pkgs\manifests\a\AdamKessel\GEDCOMNavigator" -Recurse -Force -ErrorAction SilentlyContinue
   New-Item -ItemType Directory -Path "..\winget-pkgs\manifests\a\AdamKessel\GEDCOMNavigator" -Force
   if ( Test-Path -Path "..\winget-pkgs\manifests\a\AdamKessel\GEDCOMNavigator" ) {
      Write-Output "Found local Winget Github manifests directory, copying new manifests... (remember to create pull request for version $fourDigitVersion)"
      New-Item -ItemType Directory -Path "..\winget-pkgs\manifests\a\AdamKessel\GEDCOMNavigator\$fourDigitVersion" -Force
      Copy-Item -Path ".\dist\*.yaml" -Destination "..\winget-pkgs\manifests\a\AdamKessel\GEDCOMNavigator\$fourDigitVersion" -Force
      Set-Location -Path "..\winget-pkgs\manifests\a\AdamKessel\GEDCOMNavigator\$fourDigitVersion"
      git switch master
      git pull
      git branch $fourDigitVersion
      git switch $fourDigitVersion 
      git add *.yaml
      git commit -m "Update Winget manifests for version $fourDigitVersion"
      git push --set-upstream origin $fourDigitVersion
      git switch master
      Set-Location -Path $PSScriptRoot/..
   }
}