"""
Entry point for the GEDCOM DNA Finder CLI.

When installed via pip the actual CLI script lives in _scripts/ (placed there
by hatch_build.py during the wheel build).  When running from a source
checkout the script is found in the sibling src/ directory instead.
"""

import importlib.util
import os
import sys


def _scripts_dir():
    pkg = os.path.dirname(os.path.abspath(__file__))
    installed = os.path.join(pkg, "_scripts")
    if os.path.isdir(installed):
        return installed
    dev = os.path.join(os.path.dirname(pkg), "src")
    if os.path.isdir(dev):
        return dev
    return None


def main():
    """Wrapper used only for pypi build to launch the CLI."""
    sd = _scripts_dir()
    if sd is None:
        raise RuntimeError(
            "Cannot locate gedcom_dna_finder_cli.py. "
            "Re-install the package or run from the source tree."
        )
    if sd not in sys.path:
        sys.path.insert(0, sd)
    script = os.path.join(sd, "gedcom_dna_finder_cli.py")
    spec = importlib.util.spec_from_file_location("gedcom_dna_finder_cli", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gedcom_dna_finder_cli"] = mod
    spec.loader.exec_module(mod)
    mod.main()
