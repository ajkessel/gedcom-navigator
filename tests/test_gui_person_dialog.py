"""Tests for person dialog defensive behavior."""

from gedcom_gui_person_dialog import PersonDialogMixin
from gedcom_gui_results import ResultsMixin
from gedcom_strings import (
    BIO_SECTION,
    FAM_SECTION,
    GEDCOM_SECTION,
    RESULT_PATH_SECTION,
)


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeText:
    def __init__(self):
        self._textbox = self
        self.parts = []

    def insert(self, _index, text, _tags=None):
        self.parts.append(text)

    def tag_configure(self, *_args, **_kwargs):
        pass

    def tag_bind(self, *_args, **_kwargs):
        pass

    def tag_names(self, *_args):
        return []


class Model:
    def find_common_ancestors(self, *_args):
        return []


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


def test_tree_context_profile_stays_in_person_window():
    """Tree View Profile action navigates within the person detail window."""

    class App(PersonDialogMixin):
        def __init__(self):
            self.calls = []

        def _select_person_in_main_tree(self, indi_id):
            self.calls.append(('select', indi_id))

        def _set_display_mode(self, mode):
            self.calls.append(('display', mode))

    app = App()
    navigated = []

    app._show_profile_from_tree_context('@P1@', lambda iid: navigated.append(iid))

    assert navigated == ['@P1@']
    assert app.calls == []


def test_tree_initial_view_uses_configured_default_tree():
    """Opening Tree View starts with the configured tree subview."""

    class Config:
        def get_default_tree(self):
            return 'pedigree'

    class App(PersonDialogMixin):
        def __init__(self):
            self._config = Config()

    app = App()

    assert app._resolve_initial_person_view('tree') == 'pedigree'
    assert app._resolve_initial_person_view('descendant') == 'descendant'
    assert app._resolve_initial_person_view('profile') == 'profile'
    assert app._resolve_initial_person_view(None) == 'profile'


def test_button_bar_needed_width_includes_window_padding():
    """Tree View initial sizing accounts for the full button row."""

    class ButtonFrame:
        def __init__(self):
            self.updated = False

        def update_idletasks(self):
            self.updated = True

        def winfo_reqwidth(self):
            return 820

    frame = ButtonFrame()

    assert PersonDialogMixin._button_bar_needed_width(frame) == 844
    assert frame.updated is True


def test_tree_search_recenters_only_when_person_selected():
    """Tree search leaves the current center unchanged when the picker is cancelled."""

    class App(PersonDialogMixin):
        pass

    app = App()
    recentered = []

    selected = app._search_tree_center_context(lambda: '@P1@', recentered.append)
    cancelled = app._search_tree_center_context(lambda: None, recentered.append)

    assert selected == '@P1@'
    assert cancelled is None
    assert recentered == ['@P1@']


def test_profile_home_path_appears_between_bio_and_full_gedcom():
    """Profile mode inserts the home path before later profile sections."""

    class App(PersonDialogMixin, ResultsMixin):
        def _display_name(self, indi):
            return indi['name']

        def _get_family_members(self, _indi_id):
            return [], [], [], []

        def _show_path_graph(self, *_args):
            pass

    app = App()
    app.individuals = {
        '@A@': {
            'name': 'Alex Person',
            'sex': 'M',
            'famc': [],
            'fams': [],
            'tags': [],
            '_raw': [(0, '@A@', 'INDI', ''),
                     (1, None, 'BIRT', ''),
                     (2, None, 'DATE', '1900')],
        },
        '@H@': {
            'name': 'Home Person',
            'sex': 'M',
            'famc': [],
            'fams': [],
            'tags': [],
            '_raw': [],
        },
    }
    app.families = {}
    app.show_ids = Var(False)
    app.show_full_gedcom = Var(True)
    app._link_color = '#0000ee'
    app._mono_family = 'Courier'
    app._mono_size = 12
    app._model = Model()
    text = FakeText()

    app._insert_person_profile(
        text,
        '@A@',
        lambda _indi_id: None,
        home_paths={
            'home_id': '@H@',
            'paths': [[('@A@', None), ('@H@', 'father')]],
        },
    )
    rendered = ''.join(text.parts)

    assert rendered.index(BIO_SECTION) < rendered.index(RESULT_PATH_SECTION)
    assert rendered.index(BIO_SECTION) < rendered.index(FAM_SECTION)
    assert rendered.index(FAM_SECTION) < rendered.index(RESULT_PATH_SECTION)
    assert rendered.index(RESULT_PATH_SECTION) < rendered.index(GEDCOM_SECTION)
