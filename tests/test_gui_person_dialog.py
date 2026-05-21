"""Tests for person dialog defensive behavior."""

from gedcom_gui_person_dialog import PersonDialogMixin


class Button:
    def __init__(self):
        self.configs = []

    def configure(self, **kwargs):
        self.configs.append(kwargs)


class Tooltip:
    def __init__(self):
        self.texts = []

    def update_text(self, text):
        self.texts.append(text)


def test_show_person_for_missing_id_warns_without_opening_window(monkeypatch):
    """Stale callbacks should not build a profile/tree window for missing IDs."""

    class App(PersonDialogMixin):
        pass

    app = App()
    app.individuals = {}
    warnings = []
    monkeypatch.setattr(
        'gedcom_gui_person_dialog.messagebox.showwarning',
        lambda title, message: warnings.append((title, message)),
    )

    app._show_person_for('@OLD@', initial_view='tree')

    assert warnings
    assert not hasattr(app, '_secondary_win')


def test_update_show_person_button_uses_dynamic_i18n_tooltips(monkeypatch):
    """Shift toggling uses current tooltip helpers instead of removed constants."""

    class App(PersonDialogMixin):
        def _show_person(self, initial_view=None):
            return initial_view

    monkeypatch.setattr(
        'gedcom_gui_person_dialog.get_tip_show_person',
        lambda: 'profile tip',
    )
    monkeypatch.setattr(
        'gedcom_gui_person_dialog.get_tip_show_person_tree',
        lambda: 'tree tip',
    )
    app = App()
    app._default_profile_view = 'tree'
    app.show_person_btn = Button()
    app._show_person_tooltip = Tooltip()

    app._update_show_person_btn_for_shift(True)
    app._update_show_person_btn_for_shift(False)

    assert app._show_person_tooltip.texts == ['profile tip', 'tree tip']
