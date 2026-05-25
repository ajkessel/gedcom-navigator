"""Tests for family tree expansion button visibility."""

from gedcom_gui_results import ResultsMixin


def test_expansion_button_omits_active_category_without_members():
    """An expanded category with no relatives should not render a button."""
    options = {
        'parents': [],
        'siblings': [],
        'spouses': [],
        'children': [],
    }
    expanded = {('@A@', 'spouses')}
    members = {
        'parents': [],
        'siblings': [],
        'spouses': [],
        'children': [],
    }

    assert ResultsMixin._show_expansion_button(
        options, expanded, '@A@', 'spouses', members) is False


def test_expansion_button_keeps_active_category_with_visible_members():
    """An expanded category with visible relatives keeps its collapse button."""
    options = {
        'parents': [],
        'siblings': [],
        'spouses': [],
        'children': [],
    }
    expanded = {('@A@', 'spouses')}
    members = {
        'parents': [],
        'siblings': [],
        'spouses': ['@B@'],
        'children': [],
    }

    assert ResultsMixin._show_expansion_button(
        options, expanded, '@A@', 'spouses', members) is True
