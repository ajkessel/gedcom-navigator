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
        self.inserted = []
        self.bindings = {}
        self.configured_tags = {}
        self.deleted_tags = []

    def insert(self, _index, text, _tags=None):
        self.parts.append(text)
        self.inserted.append((text, _tags))

    def tag_configure(self, *_args, **_kwargs):
        if _args:
            self.configured_tags[_args[0]] = _kwargs

    def tag_bind(self, tag, sequence, callback=None, **_kwargs):
        self.bindings[(tag, sequence)] = callback

    def tag_names(self, *_args):
        return list(self.configured_tags)

    def tag_delete(self, tag):
        self.deleted_tags.append(tag)


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


def test_add_canvas_highlighted_node_redraws_only_when_added():
    """Tree jump highlighting redraws when it marks a newly selected person."""

    class Canvas:
        def __init__(self):
            self._highlighted_nodes = {'@A@'}
            self.redraws = 0
            self._redraw_fn = self._redraw

        def _redraw(self):
            self.redraws += 1

    canvas = Canvas()

    added = PersonDialogMixin._add_canvas_highlighted_node(canvas, '@B@')
    unchanged = PersonDialogMixin._add_canvas_highlighted_node(canvas, '@B@')

    assert added is True
    assert unchanged is False
    assert canvas._highlighted_nodes == {'@A@', '@B@'}
    assert canvas.redraws == 1


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


def test_full_gedcom_https_urls_are_clickable(monkeypatch):
    """Full GEDCOM Record URLs are rendered as browser links."""

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
            '_raw': [
                (0, '@A@', 'INDI', ''),
                (1, None, 'WWW', 'https://example.com/person?x=1.'),
                (1, None, 'NOTE', 'See https://example.org/a and https://b.test/z)'),
            ],
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
    opened = []
    monkeypatch.setattr(
        'gedcom_gui_person_dialog.webbrowser.open', lambda url: opened.append(url)
    )

    app._insert_person_profile(text, '@A@', lambda _indi_id: None)

    rendered = ''.join(text.parts)
    assert '1 WWW https://example.com/person?x=1.' in rendered
    assert 'gedcom_url_link' not in text.deleted_tags
    assert ('gedcom_url_link', 'gedcom_url_0') in [
        tags for part, tags in text.inserted
        if part == 'https://example.com/person?x=1'
    ]
    assert ('gedcom_url_link', 'gedcom_url_1') in [
        tags for part, tags in text.inserted
        if part == 'https://example.org/a'
    ]
    assert ('gedcom_url_link', 'gedcom_url_2') in [
        tags for part, tags in text.inserted
        if part == 'https://b.test/z'
    ]

    text.bindings[('gedcom_url_0', '<Button-1>')](None)
    text.bindings[('gedcom_url_2', '<Button-1>')](None)

    assert opened == ['https://example.com/person?x=1', 'https://b.test/z']


def test_profile_labels_non_biological_and_half_relatives():
    """Profile family section qualifies only non-ordinary relatives."""

    class App(PersonDialogMixin, ResultsMixin):
        def _display_name(self, indi):
            return indi['name']

        def _show_path_graph(self, *_args):
            pass

    app = App()
    app.individuals = {
        '@ME@': {
            'id': '@ME@', 'name': 'Me Person', 'sex': 'M',
            'famc': ['@F1@'], 'fams': [], 'tags': [], '_raw': [],
        },
        '@DAD@': {
            'id': '@DAD@', 'name': 'Dad Person', 'sex': 'M',
            'famc': [], 'fams': ['@F1@', '@F2@'], 'tags': [], '_raw': [],
        },
        '@STEP@': {
            'id': '@STEP@', 'name': 'Step Parent', 'sex': 'F',
            'famc': [], 'fams': ['@F1@'], 'tags': [], '_raw': [],
        },
        '@HALF@': {
            'id': '@HALF@', 'name': 'Half Sibling', 'sex': 'F',
            'famc': ['@F2@'], 'fams': [], 'tags': [], '_raw': [],
        },
    }
    app.families = {
        '@F1@': {
            'id': '@F1@', 'husb': '@DAD@', 'wife': '@STEP@',
            'chil': ['@ME@'],
            'child_links': {'@ME@': {'father': 'birth', 'mother': 'step'}},
        },
        '@F2@': {
            'id': '@F2@', 'husb': '@DAD@', 'wife': None,
            'chil': ['@HALF@'], 'child_links': {},
        },
    }
    app.show_ids = Var(False)
    app.show_full_gedcom = Var(False)
    app._link_color = '#0000ee'
    app._mono_family = 'Courier'
    app._mono_size = 12
    app._model = Model()
    text = FakeText()

    app._insert_person_profile(text, '@ME@', lambda _indi_id: None)

    rendered = ''.join(text.parts)
    assert 'Father: Dad Person' in rendered
    assert 'Step-mother: Step Parent' in rendered
    assert 'Half-sister: Half Sibling' in rendered
    assert 'Biological' not in rendered
