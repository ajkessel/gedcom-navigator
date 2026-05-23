"""Shared keyboard shortcut metadata for the GUI and tests."""

import sys
from typing import NamedTuple, Optional


class ShortcutSpec(NamedTuple):
    """One keyboard shortcut in a named GUI scope."""

    key: str
    sequence: Optional[str]
    display: str
    action_key: str
    scope: str = "main"


def _platform(platform=None):
    return platform or sys.platform


def modifier_sequence(platform=None):
    """Return the Tk modifier name for command shortcuts."""
    return "Command" if _platform(platform) == "darwin" else "Control"


def modifier_display(platform=None):
    """Return the human-readable modifier label for command shortcuts."""
    return "⌘" if _platform(platform) == "darwin" else "Ctrl+"


def modifier_display_prefix(platform=None):
    """Return modifier text for display labels that include a named key."""
    return "⌘" if _platform(platform) == "darwin" else "Ctrl+"


def display_combo(key, platform=None):
    """Return a human-readable modifier shortcut label."""
    return f"{modifier_display_prefix(platform)}{key}"


def display_named_combo(key, platform=None):
    """Return display text for named keys such as Plus and Minus."""
    return f"⌘+{key}" if _platform(platform) == "darwin" else f"Ctrl+{key}"


def _mod_shortcut(key, action_key, platform=None, scope="main"):
    mod_seq = modifier_sequence(platform)
    return ShortcutSpec(
        key=key,
        sequence=f"<{mod_seq}-{key.lower()}>",
        display=display_combo(key.upper(), platform),
        action_key=action_key,
        scope=scope,
    )


def main_window_shortcuts(platform=None):
    """Return shortcuts registered on the main application window."""
    platform = _platform(platform)
    shortcuts = [
        ShortcutSpec(
            "help",
            "<Command-question>" if platform == "darwin" else "<F1>",
            display_combo("?", platform) if platform == "darwin" else "F1",
            "help",
        ),
        ShortcutSpec(
            "keyboard_shortcuts",
            f"<{modifier_sequence(platform)}-k>" if platform == "darwin" else "<F2>",
            display_combo("K", platform) if platform == "darwin" else "F2",
            "keyboard_shortcuts",
        ),
    ]
    if platform != "darwin":
        shortcuts.append(ShortcutSpec(
            "preferences", "<F3>", "F3", "preferences"))
    shortcuts.extend([
        _mod_shortcut("f", "find_person", platform),
        _mod_shortcut("i", "filter_results", platform),
        _mod_shortcut("d", "toggle_tagged_filter", platform),
        _mod_shortcut("u", "toggle_fuzzy_search", platform),
        _mod_shortcut("m", "toggle_married_name_search", platform),
        _mod_shortcut("p", "display_paths", platform),
        _mod_shortcut("t", "select_tag", platform),
        _mod_shortcut("o", "open_gedcom", platform),
        _mod_shortcut("h", "set_home", platform),
        _mod_shortcut("e", "display_profile", platform),
        _mod_shortcut("s", "save_results", platform),
        _mod_shortcut("n", "display_matches", platform),
        _mod_shortcut("r", "reverse_results", platform),
        ShortcutSpec(
            "back",
            "<Command-Left>" if platform == "darwin" else "<Alt-Left>",
            "⌘←" if platform == "darwin" else "Alt+←",
            "back",
        ),
        ShortcutSpec(
            "forward",
            "<Command-Right>" if platform == "darwin" else "<Alt-Right>",
            "⌘→" if platform == "darwin" else "Alt+→",
            "forward",
        ),
        _mod_shortcut("c", "copy_results", platform),
    ])
    return shortcuts


def shortcut_by_key(key, platform=None):
    """Return a main-window shortcut by stable key."""
    for shortcut in main_window_shortcuts(platform):
        if shortcut.key == key:
            return shortcut
    raise KeyError(key)


def shortcut_by_action(action_key, platform=None):
    """Return a main-window shortcut by action key."""
    for shortcut in main_window_shortcuts(platform):
        if shortcut.action_key == action_key:
            return shortcut
    raise KeyError(action_key)


def keyboard_shortcut_rows(platform=None):
    """Return rows shown in the Keyboard Shortcuts window."""
    rows = list(main_window_shortcuts(platform))
    rows.extend([
        ShortcutSpec("zoom_in_out", None,
                     f"{display_named_combo('Plus', platform)} / "
                     f"{display_named_combo('Minus', platform)}",
                     "zoom_in_out"),
        ShortcutSpec("zoom_reset", None,
                     display_named_combo("0", platform), "zoom_reset"),
    ])
    return rows
