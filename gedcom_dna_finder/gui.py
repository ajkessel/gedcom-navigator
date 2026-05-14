"""
Entry point for the GEDCOM DNA Finder GUI.

When installed via pip the actual GUI script lives in _scripts/ (placed there
by hatch_build.py during the wheel build).  When running from a source
checkout the script is found in the sibling src/ directory instead.
"""

import importlib.util
import os
import sys


def _scripts_dir():
    pkg = os.path.dirname(os.path.abspath(__file__))
    # Installed wheel: scripts are bundled inside the package.
    installed = os.path.join(pkg, "_scripts")
    if os.path.isdir(installed):
        return installed
    # Source checkout: scripts live in src/ next to the repo root.
    dev = os.path.join(os.path.dirname(pkg), "src")
    if os.path.isdir(dev):
        return dev
    return None


def main():
    """Wrapper used only for pypi build to launch the GUI."""
    sd = _scripts_dir()
    if sd is None:
        raise RuntimeError(
            "Cannot locate gedcom_dna_finder_gui.py. "
            "Re-install the package or run from the source tree."
        )
    if sd not in sys.path:
        sys.path.insert(0, sd)
    script = os.path.join(sd, "gedcom_dna_finder_gui.py")
    spec = importlib.util.spec_from_file_location(
        "gedcom_dna_finder_gui", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gedcom_dna_finder_gui"] = mod
    spec.loader.exec_module(mod)
    mod.main()
