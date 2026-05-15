# -*- mode: python ; coding: utf-8 -*-

import glob
import os
import sys
import subprocess
import re
from PyInstaller.utils.hooks import collect_data_files

# Read version and release date from the single source of truth.
_init_path = os.path.join(SPECPATH, '..', 'gedcom_dna_finder', '__init__.py')
with open(_init_path) as _f:
    _init_src = _f.read()
_app_version = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', _init_src).group(1)
_app_release_date = re.search(r'__release_date__\s*=\s*["\']([^"\']+)["\']', _init_src).group(1)


def check_codesigning_key():
    """
    Checks if a codesigning key exists in the user keychain; if so, use to sign the package.
    """
    identity_name = "Developer ID Application"
    try:
        result = subprocess.run(
            ['security', 'find-identity', '-v', '-p', 'codesigning'],
            capture_output=True,
            text=True,
            check=True
        )
        for line in result.stdout.splitlines():
            if identity_name in line:
                key = re.search(r'[0-9A-Z]{40}', line)
                return (key[0])

    except subprocess.CalledProcessError as e:
        print(f"Error checking keychain: {e}")
        return False


# ffi-8.dll / libffi-8.dll is required by _ctypes.pyd on Windows but is not
# auto-detected by PyInstaller. Conda names it ffi-8.dll (no lib prefix) and
# places it under base_prefix\Library\bin; standard CPython uses libffi-8.dll
# in the executable directory or DLLs\. When building inside a venv backed by
# conda, sys.executable points to the venv Scripts dir but the DLL lives under
# sys.base_prefix (the conda root), so both locations must be searched.
#
# tcl86t.dll / tk86t.dll are required by _tkinter.pyd. Same issue — they live
# under base_prefix\Library\bin, not under the venv Scripts directory.
_extra_binaries = []
_excludes = [
]

if sys.platform != 'darwin':
    # Pillow is needed by the macOS graph clipboard path, but non-macOS builds
    # do not use it at runtime. Exclude it there so customtkinter's optional
    # CTkImage import does not pull helper-only Pillow modules into the bundle.
    _excludes += ['PIL', 'PIL.*']

if sys.platform == 'win32':
    _base = os.path.dirname(sys.executable)
    _conda_base = sys.base_prefix  # resolves to conda root even inside a venv
    for _pat in [
        os.path.join(_base, 'libffi*.dll'),
        os.path.join(_base, 'ffi*.dll'),
        os.path.join(_base, 'DLLs', 'libffi*.dll'),
        os.path.join(_base, 'DLLs', 'ffi*.dll'),
        os.path.join(_base, 'Library', 'bin', 'libffi*.dll'),
        os.path.join(_base, 'Library', 'bin', 'ffi*.dll'),
        # conda places ffi DLLs in base_prefix\Library\bin, not in the venv
        os.path.join(_conda_base, 'libffi*.dll'),
        os.path.join(_conda_base, 'ffi*.dll'),
        os.path.join(_conda_base, 'DLLs', 'libffi*.dll'),
        os.path.join(_conda_base, 'DLLs', 'ffi*.dll'),
        os.path.join(_conda_base, 'Library', 'bin', 'libffi*.dll'),
        os.path.join(_conda_base, 'Library', 'bin', 'ffi*.dll'),
        # TCL/TK DLLs — conda-forge places these in base_prefix, not the venv
        os.path.join(_conda_base, 'DLLs', 'tk*.dll'),
        os.path.join(_conda_base, 'DLLs', 'tcl*.dll'),
        os.path.join(_conda_base, 'Library', 'bin', 'tk*.dll'),
        os.path.join(_conda_base, 'Library', 'bin', 'tcl*.dll'),
    ]:
        _extra_binaries += [(p, '.') for p in glob.glob(_pat)]

a = Analysis(
    ['../src/gedcom_dna_finder_gui.py'],
    pathex=[],
    binaries=_extra_binaries,
    datas=[('../docs/HELP.md', './docs'), ('../docs/LICENSE.md', './docs'),
           ('../docs/KEYBOARD_SHORTCUTS.md', './docs'), ('../docs/PRIVACY_POLICY.md', './docs'),
           ('../icons/family_tree.ico', './icons'), ('../icons/family_tree.png', './icons'),
           ('../gedcom_dna_finder/__init__.py', 'gedcom_dna_finder')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='gedcom-dna-finder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['../icons/family_tree.ico'],
)

if sys.platform == 'darwin':
    exe = EXE(pyz,
              a.scripts,
              exclude_binaries=True,
              name='gedcom-dna-finder',
              codesign_identity=check_codesigning_key(),
              entitlements_file=os.path.join(SPECPATH, 'entitlements.plist'),
              target_arch='universal2',
              console=False)

    coll = COLLECT(exe,
                   a.binaries,
                   a.zipfiles,
                   a.datas,
                   strip=False,
                   upx=True,
                   name='gedcom-dna-finder.app')

    app = BUNDLE(coll,
                 name='gedcom-dna-finder.app',
                 icon='../icons/family_tree.icns',
                 bundle_identifier='com.ajkessel.gedcom-dna-finder',
                 info_plist={
                     'CFBundleName': 'GEDCOM DNA Finder',
                     'CFBundleDisplayName': 'GEDCOM DNA Finder',
                     'CFBundleSupportedPlatforms': ['MacOSX'],
                     'LSMinimumSystemVersion': '10.13.0',
                     'CFBundleIdentifier': 'com.ajkessel.gedcom-dna-finder',
                     'CFBundleShortVersionString': _app_version,
                     'CFBundleVersion': _app_version,
                     'NSHumanReadableCopyright': f'Copyright {_app_release_date[:4]} Adam Kessel',
                     'NSHighResolutionCapable': True,
                     'LSApplicationCategoryType': 'public.app-category.utilities',
                     'ITSAppUsesNonExemptEncryption': False,
                 })
