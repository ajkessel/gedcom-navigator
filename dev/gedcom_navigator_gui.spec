# -*- mode: python ; coding: utf-8 -*-

import glob
import os
import sys
import subprocess
import re
from PyInstaller.utils.hooks import collect_data_files
if sys.platform == 'darwin':
    import certifi

# Read version and release date from the single source of truth.
_init_path = os.path.join(SPECPATH, '..', 'gedcom_navigator', '__init__.py')
with open(_init_path) as _f:
    _init_src = _f.read()
_app_version = re.search(
    r'__version__\s*=\s*["\']([^"\']+)["\']', _init_src).group(1)
_app_release_date = re.search(
    r'__release_date__\s*=\s*["\']([^"\']+)["\']', _init_src).group(1)


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
_excludes = []

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
        # OpenSSL DLLs — required for HTTPS (check for updates)
        os.path.join(_conda_base, 'Library', 'bin', 'libssl*.dll'),
        os.path.join(_conda_base, 'Library', 'bin', 'libcrypto*.dll'),
    ]:
        _extra_binaries += [(p, '.') for p in glob.glob(_pat)]

d = [('../docs/HELP.md', './docs'), ('../docs/LICENSE.md', './docs'),
     ('../docs/KEYBOARD_SHORTCUTS.md',
     './docs'), ('../docs/PRIVACY_POLICY.md', './docs'),
     ('../icons/gedcom_navigator.ico', './icons'), ('../icons/gedcom_navigator.png', './icons'),
     ('../gedcom_navigator/__init__.py', 'gedcom_navigator'),
     ('../samples/fictional_genealogy.ged', './samples'),
     ('../locales', './locales')]

# package certificates for MacOS since python.org does not include them by default
if sys.platform == 'darwin':
    d.append((certifi.where(), 'certifi'))

a = Analysis(
    ['../src/gedcom_navigator_gui.py'],
    datas=d,
    pathex=[],
    binaries=_extra_binaries,
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
    name='gedcom-navigator',
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
    icon=['../icons/gedcom_navigator.ico'],
)

if sys.platform == 'darwin':
    target_arch = os.environ.get('target_arch', 'universal2')
    exe = EXE(pyz,
              a.scripts,
              exclude_binaries=True,
              name='gedcom-navigator',
              codesign_identity=check_codesigning_key(),
              entitlements_file=os.path.join(SPECPATH, 'entitlements.plist'),
              target_arch=target_arch,
              console=False)

    coll = COLLECT(exe,
                   a.binaries,
                   a.zipfiles,
                   a.datas,
                   strip=False,
                   upx=True,
                   name='gedcom-navigator.app')

    app = BUNDLE(coll,
                 name='gedcom-navigator.app',
                 icon='../icons/gedcom_navigator.icns',
                 bundle_identifier='com.ajkessel.gedcom-navigator',
                 info_plist={
                     'CFBundleName': 'GEDCOM Navigator',
                     'CFBundleDisplayName': 'GEDCOM Navigator',
                     'CFBundleSupportedPlatforms': ['MacOSX'],
                     'LSMinimumSystemVersion': '10.13.0',
                     'CFBundleIdentifier': 'com.ajkessel.gedcom-navigator',
                     'CFBundleShortVersionString': _app_version,
                     'CFBundleVersion': _app_version,
                     'NSHumanReadableCopyright': f'Copyright {_app_release_date[:4]} Adam Kessel',
                     'NSHighResolutionCapable': True,
                     'LSApplicationCategoryType': 'public.app-category.utilities',
                     'ITSAppUsesNonExemptEncryption': False,
                     'CFBundleDocumentTypes': [{
                         'CFBundleTypeName': 'GEDCOM File',
                         'CFBundleTypeRole': 'Editor',
                         'LSHandlerRank': 'Owner',
                         'LSItemContentTypes': ['com.ajkessel.gedcom-navigator.ged'],
                         'CFBundleTypeIconFile': 'gedcom_navigator.icns',
                     }],
                     'UTExportedTypeDeclarations': [{
                         'UTTypeIdentifier': 'com.ajkessel.gedcom-navigator.ged',
                         'UTTypeDescription': 'GEDCOM Genealogy File',
                         'UTTypeConformsTo': ['public.plain-text', 'public.data'],
                         'UTTypeTagSpecification': {
                             'public.filename-extension': ['ged'],
                         },
                     }],
                 })
