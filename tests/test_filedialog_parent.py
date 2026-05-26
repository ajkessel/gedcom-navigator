"""Static check: all filedialog calls with parent= must use filedialog_parent().

On macOS, passing a raw window as parent= to tkinter filedialog functions causes
the dialog to be shown as a sheet via NSWindow _beginSheet.  In compiled
(PyInstaller) apps this triggers an AppKit assertion and aborts.  The helper
filedialog_parent() returns None on macOS, making the dialog appear as a
standalone window instead.
"""

import ast
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src"


def _bare_parent_violations(path):
    """Return (lineno, func_name) pairs for filedialog calls with a raw parent=."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "filedialog"
        ):
            continue
        for kw in node.keywords:
            if kw.arg != "parent":
                continue
            val = kw.value
            if not (
                isinstance(val, ast.Call)
                and isinstance(val.func, ast.Name)
                and val.func.id == "filedialog_parent"
            ):
                violations.append((node.lineno, func.attr))
    return violations


def test_filedialog_uses_filedialog_parent_helper():
    """Every filedialog call that passes parent= must wrap it in filedialog_parent()."""
    failures = {}
    for py_file in sorted(SRC_DIR.glob("*.py")):
        violations = _bare_parent_violations(py_file)
        if violations:
            failures[py_file.name] = violations

    assert failures == {}, (
        "filedialog calls with bare parent= kwarg (wrap with filedialog_parent()):\n"
        + "\n".join(
            f"  {fname}: line {ln} in {fn}()"
            for fname, locs in failures.items()
            for ln, fn in locs
        )
    )
