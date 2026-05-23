#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1

[ -z "${WSL_DISTRO_NAME:-}" ] && {
	echo 'This script runs GUI tests with Windows Python from WSL.'
	echo 'It is not intended for use outside of WSL.'
	exit 1
}

WIN_PY="/mnt/c/apps/src/gedcom-navigator/venv/Scripts/python.exe"
[ ! -e "${WIN_PY}" ] && {
	echo '/mnt/c/apps/src/gedcom-navigator/venv/Scripts/python.exe not found.'
	echo 'Script needs to be modified to find the Windows host venv python interpreter.'
	exit 1
}

"${WIN_PY}" -m pytest -m gui "$(wslpath -w tests/test_gui_smoke.py)" "$@"
