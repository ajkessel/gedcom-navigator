#!/usr/bin/env bash
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1
[ -z "${WSL_DISTRO_NAME}" ] && {
	echo 'This script launches the application with Windows Python from WSL.'
	echo 'It is not intended for use outside of WSL.'
	exit 1
}
[ ! -e "/mnt/c/apps/src/gedcom-navigator/venv/Scripts/python.exe" ] && {
	echo '/mnt/c/apps/src/gedcom-navigator/venv/Scripts/python.exe not found.'
	echo 'Script needs to be modified to find the Windows venv python interpreter.'
	exit 1
}
/mnt/c/apps/src/gedcom-navigator/venv/Scripts/python.exe $(wslpath -w src/gedcom_navigator_gui.py)