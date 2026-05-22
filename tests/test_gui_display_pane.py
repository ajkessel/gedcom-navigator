"""Tests for Display Pane mode routing."""

from gedcom_gui_search import SearchMixin


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Tree:
    def __init__(self, selection):
        self._selection = selection

    def selection(self):
        return self._selection


class Button:
    def configure(self, **_kwargs):
        pass


class App(SearchMixin):
    def __init__(self, mode='profile', selection=('@A@',)):
        self._busy = False
        self.individuals = {'@A@': {}, '@B@': {}, '@C@': {}}
        self.display_mode = Var(mode)
        self.tree = Tree(selection)
        self._reverse_btn = Button()
        self._active_id = None
        self._display_path_target_id = None
        self._display_mode_labels = {
            'profile': 'Profile',
            'matches': 'Matches',
            'paths': 'Paths',
        }
        self.calls = []

    def _render_profile_result(self, start_id):
        self.calls.append(('profile', start_id))

    def _find_matches(self):
        self.calls.append(('matches', self._selected_or_active_id()))

    def _pick_person(self, _title):
        self.calls.append(('pick', None))
        return '@B@'

    def _run_path_search(self, start_id, target_id):
        self.calls.append(('paths', start_id, target_id))


def test_profile_mode_renders_selected_person():
    app = App(mode='profile')

    app._refresh_display_pane()

    assert app.calls == [('profile', '@A@')]


def test_matches_mode_routes_to_match_search():
    app = App(mode='matches')

    app._refresh_display_pane()

    assert app.calls == [('matches', '@A@')]


def test_paths_mode_prompts_once_then_reuses_target():
    app = App(mode='paths')

    app._refresh_display_pane()
    app.tree = Tree(('@C@',))
    app._refresh_display_pane()

    assert app.calls == [
        ('pick', None),
        ('paths', '@A@', '@B@'),
        ('paths', '@C@', '@B@'),
    ]
