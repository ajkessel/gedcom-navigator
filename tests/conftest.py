"""pytest configuration and stable local temp paths for Windows."""
import re
import shutil
import sys
import uuid
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def tmp_path(request):
    """Return a per-test temp path without using pytest's Windows basetemp root.

    Pytest recreates its basetemp with restrictive ACLs in this sandboxed
    Windows environment, which can leave directories inaccessible after a run.
    Creating normal repo-local directories here preserves inherited ACLs.
    """
    root = _REPO_ROOT / ".pytest_test_tmp"
    root.mkdir(exist_ok=True)
    test_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.nodeid)
    path = root / f"{test_name[:80]}-{uuid.uuid4().hex[:8]}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
