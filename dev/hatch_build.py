"""
hatch_build.py — custom Hatchling build hook for gedcom-navigator.

Runs automatically during `python -m build dev/ --outdir dist/`.

What it does
------------
1. Copies every *.py file from src/ into gedcom_navigator/_scripts/ so the
   GUI and CLI entry-point shims can find them at runtime after pip install.
2. Copies docs/ and icons/ into the package so _resource_path() in the GUI
   resolves correctly (it looks two directories above __file__, which is
   gedcom_navigator/_scripts/, landing on gedcom_navigator/).
3. The static [tool.hatch.build.targets.wheel.force-include] entry in
   pyproject.toml then picks up the entire gedcom_navigator/ tree.
4. Cleans up the temporary copies after the wheel is written so the working
   tree stays tidy.

Note: this file lives in dev/ alongside pyproject.toml.  self.root is
therefore the absolute path to dev/, and the repo root is self.root's parent.
"""

import shutil
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    # Top-level repo directories that are copied into the package.
    _ASSET_DIRS = ("docs", "icons")

    def initialize(self, version, build_data):
        hook_dir = Path(self.root)

        # When building from the source tree, self.root is dev/ and the repo
        # root is its parent.  When building a wheel from an extracted sdist
        # (the second phase of `python -m build`), the sdist includes src/
        # and gedcom_navigator/ as siblings of hatch_build.py, so self.root
        # itself is the effective repo root.
        if (hook_dir.parent / "src").exists():
            repo = hook_dir.parent   # source-tree build
        elif (hook_dir / "src").exists():
            repo = hook_dir          # wheel-from-sdist build
        else:
            return                   # can't locate sources — skip

        pkg = repo / "gedcom_navigator"
        pkg.mkdir(parents=True, exist_ok=True)

        # --- scripts -------------------------------------------------------
        scripts_dst = pkg / "_scripts"
        if scripts_dst.exists():
            shutil.rmtree(scripts_dst)
        scripts_dst.mkdir()
        for py in (repo / "src").glob("*.py"):
            shutil.copy2(py, scripts_dst / py.name)

        # --- assets (docs, icons) ------------------------------------------
        for name in self._ASSET_DIRS:
            src_dir = repo / name
            dst_dir = pkg / name
            if dst_dir.exists():
                shutil.rmtree(dst_dir)
            if src_dir.exists():
                shutil.copytree(src_dir, dst_dir)

        # Tell hatchling to include the populated package directory in the wheel.
        # Using a dynamic entry here (rather than a static pyproject.toml path)
        # so it resolves to the correct absolute path whether we're in the real
        # source tree or a temp sdist extraction directory.
        build_data["force_include"][str(pkg)] = "gedcom_navigator"

    def finalize(self, version, build_data, artifact_path):
        pkg = Path(self.root).parent / "gedcom_navigator"
        for name in ("_scripts", *self._ASSET_DIRS):
            target = pkg / name
            if target.exists():
                shutil.rmtree(target)
