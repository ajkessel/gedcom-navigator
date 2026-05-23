"""pytest configuration for local test imports."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def pytest_collection_modifyitems(config, items):
    """Keep real GUI tests out of the default unit-test run."""
    markexpr = config.option.markexpr or ""
    run_gui = "gui" in markexpr or os.environ.get(
        "GEDCOM_NAVIGATOR_RUN_GUI_TESTS") == "1"
    if run_gui:
        return
    skip_gui = pytest.mark.skip(
        reason="GUI smoke tests are opt-in; run with -m gui")
    for item in items:
        if "gui" in item.keywords:
            item.add_marker(skip_gui)
