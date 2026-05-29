#!/usr/bin/env python3
"""
gedcom_file_association.py

Register the application as a handler for ``.ged`` files — no GUI imports.

Two tiers, both isolated here so the GUI never touches ``winreg`` / pyobjc /
``xdg-mime`` directly:

* :func:`ensure_can_open` — silent, idempotent registration declaring that the
  app is *able* to open ``.ged`` (run on every frozen launch).
* :func:`is_default_handler` / :func:`set_as_default` — query and set the app as
  the *default* ``.ged`` handler, driven by the once-per-version prompt.

Only frozen/installed builds register or prompt (see :func:`can_register`).
Heavy platform modules are imported lazily inside the functions that need them,
and every public function is exception-wrapped so startup can never crash on a
registration failure.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from gedcom_debug import log_exception

GED_EXTENSION = ".ged"
PROGID = "ajkessel.gedcom-navigator.ged"          # Windows ProgID
MAC_UTI = "com.ajkessel.gedcom-navigator.ged"     # exported UTI (declared in Info.plist)
LINUX_MIME_TYPE = "application/x-gedcom"
DESKTOP_FILE = "gedcom-navigator.desktop"
BUNDLE_ID = "com.ajkessel.gedcom-navigator"
_TYPE_DESCRIPTION = "GEDCOM File"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _bundle_base():
    """Return the directory bundled resources live under (frozen or source)."""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app_command_target():
    """Return the executable to register as the open-command (frozen exe)."""
    return sys.executable


def association_supported():
    """Return whether file-association registration is implemented on this OS."""
    return sys.platform in ('win32', 'darwin', 'linux')


def can_register():
    """Return whether this build should self-register and prompt.

    True only for frozen builds that are *not* running from a context we must
    not write associations from: the sandboxed macOS App Store build or a
    Windows MSIX package (both declare via their manifest instead).
    """
    if not (association_supported() and getattr(sys, 'frozen', False)):
        return False
    if sys.platform == 'darwin' and os.environ.get('APP_SANDBOX_CONTAINER_ID'):
        return False
    if sys.platform == 'win32' and 'windowsapps' in (sys.executable or '').lower():
        return False
    return True


def ensure_can_open():
    """Idempotently register the app as *able* to open ``.ged`` (no prompt)."""
    try:
        if sys.platform == 'win32':
            _win_ensure_can_open()
        elif sys.platform == 'linux':
            _linux_ensure_can_open()
        # macOS declares document types via Info.plist; Launch Services
        # auto-registers them, so there is nothing to do at runtime.
    except Exception:  # pylint: disable=broad-exception-caught
        log_exception("registering .ged open capability")


def is_default_handler():
    """Return True/False if the app is the default ``.ged`` handler, else None."""
    try:
        if sys.platform == 'win32':
            return _win_is_default()
        if sys.platform == 'darwin':
            return _mac_is_default()
        if sys.platform == 'linux':
            return _linux_is_default()
    except Exception:  # pylint: disable=broad-exception-caught
        log_exception("querying default .ged handler")
    return None


def set_as_default():
    """Make the app the default ``.ged`` handler. Return True on success."""
    try:
        if sys.platform == 'win32':
            return _win_set_default()
        if sys.platform == 'darwin':
            return _mac_set_default()
        if sys.platform == 'linux':
            return _linux_set_default()
    except Exception:  # pylint: disable=broad-exception-caught
        log_exception("setting default .ged handler")
    return False


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def _win_set_value(subkey, value, name=""):
    """Create ``HKCU\\<subkey>`` and set a string value (default if name='')."""
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, subkey) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _win_ensure_can_open():
    """Register the ProgID + open-command and list it under OpenWithProgids."""
    import winreg
    exe = _app_command_target()
    base = r"Software\Classes\%s" % PROGID
    _win_set_value(base, _TYPE_DESCRIPTION)
    _win_set_value(base + r"\DefaultIcon", '"%s",0' % exe)
    _win_set_value(base + r"\shell\open\command", '"%s" "%%1"' % exe)
    # Advertise the ProgID as an "open with" option without forcing default.
    with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Classes\%s\OpenWithProgids" % GED_EXTENSION) as key:
        winreg.SetValueEx(key, PROGID, 0, winreg.REG_NONE, b"")


def _win_is_default():
    """True iff ``.ged`` resolves to our ProgID (UserChoice or class default)."""
    import winreg
    progid = None
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                r"\FileExts\.ged\UserChoice") as key:
            progid = winreg.QueryValueEx(key, "ProgId")[0]
    except FileNotFoundError:
        pass
    if progid is None:
        try:
            with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Classes\%s" % GED_EXTENSION) as key:
                progid = winreg.QueryValueEx(key, "")[0]
        except FileNotFoundError:
            return False
    return progid == PROGID


def _win_set_default():
    """Point ``.ged`` at our ProgID and refresh Explorer's association cache."""
    import ctypes
    _win_ensure_can_open()
    _win_set_value(r"Software\Classes\%s" % GED_EXTENSION, PROGID)
    # SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    return _win_is_default()


