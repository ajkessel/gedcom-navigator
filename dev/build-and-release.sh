#!/bin/bash
# script for building and uploading executables to Github
# intended to run from WSL instance with access to local powershell and mac accessible via ssh with source code installed at hostname 'mac'
# include -c as command line switch to create new release, otherwise latest release will be used
if [[ "$STDBUF_ACTIVE" != "1" ]]; then
	export STDBUF_ACTIVE=1
	exec stdbuf -oL "$0" "$@"
fi
while getopts "hnci" opt; do # spell:disable-line
	case $opt in
	h)
		echo "Usage: $0 [-h] [-n] [-c] [-i]"
		echo "  -h  Show this help message and exit"
		echo "  -n  Dry run: build the app but skip uploading to GitHub"
		echo "  -c  Clean build: remove virtual environment and pyenv versions before building"
		echo "  -i  Update gh to new release number"
		exit 0
		;;
	n) DRY=true ;;
	c) CLEAN=true ;;
	i) UPDATE_GH=true ;;
	*)
		echo "Invalid option"
		exit 1
		;;
	esac
done
[ -n "$CLEAN" ] && OPTIONS="-c"
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1
exec > >(sed 's/\x1b\[[0-9;]*m//g' | tee -a build-and-release.log) 2>&1
printf -- "---------------------------------\ngedcom-dna-finder build log\n%s\n---------------------------------\n" "$(date)"
[ -n "$UPDATE_GH" ] && {
  GH_FORCE_TTY=true gh release create || exit 1
}
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
./dev/build.sh "${OPTIONS}"
echo 'Building for Windows platform...'
pwsh -command 'c:/apps/src/gedcom-dna-finder/dev/build.ps1'
echo 'Building for Mac platform...'
ssh mac "src/gedcom-dna-finder/dev/build.sh ${OPTIONS}"
echo 'Copying built ZIP files locally...'
scp mac:src/gedcom-dna-finder/dist/*zip ./dist
cp /mnt/c/apps/src/gedcom-dna-finder/dist/*zip ./dist
[ -z "${DRY}" ] && echo 'Creating new release on GitHub...' && gh release create "${current}" ./dist/*zip --clobber
