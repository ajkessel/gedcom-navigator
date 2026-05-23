"""
Static check: no source file should assign _ as a local variable in a function
that also defines closures capturing _ as a free variable.

Python closures capture by reference from the enclosing scope's cell. If an
outer function writes `for _ in range(n)` and an inner function references _
(e.g. to call the gettext translation), the inner function will see the
integer loop variable, not the translation function, when it is eventually
called.
"""

import importlib
import sys
import symtable
from pathlib import Path

# All source modules that could plausibly use _() for translation in closures.
# Excludes gedcom_strings (only module-level _ calls, no closures) and
# non-GUI pure-logic modules that never use _() at all.
_SOURCE_MODULES = [
    'gedcom_gui_appearance',
    'gedcom_gui_background',
    'gedcom_gui_dialogs',
    'gedcom_gui_graph_common',
    'gedcom_gui_help_dialogs',
    'gedcom_gui_person_dialog',
    'gedcom_gui_results',
    'gedcom_gui_search',
    'gedcom_navigator_gui',
]


def _closure_clobbers(module_name):
    """
    Return (outer_scope_name, inner_scope_name) pairs where the outer scope
    assigns to _ (making it a local cell variable) and the inner scope
    captures _ as a free variable. This is the condition that causes a closure
    to see an integer instead of the translation function.
    """
    module = importlib.import_module(module_name)
    source_path = Path(module.__file__)
    top = symtable.symtable(
        source_path.read_text(encoding='utf-8'),
        str(source_path),
        'exec',
    )
    violations = []

    def walk(scope):
        outer_sym = next(
            (s for s in scope.get_symbols() if s.get_name() == '_'),
            None,
        )
        if outer_sym and outer_sym.is_assigned():
            for child in scope.get_children():
                inner_sym = next(
                    (s for s in child.get_symbols() if s.get_name() == '_'),
                    None,
                )
                if inner_sym and inner_sym.is_free():
                    violations.append((scope.get_name(), child.get_name()))
        for child in scope.get_children():
            walk(child)

    walk(top)
    return violations


def test_no_underscore_closure_clobber():
    """
    Ensure no GUI module has a function that assigns _ locally (e.g. via
    `for _ in range(n)`) while also defining a closure that captures _ as a
    free variable. Such closures would call an integer instead of the
    translation function.
    """
    src_dir = Path(__file__).parent.parent / 'src'
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    violations_by_module = {
        m: v
        for m in _SOURCE_MODULES
        if (v := _closure_clobbers(m))
    }

    assert violations_by_module == {}, (
        "Found functions that assign to _ locally and have closures that "
        "capture _ as a free variable — rename the loop variable "
        "(e.g. `for _i in range(n)`) to avoid clobbering the translation "
        "function:\n"
        + "\n".join(
            f"  {mod}: {pairs}" for mod, pairs in violations_by_module.items()
        )
    )