# ---------------------------------------------------------------------------
# macOS (Launch Services via pyobjc)
# ---------------------------------------------------------------------------

def _mac_is_default():
    """Compare the default handler for our UTI against this app's bundle id."""
    from CoreServices import (  # pylint: disable=import-outside-toplevel
        LSCopyDefaultRoleHandlerForContentType, kLSRolesAll)
    handler = LSCopyDefaultRoleHandlerForContentType(MAC_UTI, kLSRolesAll)
    if not handler:
        return False
    return str(handler).lower() == BUNDLE_ID.lower()


def _mac_set_default():
    """Set this app as the default handler for our exported UTI."""
    from CoreServices import (  # pylint: disable=import-outside-toplevel
        LSSetDefaultRoleHandlerForContentType, kLSRolesAll)
    status = LSSetDefaultRoleHandlerForContentType(
        MAC_UTI, kLSRolesAll, BUNDLE_ID)
    return status == 0


# ---------------------------------------------------------------------------
# Linux (freedesktop.org: .desktop + shared-mime-info + xdg-mime)
# ---------------------------------------------------------------------------

_MIME_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">\n'
    '  <mime-type type="%s">\n'
    '    <comment>GEDCOM genealogy file</comment>\n'
    '    <glob pattern="*.ged"/>\n'
    '    <magic priority="50"><match type="string" value="0 HEAD" offset="0"/></magic>\n'
    '  </mime-type>\n'
    '</mime-info>\n'
) % LINUX_MIME_TYPE


def _linux_data_home():
    """Return ``$XDG_DATA_HOME`` or its default ``~/.local/share``."""
    return Path(os.environ.get(
        'XDG_DATA_HOME', Path.home() / '.local' / 'share'))


def _linux_desktop_entry():
    """Return the .desktop file contents pointing at the current executable."""
    exe = _app_command_target()
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=GEDCOM Navigator\n"
        "Comment=Explore GEDCOM family tree files\n"
        'Exec="%s" %%f\n'
        "Icon=gedcom-navigator\n"
        "Terminal=false\n"
        "MimeType=%s;\n"
        "Categories=Utility;\n"
    ) % (exe, LINUX_MIME_TYPE)


def _linux_ensure_can_open():
    """Install the MIME definition, .desktop launcher, and icon under ~/.local."""
    data_home = _linux_data_home()
    mime_pkg = data_home / 'mime' / 'packages'
    apps = data_home / 'applications'
    mime_pkg.mkdir(parents=True, exist_ok=True)
    apps.mkdir(parents=True, exist_ok=True)

    (mime_pkg / 'gedcom-navigator.xml').write_text(_MIME_XML, encoding='utf-8')
    (apps / DESKTOP_FILE).write_text(_linux_desktop_entry(), encoding='utf-8')

    icon_src = os.path.join(_bundle_base(), 'icons', 'family_tree.png')
    if os.path.isfile(icon_src):
        icon_dir = data_home / 'icons' / 'hicolor' / '256x256' / 'apps'
        icon_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(icon_src, icon_dir / 'gedcom-navigator.png')

    if shutil.which('update-mime-database'):
        subprocess.run(['update-mime-database', str(data_home / 'mime')],
                       check=False, capture_output=True)
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(apps)],
                       check=False, capture_output=True)


def _linux_is_default():
    """Return True/False from ``xdg-mime query default``, or None if unavailable."""
    if not shutil.which('xdg-mime'):
        return None
    result = subprocess.run(
        ['xdg-mime', 'query', 'default', LINUX_MIME_TYPE],
        check=False, capture_output=True, text=True)
    return result.stdout.strip() == DESKTOP_FILE


def _linux_set_default():
    """Run ``xdg-mime default`` for our .desktop file. Return True on success."""
    if not shutil.which('xdg-mime'):
        return False
    _linux_ensure_can_open()
    subprocess.run(
        ['xdg-mime', 'default', DESKTOP_FILE, LINUX_MIME_TYPE],
        check=False, capture_output=True)
    return _linux_is_default() is True
