#!/bin/bash
# script for building and uploading executables to Github
# intended to run from WSL instance with access to local powershell and mac accessible via ssh with source code installed at hostname 'mac'
# include -c as command line switch to create new release, otherwise latest release will be used
die() {
    printf "Error: %s\n" "$1" >&2
    exit "${2:-1}"
}
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
		die "Invalid option specified" 
		;;
	esac
done
printf -- "---------------------------------\ngedcom-dna-finder build\n%s\n---------------------------------\n" "$(date)"
[ -n "$CLEAN" ] && echo 'Running clean builds.' && OPTIONS="-c"
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || die "Could not change to ${SCRIPT_DIR} parent directory."
[ -n "$UPDATE_GH" ] && {
  GH_FORCE_TTY=true gh release create || die "gh release create failed"
}
exec > >(sed 's/\x1b\[[0-9;]*m//g' | tee -a build-and-release.log) 2>&1
printf -- "---------------------------------\ngedcom-dna-finder build log\n%s\n---------------------------------\n" "$(date)"
current=$(gh release list --json tagName,isLatest --jq '.[] | select(.isLatest) | .tagName')
[ -n "${current}" ] || die 'Error finding current release number.'
echo "Building for release target ${current}."
branch=$(git branch --show-current)
echo "current git branch: ${branch}"
if [ "${branch}" != "main" ]; then
  echo "Warning: not on main branch."
  read -t 5 -n 1 -s -r -p "Press any key to continue or q to exit (waiting 5s)..." x
  [ "${x}" == "q" ] && exit 1
fi
git pull || die 'Error updating from git.'
# shellcheck source=/dev/null
source .venv/bin/activate || die 'Error activating venv.'
echo 'Building for Linux platform...'
./dev/build.sh "${OPTIONS}" || die 'Error building for Linux.'
echo 'Building for Windows platform...'
pwsh -command 'c:/apps/src/gedcom-dna-finder/dev/build.ps1' || die 'Error building for Windows.'
echo 'Building for Mac platform...'
# ${OPTIONS} should be expanded locally, not remotely
# shellcheck disable=SC2029
ssh mac "src/gedcom-dna-finder/dev/build.sh ${OPTIONS}" || die 'Error building for Mac.'
echo 'Copying built ZIP files locally...'
scp mac:src/gedcom-dna-finder/dist/*zip ./dist || die 'Error copying ZIP files.'
cp /mnt/c/apps/src/gedcom-dna-finder/dist/*zip ./dist || die 'Error copying ZIP files.'
[ -z "${DRY}" ] && echo 'Uploading to GitHub...' && gh release upload "${current}" ./dist/*zip --clobber
