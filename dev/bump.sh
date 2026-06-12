#!/usr/bin/env bash
[ -z "${1}" ] && echo "Usage: $0 <version>/bump/clobber" && exit 1
set -euo pipefail
current=$(git describe --tags --abbrev=0)
[ -z "$current" ] && echo "No tags found. Please create a tag first." && exit 1
[ "$1" = "bump" ] && {
	IFS=. read -r major minor patch <<<"${current#v}"
	patch=$((patch + 1))
	set -- "$major.$minor.$patch"
}
[ "$1" = "clobber" ] && {
	set -- "${current#v}"
}
tag="v${1}"
printf "Current version: %s\nNew version: %s\n" "${current}" "${tag}"
read -rp "Continue? [y/N] " answer
[ "$answer" != "y" ] && echo "Aborting." && exit 1
if git rev-parse "${tag}" &> /dev/null; then 
	printf "Removing existing tag %s\n" "${tag}"
	git tag -d "${1}"
	git push origin --delete "${1}"
fi
git tag "${tag}" -m "GEDCOM Navigator Release ${tag}"
git push origin "${tag}"
