#!/usr/bin/env bash
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1
[ -z "${WSL_DISTRO_NAME}" ] && {
	echo 'This script launches the application with Windows Python from WSL.'
	echo 'It is not intended for use outside of WSL.'
	exit 1
}
WIN_PY="/mnt/c/apps/src/gedcom-navigator/venv/Scripts/python.exe"
[ ! -e "${WIN_PY}" ] && {
	echo '/mnt/c/apps/src/gedcom-navigator/venv/Scripts/python.exe not found.'
	echo 'Script needs to be modified to find the Windows host venv python interpreter.'
	exit 1
}
args=()
for arg in "$@"; do
	if [[ "${arg}" != -* && -e "${arg}" ]]; then
		args+=("$(wslpath -w "${arg}")")
	else
		args+=("${arg}")
	fi
done
if [ -n "${gedcom_navigator_debug:-}" ] && [ -z "${GEDCOM_NAVIGATOR_DEBUG:-}" ]; then
	export GEDCOM_NAVIGATOR_DEBUG="${gedcom_navigator_debug}"
fi
if [ -n "${gedcom_navigator_debug_log:-}" ] && [ -z "${GEDCOM_NAVIGATOR_DEBUG_LOG:-}" ]; then
	export GEDCOM_NAVIGATOR_DEBUG_LOG="${gedcom_navigator_debug_log}"
fi
if [ -n "${GEDCOM_NAVIGATOR_DEBUG}" ] || [ -n "${GEDCOM_NAVIGATOR_DEBUG_LOG}" ]; then
	export GEDCOM_NAVIGATOR_DEBUG
	export GEDCOM_NAVIGATOR_DEBUG_LOG
	export WSLENV="${WSLENV:+$WSLENV:}GEDCOM_NAVIGATOR_DEBUG/w:GEDCOM_NAVIGATOR_DEBUG_LOG/wp"
fi
"${WIN_PY}" "$(wslpath -w src/gedcom_navigator_gui.py)" "${args[@]}"
