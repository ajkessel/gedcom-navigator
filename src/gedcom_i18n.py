import gettext
import os
import sys
from pathlib import Path

from gedcom_debug import log_exception

def setup_i18n(lang_code=None):
    """
    Initialize gettext for the application.
    If lang_code is 'sys' or None, it will try to use the system locale.
    """
    # Locate the locales directory
    if getattr(sys, 'frozen', False):
        # Running as a bundled executable
        base_dir = Path(sys._MEIPASS)
    else:
        # Running from source
        base_dir = Path(__file__).parent.parent

    locales_dir = base_dir / 'locales'
    
    # Ensure the directory exists (or gettext will fail silently or loudly)
    if not locales_dir.exists():
        locales_dir.mkdir(parents=True, exist_ok=True)

    if lang_code == 'sys':
        lang_code = None
    
    if lang_code == 'iw':
        lang_code = 'he'
        
    languages = [lang_code] if lang_code else None
    
    try:
        translation = gettext.translation(
            'gedcom_navigator',
            localedir=str(locales_dir),
            languages=languages,
            fallback=True
        )
        translation.install()
        return translation.gettext
    except Exception:  # pylint: disable=broad-exception-caught
        # Fallback to a dummy translator if something goes wrong
        log_exception(f"setting up gettext for language {lang_code!r}")
        return lambda s: s

# Initial dummy _ so modules can define strings before setup_i18n is called.
# It is dynamic: if a real gettext is installed in builtins, it delegates to it.
def _(s):
    import builtins
    real_gettext = getattr(builtins, '_', None)
    if real_gettext and real_gettext is not _:
        return real_gettext(s)
    return s

def get_available_languages():
    """
    Return a list of (display_name, lang_code) for available translations.
    """
    # Locate the locales directory
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).parent.parent

    locales_dir = base_dir / 'locales'
    
    # Map of codes to names (add more as needed)
    code_to_name = {
        'en': 'English',
        'fr': 'Français',
        'de': 'Deutsch',
        'es': 'Español',
        'it': 'Italiano',
        'iw': 'Hebrew (עברית)',
        'he': 'Hebrew (עברית)',
        'ru': 'Русский',
        'zh': '中文',
        'ja': '日本語',
    }
    
    langs = [('System Default', 'sys'), ('English', 'en')]
    seen = {'en', 'sys'}
    
    if locales_dir.exists():
        for item in locales_dir.iterdir():
            if item.is_dir() and (item / 'LC_MESSAGES').exists():
                code = item.name
                if code not in seen:
                    name = code_to_name.get(code, code)
                    langs.append((name, code))
                    seen.add(code)
    
    return langs
