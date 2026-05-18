#!/usr/bin/env python3
"""
gedcom_config.py

Typed persistence layer for settings.json — no GUI imports.
"""

import json
import sys
from pathlib import Path


class ConfigManager:
    """Read/write a single settings.json file; all I/O is isolated here."""

    def __init__(self, config_path: Path):
        """Create a manager backed by the given settings file path."""
        self._path = config_path

    # ------------------------------------------------------------------
    # Generic key/value accessors
    # ------------------------------------------------------------------

    def load_value(self, key, default=None):
        """Return a saved value for key, or default if it is missing or unreadable."""
        try:
            data = json.loads(self._path.read_text(encoding='utf-8'))
            return data.get(key, default)
        except Exception:  # pylint: disable=broad-exception-caught
            return default

    def save_value(self, key, value):
        """Persist a single setting value while preserving other saved settings."""
        try:
            data = json.loads(self._path.read_text(encoding='utf-8'))
        except Exception:  # pylint: disable=broad-exception-caught
            data = {}
        data[key] = value
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    # ------------------------------------------------------------------
    # Typed accessors
    # ------------------------------------------------------------------

    def get_recent_files(self):
        """Return saved recent GEDCOM file paths, discarding non-string entries."""
        raw = self.load_value('recent_files', [])
        return [p for p in raw if isinstance(p, str)]

    def set_recent_files(self, files):
        """Save the ordered list of recent GEDCOM file paths."""
        self.save_value('recent_files', files)

    def get_home_person(self, gedcom_path):
        """Return the saved home person ID for a GEDCOM path, if one exists."""
        return self.load_value('home_persons', {}).get(gedcom_path)

    def set_home_person(self, gedcom_path, indi_id):
        """Save the home person ID associated with a GEDCOM path."""
        home_persons = self.load_value('home_persons', {})
        home_persons[gedcom_path] = indi_id
        self.save_value('home_persons', home_persons)

    def get_font_preference(self, valid_sizes):
        """Return a saved font size preference, falling back to medium if invalid."""
        pref = self.load_value('font_size', 'medium')
        return pref if pref in valid_sizes else 'medium'

    def set_font_preference(self, size_name):
        """Save the selected font size preference name."""
        self.save_value('font_size', size_name)

    def get_theme_preference(self, valid_themes):
        """Return a saved theme preference, falling back to System if invalid."""
        pref = self.load_value('theme', 'System')
        return pref if pref in valid_themes else 'System'

    def set_theme_preference(self, theme_name):
        """Save the selected theme preference name."""
        self.save_value('theme', theme_name)

    def get_window_geometry(self, key):
        """Return saved window geometry for the given key, if present."""
        return self.load_value(key)

    def set_window_geometry(self, key, geometry):
        """Save window geometry under the given settings key."""
        self.save_value(key, geometry)

    def get_top_n(self, default=3):
        """Return the positive number of closest matches to show."""
        val = self.load_value('top_n', default)
        try:
            return max(1, int(val))
        except (TypeError, ValueError):
            return default

    def set_top_n(self, value):
        """Save the number of closest matches to show."""
        self.save_value('top_n', int(value))

    def get_max_depth(self, default=10):
        """Return the positive maximum ancestor search depth."""
        val = self.load_value('max_depth', default)
        try:
            return max(1, int(val))
        except (TypeError, ValueError):
            return default

    def set_max_depth(self, value):
        """Save the maximum ancestor search depth."""
        self.save_value('max_depth', int(value))

    def get_fuzzy_threshold(self, default=0.72):
        """Return the fuzzy match threshold clamped to the inclusive range 0.0 to 1.0."""
        val = self.load_value('fuzzy_threshold', default)
        try:
            return min(1.0, max(0.0, float(val)))
        except (TypeError, ValueError):
            return default

    def set_fuzzy_threshold(self, value):
        """Save the fuzzy match threshold as a floating-point value."""
        self.save_value('fuzzy_threshold', float(value))

    def get_max_display(self, default=2000):
        """Return the maximum number of people shown in the search results list."""
        val = self.load_value('max_display', default)
        try:
            return max(1, int(val))
        except (TypeError, ValueError):
            return default

    def set_max_display(self, value):
        """Save the maximum number of people shown in the search results list."""
        self.save_value('max_display', int(value))

    def get_show_ids(self):
        """Return whether individual IDs should be shown in the UI."""
        return bool(self.load_value('show_ids', False))

    def set_show_ids(self, value):
        """Save whether individual IDs should be shown in the UI."""
        self.save_value('show_ids', bool(value))

    def get_name_order(self):
        """Return the saved display name order, defaulting to first-name first."""
        val = self.load_value('name_order', 'first_last')
        return val if val in ('first_last', 'last_first') else 'first_last'

    def set_name_order(self, value):
        """Save the display name order preference."""
        self.save_value('name_order', value)

    def get_hide_tooltips(self):
        """Return whether tooltips should be suppressed."""
        return bool(self.load_value('hide_tooltips', False))

    def set_hide_tooltips(self, value):
        """Save whether tooltips should be suppressed."""
        self.save_value('hide_tooltips', bool(value))

    def get_profile_view_default(self):
        """Return the default view for the profile window ('profile' or 'tree')."""
        val = self.load_value('profile_view_default', 'profile')
        return val if val in ('profile', 'tree') else 'profile'

    def set_profile_view_default(self, value):
        """Save the default view for the profile window."""
        self.save_value('profile_view_default', value)

    # ------------------------------------------------------------------
    # Platform default path
    # ------------------------------------------------------------------

    @staticmethod
    def default_path():
        """Return the platform-specific default settings.json path."""
        if sys.platform == 'win32':
            import os
            base = Path(os.environ.get('APPDATA', Path.home()))
        elif sys.platform == 'darwin':
            base = Path.home() / 'Library' / 'Application Support'
        else:
            import os
            base = Path(os.environ.get(
                'XDG_CONFIG_HOME', Path.home() / '.config'))
        return base / 'gedcom-dna-finder' / 'settings.json'
