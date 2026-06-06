"""Tests for Display Pane mode routing."""

import threading

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
    def __init__(self):
        self.visible = True
        self.config = {}

    def configure(self, **kwargs):
        self.config.update(kwargs)

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False


class Model:
    def __init__(self, paths=None):
        self.paths = paths or []
        self.calls = []

    def find_all_paths(self, start_id, end_id, top_n, max_depth, cancel_event=None):
        self.calls.append((start_id, end_id, top_n, max_depth, cancel_event))
        return self.paths, False


class Frame:
    def pack(self, **kwargs):
        pass

    def pack_forget(self):
        pass


class App(SearchMixin):
    def __init__(self, mode='profile', sub_mode='bio', selection=('@A@',),
                 pick_results=None):
        self._busy = False
        self.individuals = {'@A@': {}, '@B@': {}, '@C@': {}}
        self.display_mode = Var(mode)
        self.profile_sub_mode = Var(sub_mode)
        self.tree = Tree(selection)
        self._reverse_btn = Button()
        self._matches_settings_frame = Button()
        self._profile_sub_mode_frame = Frame()
        self._active_id = None
        self._display_path_target_id = None
        self._home_person_id = None
        self._model = Model()
        self._display_mode_labels = {
            'profile': 'Profile',
            'matches': 'Matches',
            'paths': 'Paths',
        }
        self._profile_sub_mode_labels = {
            'bio': 'Bio',
            'pedigree': 'Pedigree',
            'descendants': 'Descendants',
        }
        self.calls = []
        self.pick_results = (
            list(pick_results) if pick_results is not None else ['@B@'])

    def _render_profile_result(self, start_id, home_paths=None):
        self.calls.append(('profile', start_id, home_paths))

    def _render_pedigree_text_result(self, start_id):
        self.calls.append(('pedigree', start_id))

    def _render_descendants_text_result(self, start_id):
        self.calls.append(('descendants', start_id))

    def _find_matches(self):
        self.calls.append(('matches', self._selected_or_active_id()))

    def _pick_person(self, _title):
        self.calls.append(('pick', None))
        return self.pick_results.pop(0) if self.pick_results else '@B@'

    def _run_path_search(self, start_id, target_id):
        self.calls.append(('paths', start_id, target_id))

    def _sync_profile_sub_mode_selector(self):
        pass


def test_profile_mode_renders_selected_person():
    app = App(mode='profile')

    app._refresh_display_pane()

    assert app.calls == [('profile', '@A@', None)]
    assert app._reverse_btn.visible is False
    assert app._reverse_btn.config['state'] == 'disabled'
    assert app._matches_settings_frame.visible is False


def test_matches_mode_routes_to_match_search():
    app = App(mode='matches')

    app._refresh_display_pane()

    assert app.calls == [('matches', '@A@')]
    assert app._reverse_btn.visible is False
    assert app._matches_settings_frame.visible is True


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
    assert app._reverse_btn.visible is True
    assert app._matches_settings_frame.visible is False


def test_paths_mode_cancel_does_not_immediately_prompt_again():
    app = App(mode='paths', pick_results=[None, '@B@'])

    app._refresh_display_pane()
    app._refresh_display_pane()

    assert app.calls == [('pick', None)]
    assert app._reverse_btn.visible is True
    assert app._matches_settings_frame.visible is False


def test_set_display_mode_toggles_footer_control_visibility():
    app = App(mode='profile')

    app._set_display_mode('paths', refresh=False)
    assert app._reverse_btn.visible is True
    assert app._matches_settings_frame.visible is False

    app._set_display_mode('matches', refresh=False)
    assert app._reverse_btn.visible is False
    assert app._matches_settings_frame.visible is True

    app._set_display_mode('profile', refresh=False)
    assert app._reverse_btn.visible is False
    assert app._matches_settings_frame.visible is False


def test_profile_pedigree_sub_mode_dispatches_pedigree_renderer():
    app = App(mode='profile', sub_mode='pedigree')

    app._refresh_display_pane()

    assert app.calls == [('pedigree', '@A@')]
    assert app._reverse_btn.config.get('state') == 'disabled'


def test_profile_descendants_sub_mode_dispatches_descendants_renderer():
    app = App(mode='profile', sub_mode='descendants')

    app._refresh_display_pane()

    assert app.calls == [('descendants', '@A@')]


def test_home_path_data_returns_none_without_home():
    app = App()

    assert app._find_home_path_data('@A@', 10) is None


def test_home_path_data_returns_same_person_path_for_home_selection():
    app = App()
    app._home_person_id = '@A@'

    assert app._find_home_path_data('@A@', 10) == {
        'home_id': '@A@',
        'paths': [[('@A@', None)]],
    }


def test_home_path_data_finds_path_to_home_person():
    path = [[('@A@', None), ('@B@', 'father')]]
    app = App()
    app._home_person_id = '@B@'
    app._model = Model(paths=path)

    assert app._find_home_path_data('@A@', 12) == {
        'home_id': '@B@',
        'paths': path,
    }
    assert app._model.calls == [('@A@', '@B@', 1, 12, None)]


def test_home_path_data_uses_cache_for_revisited_person():
    path = [[('@A@', None), ('@B@', 'father')]]
    app = App()
    app._home_person_id = '@B@'
    app._model = Model(paths=path)

    first = app._find_home_path_data('@A@', 12)
    second = app._find_home_path_data('@A@', 12)

    assert first == second == {'home_id': '@B@', 'paths': path}
    assert app._model.calls == [('@A@', '@B@', 1, 12, None)]


def test_profile_home_path_render_starts_background_lookup():
    app = App()
    app._home_person_id = '@B@'
    started = []
    app._start_profile_home_path_lookup = (
        lambda start_id, max_depth, key:
        started.append((start_id, max_depth, key)))

    result = app._profile_home_path_for_render('@A@', 12)

    assert result == {'home_id': '@B@', 'loading': True}
    assert started == [('@A@', 12, ('@A@', '@B@', 12))]
    assert app._model.calls == []


def test_stale_profile_home_path_result_is_ignored():
    app = App()
    app._home_person_id = '@B@'
    app._last_result = {'type': 'profile', 'start_id': '@A@'}
    app._profile_home_path_request_id = 2
    key = ('@A@', '@B@', 12)
    app._profile_home_path_pending_key = key
    app._profile_home_path_pending_request_id = 2

    app._finish_profile_home_path_lookup(
        1,
        key,
        '@A@',
        {'home_id': '@B@', 'paths': []},
        None,
        threading.Event(),
    )

    assert app.calls == []
    assert app._profile_home_path_pending_key == key
    assert app._profile_home_path_pending_request_id == 2
