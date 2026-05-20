"""Static checks for GUI mixin split imports."""

import builtins
import importlib
import symtable
from pathlib import Path


GUI_SPLIT_MODULES = (
    'gedcom_gui_results',
    'gedcom_gui_graph_common',
    'gedcom_gui_path_graph',
    'gedcom_gui_family_tree_render',
    'gedcom_gui_graph_layout',
    'gedcom_gui_dialogs',
    'gedcom_gui_person_dialog',
    'gedcom_gui_help_dialogs',
)


def _unresolved_global_names(module_name):
    module = importlib.import_module(module_name)
    source_path = Path(module.__file__)
    symbols = symtable.symtable(
        source_path.read_text(encoding='utf-8'),
        str(source_path),
        'exec',
    )
    available = set(module.__dict__) | set(dir(builtins))
    unresolved = set()

    def walk(scope):
        for child in scope.get_children():
            for symbol in child.get_symbols():
                name = symbol.get_name()
                if (symbol.is_referenced() and symbol.is_global()
                        and name not in available):
                    unresolved.add(name)
            walk(child)

    walk(symbols)
    return sorted(unresolved)


def test_gui_split_modules_have_no_unresolved_global_references():
    """Catch moved callback helpers whose imports were not moved with them."""
    missing_by_module = {
        module_name: missing
        for module_name in GUI_SPLIT_MODULES
        if (missing := _unresolved_global_names(module_name))
    }

    assert missing_by_module == {}
