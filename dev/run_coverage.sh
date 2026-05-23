#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1

python -m pytest \
	--cov=src \
	--cov-report=term-missing \
	--cov-report=html:test-artifacts/coverage-html \
	tests/
