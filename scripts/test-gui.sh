#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1

[ -z "${VIRTUAL_ENV:-}" ] && {
	[ -f .venv/bin/activate ] && source .venv/bin/activate
	[ -f venv/bin/activate ] && source venv/bin/activate
	[ -f .venv/scripts/activate ] && source .venv/scripts/activate
	[ -f venv/scripts/activate ] && source venv/scripts/activate
}

[ -z "${VIRTUAL_ENV:-}" ] && {
	python3 -m venv .venv
	source .venv/bin/activate
	pip install -r ./dev/requirements-dev.txt
}

python -m pytest -m gui tests/test_gui_smoke.py "$@"
