#!/usr/bin/env bash
set -euo pipefail
[ -z "$1" ] && echo "Usage: $0 <version>/bump/clobber" && exit 1
current=$(git describe --tags --abbrev=0)
[ -z "$current" ] && echo "No tags found. Please create a tag first." && exit 1
[ "$1" = "bump" ] && {
	IFS=. read -r major minor patch <<<"${current#v}"
	patch=$((patch + 1))
	set -- "$major.$minor.$patch"
}
[ "$1" = "clobber" ] && {
	set -- "${current}"
	git tag -d "${1}"
	git push origin --delete "${1}"
	set -- "${current#v}"
}
tag="v${1}"
printf "Current version: %s\nNew version: %s\n" "${current}" "${tag}"
git tag "${tag}"
git push origin "${tag}"
