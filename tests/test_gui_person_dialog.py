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


def test_tree_context_profile_closes_window_and_shows_display_profile():
    """Tree View Profile action moves the selected person to the Display Pane."""

    class Root:
        def after_idle(self, callback):
            callback()

    class App(PersonDialogMixin):
        def __init__(self):
            self.root = Root()
            self.calls = []

        def _select_person_in_main_tree(self, indi_id):
            self.calls.append(('select', indi_id))

        def _set_display_mode(self, mode):
            self.calls.append(('display', mode))

    app = App()
    closed = []

    app._show_profile_from_tree_context('@P1@', lambda: closed.append(True))

    assert closed == [True]
    assert app.calls == [('select', '@P1@'), ('display', 'profile')]


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
