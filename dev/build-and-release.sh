#!/bin/bash
# script for building and uploading executables to Github
# intended to run from WSL instance with access to local powershell and mac accessible via ssh with source code installed at hostname 'mac'
# include -c as command line switch to create new release, otherwise latest release will be used
die() {
	printf "Error: %s\n" "$1" >&2
	exit "${2:-1}"
}
# this is necessary to keep screen buffer up to date
# while logging to file
if [[ "$STDBUF_ACTIVE" != "1" ]]; then
	export STDBUF_ACTIVE=1
	exec stdbuf -oL "$0" "$@"
fi
git_branch="main"
while getopts "hncib:" opt; do # spell:disable-line
	case $opt in
	h)
		echo "Usage: $0 [-h] [-n] [-c] [-i] [-b]"
		echo "  -h  Show this help message and exit"
		echo "  -n  Dry run: build the app but skip signing and uploading to GitHub"
		echo "  -c  Clean build: remove virtual environment and pyenv versions before building"
		echo "  -b  Branch: specify git branch to build/release (default main)"
    echo "  -i  Update gh to new release number (add tag)"
		exit 0
		;;
	n) DRY=true ;;
	c) CLEAN=true ;;
	i) UPDATE_GH=true ;;
	b) git_branch=$OPTARG ;;
	*)
		die "Invalid option specified"
		;;
	esac
done
printf -- "---------------------------------\ngedcom-navigator build\n%s\n---------------------------------\n" "$(date)"
[ -n "${DRY}" ] && OPTIONS+=" -n"
[ -n "${CLEAN}" ] && echo 'Running clean builds.' && OPTIONS+=" -c"
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || die "Could not change to ${SCRIPT_DIR} parent directory."
[ -n "$UPDATE_GH" ] && {
	GH_FORCE_TTY=true gh release create || die "gh release create failed"
}
exec > >(sed 's/\x1b\[[0-9;]*m//g' | tee -a build-and-release.log) 2>&1
printf -- "---------------------------------\ngedcom-navigator build log\n%s\n---------------------------------\n" "$(date)"
git switch "${git_branch}" || {
	echo "Error: could not switch to ${git_branch}. Aborting."
	exit 1
}
if [ "${git_branch}" != "main" ]; then
	echo "Warning: not on main branch."
	read -t 5 -n 1 -s -r -p "Press any key to continue or q to exit (waiting 5s)..." x
	[ "${x}" == "q" ] && exit 1
fi
git pull || die 'Error updating from git.'
# shellcheck source=/dev/null
source .venv/bin/activate || die 'Error activating venv.'
echo 'Building for Linux platform...'
./dev/build.sh -b "${git_branch}" ${OPTIONS} || die 'Error building for Linux.'
echo 'Building for Windows platform...'
pwsh=$(command -v pwsh.exe)
[ -z "$pwsh" ] && pwsh=$(command -v /mnt/c/Program\ Files/PowerShell/7/pwsh.exe)
[ -z "$pwsh" ] && die 'PowerShell executable not found, cannot continue.'
"${pwsh}" -command 'c:/apps/src/gedcom-navigator/dev/build.ps1' || die 'Error building for Windows.'
echo 'Building for Mac platform...'
# ${OPTIONS} should be expanded locally, not remotely
# shellcheck disable=SC2029
ssh mac '${HOME}/src/gedcom-navigator/dev/build.sh '"${OPTIONS}" || die 'Error building for Mac.'
echo 'Copying built ZIP files locally...'
scp mac:src/gedcom-navigator/dist/*zip ./dist || die 'Error copying ZIP files.'
cp /mnt/c/apps/src/gedcom-navigator/dist/*zip /mnt/c/apps/src/gedcom-navigator/dist/*exe ./dist || die 'Error copying ZIP files.'
current=$(gh release list --json tagName,isLatest --jq '.[] | select(.isLatest) | .tagName')
[ -n "${current}" ] || die 'Error finding current branch.'
[ -z "${DRY}" ] && echo 'Uploading to GitHub...' && gh release upload "${current}" ./dist/*zip ./dist/*installer.exe --clobber
