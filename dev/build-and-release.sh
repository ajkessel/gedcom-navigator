#!/bin/bash
# script for building and uploading executables to Github
# intended to run from WSL instance with access to local powershell and mac accessible via ssh with source code installed at hostname 'mac'
# include -c as command line switch to create new release, otherwise latest release will be used
if [[ "$STDBUF_ACTIVE" != "1" ]]; then
	export STDBUF_ACTIVE=1
	exec stdbuf -oL "$0" "$@"
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.."
exec > >(sed 's/\x1b\[[0-9;]*m//g' | tee -a build-and-release.log) 2>&1
printf -- "---------------------------------\ngedcom-dna-finder build log\n$(date)\n---------------------------------\n"
if [ "$1" == "-c" ]; then
	gh release create
fi
current=$(gh release list --json tagName,isLatest --jq '.[] | select(.isLatest) | .tagName')
[ "$current" ] || {
	echo 'Error finding current release number.'
	exit 1
}
git pull || {
	echo 'Error updating from git.'
	exit 1
}
source .venv/bin/activate
echo 'Building for Linux platform...'
./dev/build.sh
echo 'Building for Windows platform...'
pwsh -command 'c:/apps/src/gedcom-dna-finder/dev/build.ps1'
echo 'Building for Mac platform...'
ssh mac 'src/gedcom-dna-finder/dev/build.sh'
echo 'Copying built ZIP files locally...'
scp mac:src/gedcom-dna-finder/dist/*zip ./dist
cp /mnt/c/apps/src/gedcom-dna-finder/dist/*zip ./dist
echo 'Uploading new release to GitHub...'
gh release upload "${current}" ./dist/*zip --clobber
