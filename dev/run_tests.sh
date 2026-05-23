#!/usr/bin/env bash
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1
[ -d ./tests/ ] || {
	echo 'Tests folder not found.'
	exit 1
}
python -m pytest tests/ -v