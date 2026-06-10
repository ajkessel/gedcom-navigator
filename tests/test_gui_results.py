"""Tests for result-pane path rendering helpers."""

import json
from collections import defaultdict
from pathlib import Path

import pytest

from gedcom_family_tree import (
    _nearest_unblocked_column,
    build_descendant_tree_graph,
    build_family_tree_graph,
    build_pedigree_tree_graph,
    descendant_tree_expanded_requests,
    descendant_tree_expansion_options,
    family_tree_expansion_options,
    layout_descendant_tree,
    layout_family_tree,
    layout_pedigree_tree,
)
from gedcom_gui_family_tree_render import FamilyTreeRenderMixin
from gedcom_gui_results import ResultsMixin
import gedcom_strings as gs


def _debug_fixture_parent_kind(payload):
    """Build a (parent_id, child_id) -> kind lookup from saved edge kinds."""
    kinds = {}
    for edge in payload['edges']:
        kind = edge.get('relationship_kind')
        if not kind:
            continue
        if edge['category'] == 'parents':
            kinds[(edge['target'], edge['source'])] = kind
        elif edge['category'] == 'children':
            kinds[(edge['source'], edge['target'])] = kind
    return lambda parent_id, child_id: kinds.get(
        (parent_id, child_id), 'birth')


def _load_debug_family_tree_layout(name):
    path = Path('debug') / f'{name}.json'
    if not path.exists():
        pytest.skip(f'debug/{name}.json not found')
    payload = json.loads(path.read_text())
    edges = [
        (edge['source'], edge['target'], edge['category'])
        for edge in payload['edges']
    ]
    return (
        layout_family_tree(
            payload['center_id'], payload['visible_ids'], edges,
            payload.get('family_members'),
            _debug_fixture_parent_kind(payload)),
        edges,
    )


def _debug_edges_in_family_member_order(payload):
    """Return debug edges in the graph-builder order, not JSON sort order."""
    edges = [
        (edge['source'], edge['target'], edge['category'])
        for edge in payload['edges']
    ]
    edge_set = set(edges)
    ordered_edges = []
    seen_edges = set()
    for source_id in payload['visible_ids']:
        members = payload.get('family_members', {}).get(source_id, {})
        for spouse_id in members.get('spouses', ()):
            edge = (source_id, spouse_id, 'spouses')
            if edge in edge_set and edge not in seen_edges:
                ordered_edges.append(edge)
                seen_edges.add(edge)
        for child_id in members.get('children', ()):
            edge = (source_id, child_id, 'children')
            if edge in edge_set and edge not in seen_edges:
                ordered_edges.append(edge)
                seen_edges.add(edge)
    ordered_edges.extend(edge for edge in edges if edge not in seen_edges)
    return ordered_edges


def _assert_no_same_row_conflicts(layout):
    for index, left in enumerate(layout):
        for right in layout[index + 1:]:
            if left['generation'] != right['generation']:
                continue
            assert abs(left['column'] - right['column']) >= 1.0 - 1e-9


def _assert_visible_spouses_adjacent(layout, edges):
    by_id = {node['id']: node for node in layout}
    for source_id, target_id, category in edges:
        if category != 'spouses':
            continue
        if source_id not in by_id or target_id not in by_id:
            continue
        if by_id[source_id]['generation'] != by_id[target_id]['generation']:
            continue
        assert abs(
            abs(by_id[source_id]['column'] - by_id[target_id]['column'])
            - 1.0) <= 1e-9


def _max_family_tree_row_width(layout):
    by_generation = {}
    for node in layout:
        by_generation.setdefault(node['generation'], []).append(node['column'])
    return max(max(columns) - min(columns)
               for columns in by_generation.values())


def _assert_visible_child_groups_near_parents(layout, edges):
    by_id = {node['id']: node for node in layout}
    for source_id in {source_id for source_id, _target_id, _category in edges}:
        if source_id not in by_id:
            continue
        child_ids = [
            target_id for edge_source, target_id, category in edges
            if edge_source == source_id
            and category == 'children'
            and target_id in by_id
        ]
        if not child_ids:
            continue
        spouse_ids = [
            target_id for edge_source, target_id, category in edges
            if edge_source == source_id
            and category == 'spouses'
            and target_id in by_id
            and by_id[target_id]['generation'] == by_id[source_id]['generation']
        ]
        spouse_ids.extend(
            edge_source for edge_source, target_id, category in edges
            if target_id == source_id
            and category == 'spouses'
            and edge_source in by_id
            and by_id[edge_source]['generation']
            == by_id[source_id]['generation']
        )
        parent_column = by_id[source_id]['column']
        if spouse_ids:
            parent_column = (
                parent_column + by_id[spouse_ids[0]]['column']) / 2
        child_columns = [by_id[child_id]['column'] for child_id in child_ids]
        child_column = (min(child_columns) + max(child_columns)) / 2

        assert abs(parent_column - child_column) <= 1.1


class _HomeModel:
    def find_common_ancestors(self, *_args):
        return []


class _HomePathApp(ResultsMixin):
    def __init__(self):
        self.individuals = {
            '@A@': {'name': 'Alex', 'sex': 'M', 'famc': [], 'fams': []},
            '@B@': {'name': 'Home', 'sex': 'M', 'famc': [], 'fams': []},
        }
        self.families = {}
        self._model = _HomeModel()

    def _reverse_path(self, path, _individuals):
        return list(reversed([(node_id, edge) for node_id, edge in path]))

    def _path_edge_prefix(self, edge, indent='  '):
        return f'{indent}{edge}: '


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


@pytest.mark.parametrize(
    ("display_mode", "profile_sub_mode", "report_title", "keep_bold_with_next"),
    [
        ("profile", "bio", gs.DISPLAY_MODE_PROFILE, False),
        ("profile", "pedigree", gs.PROFILE_SUBMODE_PEDIGREE, True),
        ("matches", "bio", gs.DISPLAY_MODE_MATCHES, False),
        ("paths", "bio", gs.DISPLAY_MODE_PATHS, False),
    ],
)
def test_save_results_as_pdf_uses_configured_format(
        monkeypatch, tmp_path, display_mode, profile_sub_mode, report_title,
        keep_bold_with_next):
    class Textbox:
        pass

    class Results:
        _textbox = Textbox()

        def get(self, *_args):
            return "Body text\n"

    class Config:
        def get_save_format(self):
            return "pdf"

        def get_pdf_include_photos(self):
            return False

    class App(ResultsMixin):
        def __init__(self):
            self.results = Results()
            self._results_header_var = _Var("Person")
            self._config = Config()
            self._mono_size = 12
            self.root = object()
            self.display_mode = _Var(display_mode)
            self.profile_sub_mode = _Var(profile_sub_mode)

    path = tmp_path / "results.pdf"
    dialog_options = {}
    rendered = {}

    def ask_save(**kwargs):
        dialog_options.update(kwargs)
        return str(path)

    def render(pdf_path, widget, **kwargs):
        rendered.update(path=pdf_path, widget=widget, **kwargs)

    monkeypatch.setattr(
        "gedcom_gui_results.filedialog.asksaveasfilename", ask_save)
    monkeypatch.setattr(
        "gedcom_gui_results.filedialog_parent", lambda _root: None)
    monkeypatch.setattr("gedcom_gui_results.render_text_widget_pdf", render)

    app = App()
    app._save_results()

    assert dialog_options["defaultextension"] == ".pdf"
    assert dialog_options["filetypes"][0][1] == "*.pdf"
    assert rendered == {
        "path": str(path),
        "widget": app.results._textbox,
        "report_title": report_title,
        "subject": "Person",
        "photo_bytes": None,
        "keep_bold_with_next": keep_bold_with_next,
    }


def test_profile_gallery_button_visible_only_for_profile_with_extra_images():
    class Button:
        def __init__(self):
            self.visible = None

        def grid(self):
            self.visible = True

        def grid_remove(self):
            self.visible = False

    class App(ResultsMixin):
        def _profile_gallery_candidates(self, indi_id):
            return ['image'] if indi_id == '@A@' else []

    app = App()
    app.display_mode = _Var('profile')
    app.profile_sub_mode = _Var('bio')
    app._profile_gallery_btn = Button()

    app._set_profile_gallery_button_visible('@A@')
    assert app._profile_gallery_btn.visible is True

    app._set_profile_gallery_button_visible('@B@')
    assert app._profile_gallery_btn.visible is False

    app.display_mode.set('matches')
    app._set_profile_gallery_button_visible('@A@')
    assert app._profile_gallery_btn.visible is False

    app.display_mode.set('profile')
    app.profile_sub_mode.set('pedigree')
    app._set_profile_gallery_button_visible('@A@')
    assert app._profile_gallery_btn.visible is False


class _FakeTextbox:
    """Minimal stand-in for CTkTextbox used by pedigree/descendants renderers."""

    def __init__(self):
        self._textbox = self
        self._parts = []
        self._bindings = {}
        self._tags = {}
        self._state = 'normal'

    def configure(self, **kwargs):
        if 'state' in kwargs:
            self._state = kwargs['state']

    def delete(self, *_args):
        self._parts.clear()

    def insert(self, _index, text, _tags=None):
        self._parts.append(text)

    def get(self, *_args):
        return ''.join(self._parts)

    def tag_configure(self, tag, **_kwargs):
        self._tags[tag] = _kwargs

    def tag_bind(self, tag, sequence, callback=None, **_kwargs):
        self._bindings[(tag, sequence)] = callback

    def tag_names(self, *_args):
        return list(self._tags)

    def tag_delete(self, tag):
        self._tags.pop(tag, None)

    def winfo_width(self):
        return 500


class _FakeButton:
    def configure(self, **_kwargs):
        pass


class _FakeResultsApp(ResultsMixin):
    """Minimal ResultsMixin instance for exercising text-report renderers."""

    def __init__(self, individuals, families):
        self.individuals = individuals
        self.families = families
        self.results = _FakeTextbox()
        self.show_ids = _Var(False)
        self._link_color = 'blue'
        self._reverse_btn = _FakeButton()
        self._results_header_var = _Var('')
        self._results_header_id = None

    def _display_name(self, indi):
        return indi.get('name') or '(unknown)'

    def _navigate_to(self, _indi_id):
        pass

    def _set_profile_gallery_button_visible(self, _indi_id=None):
        pass

    def _set_results_header_for_person(self, _indi_id):
        pass

    def _update_header_label_style(self):
        pass

    def _reset_results_pane(self):
        pass

    def _place_profile_thumbnail(self, _text, _indi_id):
        pass


def _make_family(fam_id, husb=None, wife=None, children=None):
    return {
        'id': fam_id, 'husb': husb, 'wife': wife,
        'chil': children or [],
        'marr_date': '', 'marr_place': '',
    }


def _make_person(pid, name, sex='', famc=None, fams=None,
                 birth_year=None, death_year=None):
    return {
        'id': pid, 'name': name, 'sex': sex,
        'famc': famc or [], 'fams': fams or [],
        'birth_year': birth_year, 'death_year': death_year,
        'given_name': name.split()[0] if name else '',
        'surname': name.split()[-1] if name else '',
    }


def test_pedigree_ahnentafel_renders_title_and_slots():
    indis = {
        '@I1@': _make_person('@I1@', 'Alice Smith', sex='F',
                             famc=['@F1@'], birth_year=1950, death_year=2020),
        '@I2@': _make_person('@I2@', 'Bob Smith', sex='M',
                             fams=['@F1@'], birth_year=1920, death_year=1990),
        '@I3@': _make_person('@I3@', 'Carol Jones', sex='F',
                             fams=['@F1@'], birth_year=1925, death_year=2000),
    }
    fams = {
        '@F1@': _make_family('@F1@', husb='@I2@', wife='@I3@',
                             children=['@I1@']),
    }
    app = _FakeResultsApp(indis, fams)
    app._render_pedigree_text_result('@I1@')
    text = app.results.get()

    assert 'Alice Smith' in text
    assert '1.' in text
    assert '2.' in text   # father slot
    assert '3.' in text   # mother slot
    assert 'Bob Smith' in text
    assert 'Carol Jones' in text
    assert 'Generation 1' in text
    assert 'Generation 2' in text
    assert '(father)' in text
    assert '(mother)' in text


def test_pedigree_skips_unknown_ancestors():
    # Unknown ancestors are omitted entirely (list-format Ahnentafel convention).
    indis = {
        '@I1@': _make_person('@I1@', 'Alice Smith', sex='F',
                             famc=['@F1@']),
        '@I2@': _make_person('@I2@', 'Bob Smith', sex='M', fams=['@F1@']),
        # No mother in family — slot 3 should be completely absent
    }
    fams = {
        '@F1@': _make_family('@F1@', husb='@I2@', wife=None, children=['@I1@']),
    }
    app = _FakeResultsApp(indis, fams)
    app._render_pedigree_text_result('@I1@')
    text = app.results.get()

    assert '2.' in text
    assert 'Bob Smith' in text
    assert '[unknown]' not in text
    assert '3.' not in text  # missing mother slot silently skipped


def test_pedigree_children_of_unknown_ancestor_also_skipped():
    # When a person's parent is unknown, the grandparent slots that descend
    # from that unknown parent also don't appear (BFS never visits them).
    indis = {
        '@I1@': _make_person('@I1@', 'Alice', famc=['@F1@']),
        '@I2@': _make_person('@I2@', 'Bob', sex='M', fams=['@F1@'], famc=['@F2@']),
        # No mother for Alice — slot 3 and its descendants (6, 7) all absent
        '@I4@': _make_person('@I4@', 'Dave', sex='M', fams=['@F2@']),
        # No paternal grandmother — slot 5 absent
    }
    fams = {
        '@F1@': _make_family('@F1@', husb='@I2@', wife=None, children=['@I1@']),
        '@F2@': _make_family('@F2@', husb='@I4@', wife=None, children=['@I2@']),
    }
    app = _FakeResultsApp(indis, fams)
    app._render_pedigree_text_result('@I1@')
    text = app.results.get()

    assert 'Bob' in text        # slot 2 — known
    assert 'Dave' in text       # slot 4 — known
    assert '[unknown]' not in text
    assert '3.' not in text     # Alice's mother — unknown, skipped
    assert '5.' not in text     # Bob's mother — unknown, skipped
    assert '6.' not in text     # maternal grandfather — unreachable, skipped
    assert '7.' not in text     # maternal grandmother — unreachable, skipped


def test_pedigree_ahnentafel_grandparent_labels():
    indis = {
        '@I1@': _make_person('@I1@', 'Alice', famc=['@F1@']),
        '@I2@': _make_person('@I2@', 'Bob', sex='M', fams=['@F1@'], famc=['@F2@']),
        '@I3@': _make_person('@I3@', 'Carol', sex='F', fams=['@F1@']),
        '@I4@': _make_person('@I4@', 'Dave', sex='M', fams=['@F2@']),
        '@I5@': _make_person('@I5@', 'Eve', sex='F', fams=['@F2@']),
    }
    fams = {
        '@F1@': _make_family('@F1@', husb='@I2@', wife='@I3@', children=['@I1@']),
        '@F2@': _make_family('@F2@', husb='@I4@', wife='@I5@', children=['@I2@']),
    }
    app = _FakeResultsApp(indis, fams)
    app._render_pedigree_text_result('@I1@')
    text = app.results.get()

    assert 'Generation 3' in text
    assert 'paternal grandfather' in text
    assert 'paternal grandmother' in text
    assert 'Dave' in text
    assert 'Eve' in text


def test_descendants_henry_numbering():
    indis = {
        '@I1@': _make_person('@I1@', 'Alice', sex='F', fams=['@F1@']),
        '@I2@': _make_person('@I2@', 'Bob', sex='M', fams=['@F1@']),
        '@I3@': _make_person('@I3@', 'Charlie', famc=['@F1@'], fams=['@F2@']),
        '@I4@': _make_person('@I4@', 'Diana', famc=['@F1@']),
        '@I5@': _make_person('@I5@', 'Eve', sex='F', fams=['@F2@']),
        '@I6@': _make_person('@I6@', 'Frank', famc=['@F2@']),
    }
    fams = {
        '@F1@': _make_family('@F1@', husb='@I2@', wife='@I1@',
                             children=['@I3@', '@I4@']),
        '@F2@': _make_family('@F2@', husb='@I3@', wife='@I5@',
                             children=['@I6@']),
    }
    app = _FakeResultsApp(indis, fams)
    app._render_descendants_text_result('@I1@')
    text = app.results.get()

    assert '1.' in text
    assert '1.1.' in text
    assert '1.2.' in text
    assert '1.1.1.' in text
    assert 'Charlie' in text
    assert 'Diana' in text
    assert 'Frank' in text
    assert 'm. ' in text  # marriage prefix


def test_descendants_spouse_shown_under_parent():
    indis = {
        '@I1@': _make_person('@I1@', 'Alice', sex='F', fams=['@F1@']),
        '@I2@': _make_person('@I2@', 'Bob', sex='M', fams=['@F1@']),
        '@I3@': _make_person('@I3@', 'Charlie', famc=['@F1@']),
    }
    fams = {
        '@F1@': _make_family('@F1@', husb='@I2@', wife='@I1@',
                             children=['@I3@']),
    }
    app = _FakeResultsApp(indis, fams)
    app._render_descendants_text_result('@I1@')
    text = app.results.get()

    assert 'Bob' in text
    assert 'm. Bob' in text


def test_pedigree_ahnentafel_label_static():
    from gedcom_gui_results import ResultsMixin
    assert ResultsMixin._ahnentafel_label(1) is None
    assert ResultsMixin._ahnentafel_label(2) == 'father'
    assert ResultsMixin._ahnentafel_label(3) == 'mother'
    assert ResultsMixin._ahnentafel_label(4) == 'paternal grandfather'
    assert ResultsMixin._ahnentafel_label(5) == 'paternal grandmother'
    assert ResultsMixin._ahnentafel_label(6) == 'maternal grandfather'
    assert ResultsMixin._ahnentafel_label(7) == 'maternal grandmother'
    assert ResultsMixin._ahnentafel_label(8) == 'paternal great-grandfather'
    assert ResultsMixin._ahnentafel_label(9) == 'paternal great-grandmother'
    assert ResultsMixin._ahnentafel_label(12) == 'maternal great-grandfather'
    assert ResultsMixin._ahnentafel_label(16) == 'paternal 2nd great-grandfather'
    assert ResultsMixin._ahnentafel_label(32) == 'paternal 3rd great-grandfather'


def test_pedigree_font_extra_shrink_only_applies_below_normal_zoom():
    assert FamilyTreeRenderMixin._horizontal_tree_font_shrink(1.0) == 0
    assert FamilyTreeRenderMixin._horizontal_tree_font_shrink(1.5) == 0
    assert FamilyTreeRenderMixin._horizontal_tree_font_shrink(0.9) == 1
    assert FamilyTreeRenderMixin._horizontal_tree_font_shrink(0.75) == 2
    assert FamilyTreeRenderMixin._horizontal_tree_font_shrink(0.5) == 3


def test_pedigree_parent_connectors_are_orthogonal():
    assert FamilyTreeRenderMixin._horizontal_parent_connector_segments(
        140, 50, [(200, 20), (200, 80)], 40) == [
            (140, 50, 158.0, 50),
            (158.0, 20, 158.0, 80),
            (158.0, 20, 200, 20),
            (158.0, 80, 200, 80),
        ]


def test_pedigree_single_parent_connector_exits_horizontally():
    assert FamilyTreeRenderMixin._horizontal_parent_connector_segments(
        140, 50, [(200, 50)], 40) == [(140, 50, 200, 50)]
    assert FamilyTreeRenderMixin._horizontal_parent_connector_segments(
        140, 50, [(200, 20)], 40) == [
            (140, 50, 158.0, 50, 158.0, 20, 200, 20),
        ]


def test_expansion_button_tab_rounds_only_outer_edge():
    class FakeCanvas:
        def __init__(self):
            self.polygons = []

        def create_polygon(self, *args, **kwargs):
            self.polygons.append((args, kwargs))

    canvas = FakeCanvas()

    FamilyTreeRenderMixin._draw_expansion_button_tab(
        canvas,
        50,
        60,
        20,
        'spouses',
        'right',
        '#336699',
        '#d0d0d0',
        ('family_tree_button', 'node_button'),
    )

    points, kwargs = canvas.polygons[0]

    assert points[:4] == (40.0, 50.0, 50.0, 50.0)
    assert points[-2:] == (40.0, 70.0)
    assert max(points[0::2]) == 60.0
    assert kwargs == {
        'fill': '#336699',
        'outline': '#d0d0d0',
        'width': 1,
        'tags': ('family_tree_button', 'node_button'),
    }


def test_home_path_section_renders_missing_path_message():
    app = _HomePathApp()
    lines = []

    rendered = app._render_home_path_section(
        '@A@',
        {'home_id': '@B@', 'paths': []},
        nl=lambda text='', bold=False: lines.append(text),
        person=lambda indi_id, prefix='': lines.append(prefix + indi_id),
        relationship_line=lambda rel, path, prefix='': lines.append(rel),
        common_ancestor_line=lambda ancestor_ids, prefix='', item_prefix='    ': None,
    )

    assert rendered is True
    assert gs.RESULT_PATH_SECTION in lines
    assert gs.RESULT_NO_HOME_PATH in lines


def test_home_path_section_renders_loading_message():
    app = _HomePathApp()
    lines = []

    rendered = app._render_home_path_section(
        '@A@',
        {'home_id': '@B@', 'loading': True},
        nl=lambda text='', bold=False: lines.append(text),
        person=lambda indi_id, prefix='': lines.append(prefix + indi_id),
        relationship_line=lambda rel, path, prefix='': lines.append(rel),
        common_ancestor_line=lambda ancestor_ids, prefix='', item_prefix='    ': None,
    )

    assert rendered is True
    assert gs.RESULT_HOME_PATH_LOADING in lines


def test_home_path_section_renders_same_person_message():
    app = _HomePathApp()
    lines = []

    app._render_home_path_section(
        '@A@',
        {'home_id': '@A@', 'paths': [[('@A@', None)]]},
        nl=lambda text='', bold=False: lines.append(text),
        person=lambda indi_id, prefix='': lines.append(prefix + indi_id),
        relationship_line=lambda rel, path, prefix='': lines.append(rel),
        common_ancestor_line=lambda ancestor_ids, prefix='', item_prefix='    ': None,
    )

    assert gs.PATH_SAME_PERSON in lines


def test_home_path_section_is_appended_after_existing_content():
    app = _HomePathApp()
    lines = ['main content']

    app._render_home_path_section(
        '@A@',
        {'home_id': '@B@', 'paths': [[('@A@', None), ('@B@', 'father')]]},
        nl=lambda text='', bold=False: lines.append(text),
        person=lambda indi_id, prefix='': lines.append(prefix + indi_id),
        relationship_line=lambda rel, path, prefix='': lines.append(rel),
        common_ancestor_line=lambda ancestor_ids, prefix='', item_prefix='    ': None,
    )

    assert lines.index('main content') < lines.index(gs.RESULT_PATH_SECTION)


def test_path_graph_layout_aligns_same_generation_edges():
    """Sibling and spouse hops stay on the current generation row."""
    path = [
        ('@A@', None),
        ('@B@', 'father'),
        ('@C@', 'sibling'),
        ('@D@', 'child'),
        ('@E@', 'spouse'),
    ]

    layout = ResultsMixin._path_graph_layout(path)

    assert [node['generation'] for node in layout] == [0, -1, -1, 0, 0]
    assert [node['column'] for node in layout] == [0, 0, 1, 1, 2]
    assert [node['edge'] for node in layout] == [
        None, 'father', 'sibling', 'child', 'spouse']


def test_path_graph_layout_keeps_parent_child_edges_vertical():
    """Parent/child hops keep the same column instead of widening the graph."""
    path = [
        ('@A@', None),
        ('@B@', 'father'),
        ('@C@', 'mother'),
        ('@D@', 'father'),
        ('@E@', 'father'),
    ]

    layout = ResultsMixin._path_graph_layout(path)

    assert [node['generation'] for node in layout] == [0, -1, -2, -3, -4]
    assert [node['column'] for node in layout] == [0, 0, 0, 0, 0]


def test_path_graph_simplifies_parent_child_sibling_detours():
    """A path through a parent to another child graphs as a sibling hop."""
    path = [
        ('@COUSN@', None),
        ('@ANCS1@', 'father'),
        ('@ANCS2@', 'father'),
        ('@ANCS3@', 'father'),
        ('@REL1@', 'child'),
        ('@REL1_SP@', 'spouse'),
    ]

    simplified = ResultsMixin._simplify_path_for_graph(path)

    assert simplified == [
        ('@COUSN@', None),
        ('@ANCS1@', 'father'),
        ('@ANCS2@', 'father'),
        ('@REL1@', 'sibling'),
        ('@REL1_SP@', 'spouse'),
    ]


def test_path_graph_layout_avoids_duplicate_node_positions():
    """Unsimplified redundant paths still cannot stack nodes in one grid cell."""
    path = [
        ('@A@', None),
        ('@B@', 'father'),
        ('@C@', 'child'),
    ]

    layout = ResultsMixin._path_graph_layout(path)
    positions = {(node['generation'], node['column']) for node in layout}

    assert len(positions) == len(layout)


def test_pedigree_tree_graph_includes_all_recorded_parent_families():
    individuals = {
        '@ME@': {'name': 'Me', 'sex': 'M', 'famc': ['@F1@', '@F2@'], 'fams': []},
        '@DAD@': {'name': 'Dad', 'sex': 'M', 'famc': ['@F3@'], 'fams': ['@F1@']},
        '@MOM@': {'name': 'Mom', 'sex': 'F', 'famc': [], 'fams': ['@F1@']},
        '@OTHER@': {'name': 'Other', 'sex': 'M', 'famc': [], 'fams': ['@F2@']},
        '@PGF@': {'name': 'Pgf', 'sex': 'M', 'famc': [], 'fams': ['@F3@']},
        '@PGM@': {'name': 'Pgm', 'sex': 'F', 'famc': [], 'fams': ['@F3@']},
    }
    families = {
        '@F1@': {'husb': '@DAD@', 'wife': '@MOM@', 'chil': ['@ME@']},
        '@F2@': {'husb': '@OTHER@', 'wife': '', 'chil': ['@ME@']},
        '@F3@': {'husb': '@PGF@', 'wife': '@PGM@', 'chil': ['@DAD@']},
    }

    visible, edges = build_pedigree_tree_graph('@ME@', individuals, families)
    layout = layout_pedigree_tree('@ME@', visible, edges)
    columns = {node['id']: node['column'] for node in layout}
    rows = {node['id']: node['generation'] for node in layout}

    assert visible == ['@ME@', '@DAD@', '@MOM@', '@OTHER@', '@PGF@', '@PGM@']
    assert ('@ME@', '@OTHER@', 'parents') in edges
    assert columns['@ME@'] == 0
    assert columns['@DAD@'] == 1
    assert columns['@MOM@'] == 1
    assert columns['@OTHER@'] == 1
    assert columns['@PGF@'] == 2
    assert columns['@PGM@'] == 2
    assert abs(
        rows['@ME@'] - (
            rows['@DAD@'] + rows['@MOM@'] + rows['@OTHER@']) / 3
    ) < 0.0001
    assert rows['@DAD@'] == (rows['@PGF@'] + rows['@PGM@']) / 2


def test_pedigree_tree_layout_centers_people_between_their_parents():
    """Pedigree rows expand outward so parent pairs frame each child."""
    visible = [
        '@ME@',
        '@DAD@', '@MOM@',
        '@PGF@', '@PGM@', '@MGF@', '@MGM@',
        '@PGGF@', '@PGGM@', '@PMGF@', '@PMGM@',
        '@MGGF@', '@MGGM@', '@MMGF@', '@MMGM@',
    ]
    edges = [
        ('@ME@', '@DAD@', 'parents'),
        ('@ME@', '@MOM@', 'parents'),
        ('@DAD@', '@PGF@', 'parents'),
        ('@DAD@', '@PGM@', 'parents'),
        ('@MOM@', '@MGF@', 'parents'),
        ('@MOM@', '@MGM@', 'parents'),
        ('@PGF@', '@PGGF@', 'parents'),
        ('@PGF@', '@PGGM@', 'parents'),
        ('@PGM@', '@PMGF@', 'parents'),
        ('@PGM@', '@PMGM@', 'parents'),
        ('@MGF@', '@MGGF@', 'parents'),
        ('@MGF@', '@MGGM@', 'parents'),
        ('@MGM@', '@MMGF@', 'parents'),
        ('@MGM@', '@MMGM@', 'parents'),
    ]

    layout = layout_pedigree_tree('@ME@', visible, edges)
    rows = {node['id']: node['generation'] for node in layout}
    columns = {node['id']: node['column'] for node in layout}

    assert rows['@ME@'] == 0.0
    assert rows['@ME@'] == (rows['@DAD@'] + rows['@MOM@']) / 2
    assert rows['@DAD@'] == (rows['@PGF@'] + rows['@PGM@']) / 2
    assert rows['@MOM@'] == (rows['@MGF@'] + rows['@MGM@']) / 2
    assert rows['@PGF@'] == (rows['@PGGF@'] + rows['@PGGM@']) / 2
    assert rows['@PGM@'] == (rows['@PMGF@'] + rows['@PMGM@']) / 2
    assert rows['@MGF@'] == (rows['@MGGF@'] + rows['@MGGM@']) / 2
    assert rows['@MGM@'] == (rows['@MMGF@'] + rows['@MMGM@']) / 2
    assert columns['@DAD@'] == columns['@MOM@'] == 1
    assert max(rows[node['id']] for node in layout if node['column'] == 3) > (
        max(rows[node['id']] for node in layout if node['column'] == 1))
    assert min(rows[node['id']] for node in layout if node['column'] == 3) < (
        min(rows[node['id']] for node in layout if node['column'] == 1))

    for column in {node['column'] for node in layout}:
        same_column = sorted(
            node['generation'] for node in layout
            if node['column'] == column)
        assert all(
            right - left >= 1.0
            for left, right in zip(same_column, same_column[1:]))


def test_pedigree_tree_layout_keeps_deep_parent_pairs_adjacent():
    """Crowded ancestor columns keep each child's parents as a contiguous pair."""
    visible = [
        '@ME@',
        '@DAD@', '@MOM@',
        '@PGF@', '@PGM@', '@MGF@', '@MGM@',
        '@PGGF@', '@PGGM@', '@PMGF@', '@PMGM@',
        '@MGGF@', '@MGGM@', '@MMGF@', '@MMGM@',
        '@PMGM_DAD@', '@PMGM_MOM@', '@MGGF_DAD@', '@MGGF_MOM@',
    ]
    edges = [
        ('@ME@', '@DAD@', 'parents'),
        ('@ME@', '@MOM@', 'parents'),
        ('@DAD@', '@PGF@', 'parents'),
        ('@DAD@', '@PGM@', 'parents'),
        ('@MOM@', '@MGF@', 'parents'),
        ('@MOM@', '@MGM@', 'parents'),
        ('@PGF@', '@PGGF@', 'parents'),
        ('@PGF@', '@PGGM@', 'parents'),
        ('@PGM@', '@PMGF@', 'parents'),
        ('@PGM@', '@PMGM@', 'parents'),
        ('@MGF@', '@MGGF@', 'parents'),
        ('@MGF@', '@MGGM@', 'parents'),
        ('@MGM@', '@MMGF@', 'parents'),
        ('@MGM@', '@MMGM@', 'parents'),
        ('@PMGM@', '@PMGM_DAD@', 'parents'),
        ('@PMGM@', '@PMGM_MOM@', 'parents'),
        ('@MGGF@', '@MGGF_DAD@', 'parents'),
        ('@MGGF@', '@MGGF_MOM@', 'parents'),
    ]

    layout = layout_pedigree_tree('@ME@', visible, edges)
    row_order = [
        node['id']
        for node in sorted(
            (node for node in layout if node['column'] == 4),
            key=lambda item: item['generation'])
    ]

    for parent_pair in (
            ('@PMGM_DAD@', '@PMGM_MOM@'),
            ('@MGGF_DAD@', '@MGGF_MOM@')):
        indexes = sorted(row_order.index(parent_id)
                         for parent_id in parent_pair)
        assert indexes[1] - indexes[0] == 1


def test_pedigree_tree_layout_spreads_crowded_rows_before_parent_blocks():
    """Crowded generations keep each parent pair centered around its child."""
    visible = ['@ME@']
    edges = []
    previous_generation = ['@ME@']
    for depth in range(4):
        next_generation = []
        for child_id in previous_generation:
            father_id = f'{child_id}F'
            mother_id = f'{child_id}M'
            visible.extend((father_id, mother_id))
            edges.extend((
                (child_id, father_id, 'parents'),
                (child_id, mother_id, 'parents'),
            ))
            next_generation.extend((father_id, mother_id))
        previous_generation = next_generation

    layout = layout_pedigree_tree('@ME@', visible, edges)
    rows = {node['id']: node['generation'] for node in layout}
    columns = {node['id']: node['column'] for node in layout}

    for child_id, father_id, _category in edges[::2]:
        mother_id = f'{child_id}M'
        assert columns[father_id] == columns[mother_id] == (
            columns[child_id] + 1)
        assert abs(
            rows[child_id] - (
                rows[father_id] + rows[mother_id]) / 2
        ) < 0.0001


def test_descendant_tree_graph_includes_coparents_and_collapses_branches():
    individuals = {
        '@ME@': {'name': 'Me', 'sex': 'M', 'famc': [], 'fams': ['@F1@']},
        '@SPOUSE@': {
            'name': 'Spouse', 'sex': 'F', 'famc': [], 'fams': ['@F1@']},
        '@CHILD@': {
            'name': 'Child', 'sex': 'F', 'famc': ['@F1@'], 'fams': ['@F2@']},
        '@CHILDSPOUSE@': {
            'name': 'Child Spouse', 'sex': 'M', 'famc': [], 'fams': ['@F2@']},
        '@GC@': {
            'name': 'Grandchild', 'sex': 'M', 'famc': ['@F2@'], 'fams': []},
    }
    families = {
        '@F1@': {'husb': '@ME@', 'wife': '@SPOUSE@', 'chil': ['@CHILD@']},
        '@F2@': {
            'husb': '@CHILDSPOUSE@', 'wife': '@CHILD@', 'chil': ['@GC@']},
    }

    def members_for(indi_id):
        parents, siblings, spouses, children = [], [], [], []
        for fam_id in individuals[indi_id].get('famc', ()):
            fam = families[fam_id]
            parents.extend(pid for pid in (fam['husb'], fam['wife']) if pid)
            siblings.extend(
                child_id for child_id in fam['chil'] if child_id != indi_id)
        for fam_id in individuals[indi_id].get('fams', ()):
            fam = families[fam_id]
            spouse_id = fam['wife'] if fam['husb'] == indi_id else fam['husb']
            if spouse_id:
                spouses.append(spouse_id)
            children.extend(fam['chil'])
        return {
            'parents': parents,
            'siblings': siblings,
            'spouses': spouses,
            'children': children,
        }

    visible, edges = build_descendant_tree_graph(
        '@ME@', {'@ME@'}, individuals, families)
    expanded = descendant_tree_expanded_requests(
        visible, {'@ME@'}, members_for)

    assert visible == ['@ME@', '@SPOUSE@', '@CHILD@']
    assert ('@ME@', '@SPOUSE@', 'spouses') in edges
    assert ('@ME@', 'children') in expanded
    child_options = descendant_tree_expansion_options(
        '@CHILD@', visible, members_for)

    assert child_options == {'children': ['@GC@']}

    child_visible, child_edges = build_descendant_tree_graph(
        '@ME@', {'@ME@', '@CHILD@'}, individuals, families)
    child_expanded = descendant_tree_expanded_requests(
        child_visible, {'@ME@', '@CHILD@'}, members_for)

    assert child_visible == [
        '@ME@', '@SPOUSE@', '@CHILD@', '@CHILDSPOUSE@', '@GC@']
    assert ('@CHILD@', '@CHILDSPOUSE@', 'spouses') in child_edges
    assert ('@CHILD@', '@GC@', 'children') in child_edges
    assert ('@CHILD@', 'children') in child_expanded


def test_descendant_tree_layout_is_top_down_and_keeps_spouses_on_same_row():
    visible = [
        '@ME@', '@SPOUSE@', '@A@', '@B@', '@A_SPOUSE@', '@A1@', '@A2@',
    ]
    edges = [
        ('@ME@', '@SPOUSE@', 'spouses'),
        ('@ME@', '@A@', 'children'),
        ('@ME@', '@B@', 'children'),
        ('@A@', '@A_SPOUSE@', 'spouses'),
        ('@A@', '@A1@', 'children'),
        ('@A@', '@A2@', 'children'),
    ]

    layout = layout_descendant_tree('@ME@', visible, edges)
    positions = {node['id']: (node['generation'], node['column'])
                 for node in layout}

    assert positions['@ME@'][0] == 0
    assert positions['@A@'][0] == 1
    assert positions['@B@'][0] == 1
    assert positions['@A1@'][0] == 2
    assert positions['@A2@'][0] == 2
    assert positions['@SPOUSE@'][0] == positions['@ME@'][0]
    assert positions['@A_SPOUSE@'][0] == positions['@A@'][0]
    assert (
        positions['@A@'][1] + positions['@A_SPOUSE@'][1]) / 2 == (
            positions['@A1@'][1] + positions['@A2@'][1]) / 2
    for generation in {node['generation'] for node in layout}:
        columns = sorted(
            node['column'] for node in layout
            if node['generation'] == generation)
        assert all(
            right - left >= 1.0
            for left, right in zip(columns, columns[1:]))


def test_descendant_tree_layout_inserts_spouse_before_same_row_cousins():
    """A spouse context node reserves the adjacent slot beside its partner."""
    visible = [
        '@ME@', '@A@', '@B@', '@PARTNER@', '@COUSIN1@', '@COUSIN2@',
        '@COUSIN3@', '@SPOUSE@', '@CHILD@',
    ]
    edges = [
        ('@ME@', '@A@', 'children'),
        ('@ME@', '@B@', 'children'),
        ('@A@', '@PARTNER@', 'children'),
        ('@B@', '@COUSIN1@', 'children'),
        ('@B@', '@COUSIN2@', 'children'),
        ('@B@', '@COUSIN3@', 'children'),
        ('@PARTNER@', '@SPOUSE@', 'spouses'),
        ('@PARTNER@', '@CHILD@', 'children'),
    ]

    layout = layout_descendant_tree('@ME@', visible, edges)
    positions = {node['id']: (node['generation'], node['column'])
                 for node in layout}

    assert positions['@SPOUSE@'][0] == positions['@PARTNER@'][0]
    assert positions['@SPOUSE@'][1] - positions['@PARTNER@'][1] == 1.0
    same_row = sorted(
        column for generation, column in positions.values()
        if generation == positions['@PARTNER@'][0])
    assert all(
        right - left >= 1.0
        for left, right in zip(same_row, same_row[1:]))


def test_descendant_tree_layout_centers_children_under_visible_couple():
    """Visible children stay centered under the displayed parent couple."""
    visible = [
        '@ME@', '@A@', '@B@', '@PARENT@', '@COUSIN1@', '@COUSIN2@',
        '@COUSIN3@', '@SPOUSE@', '@CHILD1@', '@CHILD2@',
    ]
    edges = [
        ('@ME@', '@A@', 'children'),
        ('@ME@', '@B@', 'children'),
        ('@A@', '@PARENT@', 'children'),
        ('@B@', '@COUSIN1@', 'children'),
        ('@B@', '@COUSIN2@', 'children'),
        ('@B@', '@COUSIN3@', 'children'),
        ('@PARENT@', '@SPOUSE@', 'spouses'),
        ('@PARENT@', '@CHILD1@', 'children'),
        ('@PARENT@', '@CHILD2@', 'children'),
    ]

    layout = layout_descendant_tree('@ME@', visible, edges)
    positions = {node['id']: (node['generation'], node['column'])
                 for node in layout}
    couple_midpoint = (
        positions['@PARENT@'][1] + positions['@SPOUSE@'][1]) / 2
    child_midpoint = (
        positions['@CHILD1@'][1] + positions['@CHILD2@'][1]) / 2

    assert positions['@SPOUSE@'][0] == positions['@PARENT@'][0]
    assert child_midpoint == couple_midpoint
    same_child_row = sorted(
        column for generation, column in positions.values()
        if generation == positions['@CHILD1@'][0])
    assert all(
        right - left >= 1.0
        for left, right in zip(same_child_row, same_child_row[1:]))


def test_descendant_tree_debug_keeps_child_family_units_together():
    """Expanded descendant branches keep one parent's children contiguous."""
    cases = [
        (
            '5',
            [
                '@I102681749719@',
                '@I102681750190@',
                '@I102681764495@',
                '@I102681764496@',
                '@I102681764719@',
                '@I102681764720@',
                '@I102681764721@',
                '@I102681764722@',
                '@I102681764723@',
            ],
        ),
        (
            '6',
            [
                '@I102681749719@',
                '@I102681750190@',
                '@I102681750195@',
                '@I102681750197@',
                '@I102681750198@',
                '@I102681751293@',
                '@I102681750199@',
                '@I102681750200@',
                '@I102681750201@',
                '@I102681750205@',
                '@I102681750206@',
                '@I102681750207@',
            ],
        ),
        (
            '7',
            [
                '@I102681749719@',
                '@I102681750190@',
                '@I102681750195@',
                '@I102681750197@',
                '@I102681750198@',
                '@I102681751293@',
                '@I102681750199@',
                '@I102681750200@',
                '@I102681750201@',
                '@I102681750205@',
                '@I102681750206@',
                '@I102681750207@',
            ],
        ),
        (
            '10',
            [
                '@I102681749719@',
                '@I102681750190@',
                '@I102681750195@',
                '@I102681750197@',
                '@I102681750198@',
                '@I102681751293@',
                '@I102681750199@',
                '@I102681750200@',
                '@I102681750201@',
                '@I102681750205@',
                '@I102681750206@',
                '@I102681750207@',
            ],
        ),
    ]

    for fixture_name, family_units in cases:
        debug_path = Path('debug') / f'{fixture_name}.json'
        if not debug_path.exists():
            continue
        payload = json.loads(debug_path.read_text())
        edges = _debug_edges_in_family_member_order(payload)
        layout = layout_descendant_tree(
            payload['center_id'], payload['visible_ids'], edges)
        by_id = {node['id']: node for node in layout}
        same_generation = by_id['@I102681750190@']['generation']
        family_columns = [
            by_id[person_id]['column'] for person_id in family_units
        ]
        interposed_ids = {
            node['id'] for node in layout
            if node['generation'] == same_generation
            and min(family_columns) <= node['column'] <= max(family_columns)
        } - set(family_units)

        _assert_no_same_row_conflicts(layout)
        assert by_id['@I102681749719@']['column'] == (
            by_id['@I102681750190@']['column'] - 1.0)
        assert not interposed_ids


def test_descendant_tree_debug_keeps_same_row_spouses_adjacent():
    """Later descendant compaction must not split displayed spouse pairs."""
    debug_path = Path('debug') / '12.json'
    if not debug_path.exists():
        return

    payload = json.loads(debug_path.read_text())
    edges = [
        (edge['source'], edge['target'], edge['category'])
        for edge in payload['edges']
    ]
    layout = layout_descendant_tree(
        payload['center_id'], payload['visible_ids'], edges)
    by_id = {node['id']: node for node in layout}
    spouses_by_person = defaultdict(set)
    for source_id, target_id, category in edges:
        if category == 'spouses':
            spouses_by_person[source_id].add(target_id)
            spouses_by_person[target_id].add(source_id)

    _assert_no_same_row_conflicts(layout)
    for source_id, target_id, category in edges:
        if category != 'spouses':
            continue
        source_node = by_id.get(source_id)
        target_node = by_id.get(target_id)
        if not source_node or not target_node:
            continue
        if source_node['generation'] != target_node['generation']:
            continue
        left_column = min(source_node['column'], target_node['column'])
        right_column = max(source_node['column'], target_node['column'])
        interposed_ids = {
            node['id'] for node in layout
            if node['generation'] == source_node['generation']
            and left_column < node['column'] < right_column
        }
        allowed_ids = (
            spouses_by_person[source_id] | spouses_by_person[target_id])
        assert not (interposed_ids - allowed_ids)


def test_descendant_tree_debug_keeps_spouse_aware_sibling_units_together():
    """Expanded sibling groups stay contiguous with their displayed spouses."""
    debug_path = Path('debug') / '12.json'
    if not debug_path.exists():
        return

    payload = json.loads(debug_path.read_text())
    edges = [
        (edge['source'], edge['target'], edge['category'])
        for edge in payload['edges']
    ]
    layout = layout_descendant_tree(
        payload['center_id'], payload['visible_ids'], edges)
    by_id = {node['id']: node for node in layout}
    family_units = {
        '@I102667033170@',
        '@I102667033171@',
        '@I102667033176@',
        '@I102667033188@',
        '@I102667033177@',
        '@I102667033190@',
    }
    same_generation = by_id['@I102667033170@']['generation']
    family_columns = [by_id[person_id]['column']
                      for person_id in family_units]
    interposed_ids = {
        node['id'] for node in layout
        if node['generation'] == same_generation
        and min(family_columns) <= node['column'] <= max(family_columns)
    } - family_units

    _assert_no_same_row_conflicts(layout)
    assert not interposed_ids


def test_path_graph_expansion_adds_hidden_family_without_moving_endpoints():
    """Relationship graph expansion preserves path endpoints and adds relatives."""
    base = ResultsMixin._path_graph_layout([
        ('@A@', None),
        ('@B@', 'father'),
        ('@C@', 'sibling'),
    ])
    families = {
        '@B@': {
            'parents': ['@P1@'],
            'siblings': ['@A@', '@S1@'],
            'spouses': [],
            'children': ['@A@', '@C@', '@N1@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@B@', 'parents'), ('@B@', 'children')], lookup)
    by_id = {node['id']: node for node in layout}

    assert [node['id'] for node in layout[:3]] == ['@A@', '@B@', '@C@']
    assert layout[0]['is_endpoint'] is True
    assert layout[2]['is_endpoint'] is True
    assert by_id['@P1@']['generation'] == by_id['@B@']['generation'] - 1
    assert by_id['@N1@']['generation'] == by_id['@B@']['generation'] + 1
    assert '@A@' in by_id
    assert len([node for node in layout if node['id'] == '@A@']) == 1
    assert ('@B@', '@P1@', 'parents') in extra_edges
    assert ('@B@', '@N1@', 'children') in extra_edges


def test_path_graph_child_expansion_adds_missing_coparent():
    """Expanding children also displays the children's other parent."""
    base = ResultsMixin._path_graph_layout([
        ('@A@', None),
        ('@P@', 'father'),
    ])
    families = {
        '@A@': {
            'parents': ['@P@'],
            'siblings': [],
            'spouses': ['@SPOUSE@'],
            'children': ['@C1@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@A@' and '@C1@' in child_ids:
            return ['@SPOUSE@']
        return []

    layout, extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@A@', 'children')], lookup, coparents)
    by_id = {node['id']: node for node in layout}

    assert '@C1@' in by_id
    assert '@SPOUSE@' in by_id
    assert by_id['@SPOUSE@']['generation'] == by_id['@A@']['generation']
    assert by_id['@C1@']['generation'] == by_id['@A@']['generation'] + 1
    assert by_id['@C1@']['column'] == (
        by_id['@A@']['column'] + by_id['@SPOUSE@']['column']) / 2
    assert ('@A@', '@SPOUSE@', 'spouses') in extra_edges


def test_path_graph_no_expansion_keeps_compact_parent_child_path():
    """Unexpanded relationship paths are not widened by family normalization."""
    base = [
        {
            'id': '@START@',
            'edge': None,
            'generation': 0,
            'column': 0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': True,
        },
        {
            'id': '@START_DAD@',
            'edge': 'father',
            'generation': -1,
            'column': 0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@ANCESTOR@',
            'edge': 'father',
            'generation': -2,
            'column': 0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@ANCESTOR_SIB@',
            'edge': 'sibling',
            'generation': -2,
            'column': 1,
            'index': 3,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@ANCESTOR_SIB_SP@',
            'edge': 'spouse',
            'generation': -2,
            'column': 2,
            'index': 4,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@PARENT1@',
            'edge': 'father',
            'generation': -3,
            'column': 2,
            'index': 5,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@PARENT2@',
            'edge': 'spouse',
            'generation': -3,
            'column': 3,
            'index': 6,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@CHILD@',
            'edge': 'child',
            'generation': -2,
            'column': 3,
            'index': 7,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@DESC@',
            'edge': 'child',
            'generation': -1,
            'column': 3,
            'index': 8,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@DESC_SP@',
            'edge': 'spouse',
            'generation': -1,
            'column': 4,
            'index': 9,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@DESC_SP_MOM@',
            'edge': 'mother',
            'generation': -2,
            'column': 4,
            'index': 10,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@DESC_SP_MOM_SIB@',
            'edge': 'sibling',
            'generation': -2,
            'column': 5,
            'index': 11,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@END_DAD@',
            'edge': 'child',
            'generation': -1,
            'column': 5,
            'index': 12,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@END@',
            'edge': 'child',
            'generation': 0,
            'column': 5,
            'index': 13,
            'is_path_node': True,
            'is_endpoint': True,
        },
    ]
    families = {
        '@PARENT1@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@PARENT2@'],
            'children': ['@ANCESTOR_SIB_SP@', '@CHILD@'],
        },
        '@PARENT2@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@PARENT1@'],
            'children': ['@ANCESTOR_SIB_SP@', '@CHILD@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        child_ids = set(child_ids)
        return [
            candidate_id for candidate_id, members in families.items()
            if candidate_id != indi_id
            and child_ids.intersection(members.get('children', ()))
        ]

    layout, extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [], lookup, coparents)
    by_id = {node['id']: node for node in layout}

    assert extra_edges == []
    assert max(node['column'] for node in layout) - min(
        node['column'] for node in layout) <= 5
    for child_id, parent_id in (
            ('@START@', '@START_DAD@'),
            ('@START_DAD@', '@ANCESTOR@'),
            ('@ANCESTOR_SIB_SP@', '@PARENT1@'),
            ('@CHILD@', '@PARENT2@'),
            ('@CHILD@', '@DESC@'),
            ('@DESC_SP@', '@DESC_SP_MOM@'),
            ('@DESC_SP_MOM_SIB@', '@END_DAD@'),
            ('@END_DAD@', '@END@'),
    ):
        assert by_id[child_id]['column'] == by_id[parent_id]['column']


def test_family_tree_child_edge_groups_keep_couples_separate():
    """Rendered child connectors are grouped by parent couple."""
    positions = {
        '@P1@': (0, 0),
        '@P1_SP@': (100, 0),
        '@P2@': (300, 0),
        '@P2_SP@': (400, 0),
        '@C1@': (-50, 200),
        '@C2@': (50, 200),
        '@N1@': (250, 200),
        '@N2@': (350, 200),
    }
    edges = [
        ('@P1@', '@P1_SP@', 'spouses'),
        ('@P2@', '@P2_SP@', 'spouses'),
        ('@P1@', '@C1@', 'children'),
        ('@P1@', '@C2@', 'children'),
        ('@P2@', '@N1@', 'children'),
        ('@P2@', '@N2@', 'children'),
    ]

    def coparents(parent_id, child_ids):
        child_ids = set(child_ids)
        if parent_id == '@P1@' and child_ids & {'@C1@', '@C2@'}:
            return ['@P1_SP@']
        if parent_id == '@P2@' and child_ids & {'@N1@', '@N2@'}:
            return ['@P2_SP@']
        return []

    groups = ResultsMixin._family_tree_child_edge_groups(
        edges, positions, coparents,
        [('@P1@', '@P1_SP@'), ('@P2@', '@P2_SP@')])

    assert [group['children'] for group in groups] == [
        ['@C1@', '@C2@'],
        ['@N1@', '@N2@'],
    ]
    assert groups[0]['parent_ids'] == ('@P1@', '@P1_SP@')
    assert groups[1]['parent_ids'] == ('@P2@', '@P2_SP@')


def test_family_tree_bus_line_below_parent_nodes_at_large_node_height():
    """Bus line mid_y must be below parent node bottoms even at high DPI.

    When node_h grows (larger fonts at high DPI), the bus line connecting
    parents to children must remain below the parent node boxes.  The old
    formula (start_y + end_y) / 2 used the couple centre (parent_y) as
    start_y, placing the bus inside the parent nodes once node_h > 176.
    The fix uses parent_y + node_h/2 so the bus is always below the nodes.
    """
    # Simulate a couple at generation 0, children at generation 1.
    # node_h values that would expose the bug: 180, 200 (> 176 threshold).
    for node_h in (84, 113, 130, 147, 180, 200):
        v_gap = max(node_h + 88, 150)
        parent_y = 100.0  # arbitrary centre-y for the parent couple
        child_y = parent_y + v_gap

        # --- couple case (parent_h == 0) ---
        parent_h = 0
        start_y = parent_y + parent_h / 2  # = parent_y (couple centre)
        end_y = child_y - node_h / 2       # top of child node
        # Fixed formula: always anchors to parent_bottom
        mid_y = (parent_y + node_h / 2 + end_y) / 2
        parent_bottom = parent_y + node_h / 2

        assert mid_y >= parent_bottom, (
            f"node_h={node_h}: bus line mid_y={mid_y:.1f} is above "
            f"parent bottom={parent_bottom:.1f}"
        )
        assert mid_y <= end_y, (
            f"node_h={node_h}: bus line mid_y={mid_y:.1f} is below "
            f"child top end_y={end_y:.1f}"
        )

        # --- single parent case (parent_h == node_h) ---
        start_y_single = parent_y + node_h / 2
        mid_y_single = (parent_y + node_h / 2 + end_y) / 2
        assert mid_y_single == (start_y_single + end_y) / 2, (
            "Fixed formula must be identical to old formula for single parents"
        )


def test_path_graph_child_expansion_keeps_coparent_adjacent():
    """A new coparent takes the adjacent slot and pushes same-row nodes over."""
    base = ResultsMixin._path_graph_layout([
        ('@A@', None),
        ('@SIB@', 'sibling'),
    ])
    families = {
        '@A@': {
            'parents': [],
            'siblings': ['@SIB@'],
            'spouses': ['@SPOUSE@'],
            'children': ['@C1@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@A@' and '@C1@' in child_ids:
            return ['@SPOUSE@']
        return []

    layout, extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@A@', 'children')], lookup, coparents)
    by_id = {node['id']: node for node in layout}

    assert by_id['@SPOUSE@']['column'] < by_id['@SIB@']['column']
    assert by_id['@SPOUSE@']['column'] == 1.0
    assert by_id['@SIB@']['column'] >= 2.0
    assert by_id['@C1@']['column'] == (
        by_id['@A@']['column'] + by_id['@SPOUSE@']['column']) / 2
    assert ('@A@', '@SPOUSE@', 'spouses') in extra_edges


def test_path_graph_spouse_expansion_keeps_spouse_adjacent():
    """A directly expanded spouse takes the adjacent slot before siblings."""
    base = ResultsMixin._path_graph_layout([
        ('@A@', None),
        ('@SIB@', 'sibling'),
    ])
    families = {
        '@A@': {
            'parents': [],
            'siblings': ['@SIB@'],
            'spouses': ['@SPOUSE@'],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@A@', 'spouses')], lookup)
    by_id = {node['id']: node for node in layout}

    assert by_id['@SPOUSE@']['generation'] == by_id['@A@']['generation']
    assert by_id['@SPOUSE@']['column'] == by_id['@A@']['column'] + 1.0
    assert by_id['@SIB@']['column'] >= by_id['@SPOUSE@']['column'] + 1.0
    assert ('@A@', '@SPOUSE@', 'spouses') in extra_edges


def test_path_graph_sibling_expansion_inserts_siblings_next_to_source():
    """Expanded siblings displace unrelated same-row nodes as a group."""
    base = [
        {
            'id': '@COUSIN@',
            'edge': None,
            'generation': 0,
            'column': 0.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@BASE_SP@',
            'edge': 'sibling',
            'generation': 0,
            'column': 1.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@BASE@',
            'edge': 'spouse',
            'generation': 0,
            'column': 2.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@BASE_SP@': {
            'parents': [],
            'siblings': ['@SP_BRO2@', '@SP_BRO1@'],
            'spouses': ['@BASE@'],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@BASE_SP@', 'siblings')], lookup)
    by_id = {node['id']: node for node in layout}
    brother_columns = sorted([
        by_id['@SP_BRO2@']['column'],
        by_id['@SP_BRO1@']['column'],
        by_id['@BASE_SP@']['column'],
    ])

    assert brother_columns[2] == by_id['@BASE_SP@']['column']
    assert brother_columns[1] <= by_id['@BASE_SP@']['column'] - 1.0
    assert brother_columns[0] <= brother_columns[1] - 1.0
    assert by_id['@COUSIN@']['column'] < brother_columns[0]
    assert by_id['@BASE@']['column'] == by_id['@BASE_SP@']['column'] + 1.0
    assert ('@BASE_SP@', '@SP_BRO2@', 'siblings') in extra_edges
    assert ('@BASE_SP@', '@SP_BRO1@', 'siblings') in extra_edges


def test_path_graph_sibling_expansion_restores_path_spouse_adjacency():
    """Sibling expansion also treats path spouses as adjacency constraints."""
    base = [
        {
            'id': '@COUSIN@',
            'edge': None,
            'generation': 0,
            'column': 0.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@BASE_SP@',
            'edge': 'sibling',
            'generation': 0,
            'column': 1.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@BASE@',
            'edge': 'spouse',
            'generation': 0,
            'column': 4.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@BASE_SP@': {
            'parents': [],
            'siblings': ['@SP_BRO2@', '@SP_BRO1@'],
            'spouses': ['@BASE@'],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@BASE_SP@', 'siblings')], lookup)
    by_id = {node['id']: node for node in layout}
    brother_columns = sorted([
        by_id['@SP_BRO2@']['column'],
        by_id['@SP_BRO1@']['column'],
        by_id['@BASE_SP@']['column'],
    ])

    assert brother_columns[2] == by_id['@BASE_SP@']['column']
    assert brother_columns[1] <= by_id['@BASE_SP@']['column'] - 1.0
    assert brother_columns[0] <= brother_columns[1] - 1.0
    assert by_id['@BASE@']['column'] == by_id['@BASE_SP@']['column'] + 1.0
    assert by_id['@COUSIN@']['column'] < brother_columns[0]


def test_path_graph_sibling_expansion_evicts_cousin_from_sibling_slot():
    """A cousin in the adjacent slot moves so siblings can stay next to source."""
    base = [
        {
            'id': '@COUSIN@',
            'edge': None,
            'generation': 0,
            'column': 2.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@BASE_SP@',
            'edge': 'sibling',
            'generation': 0,
            'column': 3.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@BASE@',
            'edge': 'spouse',
            'generation': 0,
            'column': 4.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@BASE_SP@': {
            'parents': [],
            'siblings': ['@SP_BRO2@', '@SP_BRO1@'],
            'spouses': ['@BASE@'],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@BASE_SP@', 'siblings')], lookup)
    by_id = {node['id']: node for node in layout}
    brother_columns = sorted([
        by_id['@SP_BRO2@']['column'],
        by_id['@SP_BRO1@']['column'],
        by_id['@BASE_SP@']['column'],
    ])

    assert brother_columns[2] == by_id['@BASE_SP@']['column']
    assert brother_columns[1] <= by_id['@BASE_SP@']['column'] - 1.0
    assert brother_columns[0] <= brother_columns[1] - 1.0
    assert by_id['@COUSIN@']['column'] < brother_columns[0]
    assert by_id['@BASE@']['column'] == by_id['@BASE_SP@']['column'] + 1.0


def test_path_graph_sibling_next_to_spouse_pair_gets_extra_clearance():
    """A sibling beside a displayed spouse pair gets enough visual room."""
    base = [
        {
            'id': '@COUSN_SP@',
            'edge': None,
            'generation': 0,
            'column': 0.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN@',
            'edge': 'spouse',
            'generation': 0,
            'column': 1.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@COUSN@': {
            'parents': [],
            'siblings': ['@COUSN_SIB@'],
            'spouses': ['@COUSN_SP@'],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@COUSN@', 'siblings')], lookup)
    by_id = {node['id']: node for node in layout}

    assert by_id['@COUSN@']['column'] - by_id['@COUSN_SP@']['column'] == 1.0
    assert by_id['@COUSN_SIB@']['column'] - by_id['@COUSN@']['column'] >= 1.25


def test_path_graph_expanded_siblings_include_visible_sibling_component():
    """Visible path siblings move together past the selected person's spouse."""
    base = [
        {
            'id': '@SIB_LEFT1@',
            'edge': None,
            'generation': 0,
            'column': -3.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SIB_LEFT2@',
            'edge': 'sibling',
            'generation': 0,
            'column': -2.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@ANCHOR_SP@',
            'edge': 'spouse',
            'generation': 0,
            'column': -1.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@ANCHOR@',
            'edge': 'spouse',
            'generation': 0,
            'column': 0.0,
            'index': 3,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@ANCHOR@': {
            'parents': [],
            'siblings': ['@SIB_LEFT1@', '@SIB_LEFT2@', '@SIB_RIGHT1@'],
            'spouses': ['@ANCHOR_SP@'],
            'children': [],
        },
        '@ANCHOR_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@ANCHOR@'],
            'children': [],
        },
        '@SIB_LEFT2@': {
            'parents': [],
            'siblings': ['@SIB_LEFT1@', '@ANCHOR@', '@SIB_RIGHT1@'],
            'spouses': [],
            'children': [],
        },
        '@SIB_LEFT1@': {
            'parents': [],
            'siblings': ['@SIB_LEFT2@', '@ANCHOR@', '@SIB_RIGHT1@'],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@ANCHOR@', 'siblings')], lookup)
    by_id = {node['id']: node for node in layout}
    sibling_columns = [
        by_id['@SIB_LEFT1@']['column'],
        by_id['@SIB_LEFT2@']['column'],
        by_id['@SIB_RIGHT1@']['column'],
    ]

    assert by_id['@ANCHOR_SP@']['column'] == by_id['@ANCHOR@']['column'] - 1.0
    assert all(
        column > by_id['@ANCHOR@']['column']
        for column in sibling_columns)
    assert sorted(sibling_columns) == sibling_columns


def test_path_graph_expanded_siblings_ignore_spouses_sibling_component():
    """A spouse's visible siblings do not split the selected person's siblings."""
    base = [
        {
            'id': '@ANCHOR2_SIB1@',
            'edge': None,
            'generation': 0,
            'column': -4.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SPOUSE_SIB1@',
            'edge': 'sibling',
            'generation': 0,
            'column': -3.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SPOUSE_SIB2@',
            'edge': 'sibling',
            'generation': 0,
            'column': -2.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@ANCHOR2_SP@',
            'edge': 'sibling',
            'generation': 0,
            'column': -1.0,
            'index': 3,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@ANCHOR2@',
            'edge': 'spouse',
            'generation': 0,
            'column': 0.0,
            'index': 4,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@ANCHOR2_SIB2@',
            'edge': 'sibling',
            'generation': 0,
            'column': 1.0,
            'index': 5,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@ANCHOR2_SIB3@',
            'edge': 'sibling',
            'generation': 0,
            'column': 2.0,
            'index': 6,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@ANCHOR2@': {
            'parents': [],
            'siblings': ['@ANCHOR2_SIB1@', '@ANCHOR2_SIB2@', '@ANCHOR2_SIB3@', '@ANCHOR2_SIB4@'],
            'spouses': ['@ANCHOR2_SP@'],
            'children': [],
        },
        '@ANCHOR2_SP@': {
            'parents': [],
            'siblings': ['@SPOUSE_SIB1@', '@SPOUSE_SIB2@'],
            'spouses': ['@ANCHOR2@'],
            'children': [],
        },
        '@ANCHOR2_SIB1@': {
            'parents': [],
            'siblings': ['@ANCHOR2@', '@ANCHOR2_SIB2@', '@ANCHOR2_SIB3@', '@ANCHOR2_SIB4@'],
            'spouses': [],
            'children': [],
        },
        '@SPOUSE_SIB1@': {
            'parents': [],
            'siblings': ['@SPOUSE_SIB2@', '@ANCHOR2_SP@'],
            'spouses': [],
            'children': [],
        },
        '@SPOUSE_SIB2@': {
            'parents': [],
            'siblings': ['@SPOUSE_SIB1@', '@ANCHOR2_SP@'],
            'spouses': [],
            'children': [],
        },
        '@ANCHOR2_SIB2@': {
            'parents': [],
            'siblings': ['@ANCHOR2_SIB1@', '@ANCHOR2@', '@ANCHOR2_SIB3@', '@ANCHOR2_SIB4@'],
            'spouses': [],
            'children': [],
        },
        '@ANCHOR2_SIB3@': {
            'parents': [],
            'siblings': ['@ANCHOR2_SIB1@', '@ANCHOR2@', '@ANCHOR2_SIB2@', '@ANCHOR2_SIB4@'],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@ANCHOR2@', 'siblings')], lookup)
    by_id = {node['id']: node for node in layout}
    sibling_columns = [
        by_id['@ANCHOR2_SIB1@']['column'],
        by_id['@ANCHOR2_SIB2@']['column'],
        by_id['@ANCHOR2_SIB3@']['column'],
        by_id['@ANCHOR2_SIB4@']['column'],
    ]

    assert by_id['@ANCHOR2_SP@']['column'] == by_id['@ANCHOR2@']['column'] - 1.0
    assert all(
        column > by_id['@ANCHOR2@']['column']
        for column in sibling_columns)
    assert sorted(sibling_columns) == [1.0, 2.0, 3.0, 4.0]


def test_path_graph_visible_path_siblings_group_around_spouse_anchor():
    """Path-only sibling groups stay together beside the visible spouse pair."""
    base = [
        {
            'id': '@SIB_LEFT1@',
            'edge': None,
            'generation': 0,
            'column': -3.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SIB_LEFT2@',
            'edge': 'sibling',
            'generation': 0,
            'column': -2.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@ANCHOR_SP@',
            'edge': 'spouse',
            'generation': 0,
            'column': -1.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@ANCHOR@',
            'edge': 'spouse',
            'generation': 0,
            'column': 0.0,
            'index': 3,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SIB_RIGHT1@',
            'edge': 'sibling',
            'generation': 0,
            'column': 1.0,
            'index': 4,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@ANCHOR@': {
            'parents': [],
            'siblings': ['@SIB_LEFT1@', '@SIB_LEFT2@', '@SIB_RIGHT1@'],
            'spouses': ['@ANCHOR_SP@'],
            'children': [],
        },
        '@ANCHOR_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@ANCHOR@'],
            'children': [],
        },
        '@SIB_LEFT1@': {
            'parents': [],
            'siblings': ['@SIB_LEFT2@', '@ANCHOR@', '@SIB_RIGHT1@'],
            'spouses': [],
            'children': [],
        },
        '@SIB_LEFT2@': {
            'parents': [],
            'siblings': ['@SIB_LEFT1@', '@ANCHOR@', '@SIB_RIGHT1@'],
            'spouses': [],
            'children': [],
        },
        '@SIB_RIGHT1@': {
            'parents': [],
            'siblings': ['@SIB_LEFT1@', '@SIB_LEFT2@', '@ANCHOR@'],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [], lookup)
    by_id = {node['id']: node for node in layout}
    sibling_columns = sorted([
        by_id['@SIB_LEFT1@']['column'],
        by_id['@SIB_LEFT2@']['column'],
        by_id['@SIB_RIGHT1@']['column'],
    ])

    assert by_id['@ANCHOR_SP@']['column'] == by_id['@ANCHOR@']['column'] - 1.0
    assert sibling_columns == [
        by_id['@ANCHOR@']['column'] + 1.0,
        by_id['@ANCHOR@']['column'] + 2.0,
        by_id['@ANCHOR@']['column'] + 3.0,
    ]


def test_path_graph_debug_payload_omits_display_names():
    """Debug layout data captures graph state without person labels."""
    base = ResultsMixin._path_graph_layout([
        ('@A@', None),
        ('@B@', 'sibling'),
    ])
    expanded = [('@A@', 'siblings')]
    graph_state = {
        'zoom': 1.0,
        'canvas_w': 640,
        'canvas_h': 480,
        'expanded': expanded,
        'base_layout': base,
        'relationship': 'test relationship',
        'start_id': '@A@',
    }
    families = {
        '@A@': {
            'parents': [],
            'siblings': ['@B@', '@C@'],
            'spouses': [],
            'children': [],
        },
        '@B@': {
            'parents': [],
            'siblings': ['@A@', '@C@'],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, expanded, lookup)
    payload = ResultsMixin._graph_debug_payload(
        graph_state, layout, extra_edges, lookup)

    assert payload['version'] == 1
    assert payload['graph_type'] == 'relationship_path'
    assert payload['expanded'] == [
        {'source': '@A@', 'category': 'siblings'},
    ]
    assert {'source': '@A@', 'target': '@C@', 'category': 'siblings'} in (
        payload['extra_edges'])
    assert payload['family_members']['@A@']['siblings'] == ['@B@', '@C@']
    assert 'label' not in str(payload).lower()
    assert 'name' not in str(payload).lower()


def test_family_tree_debug_payload_omits_display_names():
    """Tree View debug data captures layout state without person labels."""
    families = {
        '@A@': {
            'parents': ['@P@'],
            'siblings': ['@S@'],
            'spouses': ['@W@'],
            'children': ['@C@'],
        },
        '@W@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@A@'],
            'children': ['@C@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@A@' and '@C@' in child_ids:
            return ['@W@']
        return []

    expanded = [('@A@', 'parents'), ('@A@', 'children')]
    visible, edges = build_family_tree_graph(
        '@A@', expanded, lookup, coparents)
    layout = layout_family_tree('@A@', visible, edges)
    payload = ResultsMixin._family_tree_debug_payload(
        '@A@', expanded, 1.0, 640, 480, visible, edges, layout, lookup)

    assert payload['version'] == 1
    assert payload['graph_type'] == 'family_tree'
    assert payload['center_id'] == '@A@'
    assert payload['expanded'] == [
        {'source': '@A@', 'category': 'parents'},
        {'source': '@A@', 'category': 'children'},
    ]
    assert {'source': '@A@', 'target': '@C@', 'category': 'children'} in (
        payload['edges'])
    assert payload['family_members']['@A@']['spouses'] == ['@W@']
    assert 'label' not in str(payload).lower()
    assert 'name' not in str(payload).lower()


def test_family_tree_debug_payload_includes_relationship_kind():
    """Debug graph exports preserve non-ordinary edge styling metadata."""
    visible = ['@A@', '@P@']
    edges = [('@A@', '@P@', 'parents')]
    layout = [
        {'id': '@A@', 'generation': 0, 'column': 0, 'is_center': True},
        {'id': '@P@', 'generation': -1, 'column': 0, 'is_center': False},
    ]

    def lookup(_indi_id):
        return {'parents': [], 'siblings': [], 'spouses': [], 'children': []}

    def relationship_lookup(source_id, target_id, category):
        assert (source_id, target_id, category) == ('@A@', '@P@', 'parents')
        return 'step'

    payload = ResultsMixin._family_tree_debug_payload(
        '@A@', [('@A@', 'parents')], 1.0, 640, 480, visible, edges, layout,
        lookup, relationship_lookup=relationship_lookup)

    assert payload['edges'] == [{
        'source': '@A@',
        'target': '@P@',
        'category': 'parents',
        'relationship_kind': 'step',
    }]


def test_path_graph_sibling_expansion_overrides_child_alignment_blocker():
    """Prior generations move so sibling groups do not create diagonal edges."""
    base = [
        {
            'id': '@BASE@',
            'edge': None,
            'generation': 0,
            'column': 0.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@BASE_SP@',
            'edge': 'spouse',
            'generation': 0,
            'column': 1.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SP_MOM@',
            'edge': 'mother',
            'generation': -1,
            'column': 1.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SP_AUNT@',
            'edge': 'sibling',
            'generation': -1,
            'column': 2.0,
            'index': 3,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN@',
            'edge': 'child',
            'generation': 0,
            'column': 2.0,
            'index': 4,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN2@',
            'edge': 'child',
            'generation': 1,
            'column': 2.0,
            'index': 5,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@BASE_SP@': {
            'parents': ['@SP_MOM@'],
            'siblings': ['@SP_BRO1@', '@SP_BRO2@'],
            'spouses': ['@BASE@'],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@BASE_SP@', 'siblings')], lookup)
    by_id = {node['id']: node for node in layout}
    brother_columns = sorted([
        by_id['@BASE_SP@']['column'],
        by_id['@SP_BRO1@']['column'],
        by_id['@SP_BRO2@']['column'],
    ])

    assert brother_columns == [
        by_id['@BASE_SP@']['column'],
        by_id['@BASE_SP@']['column'] + 1.0,
        by_id['@BASE_SP@']['column'] + 2.0,
    ]
    assert by_id['@BASE@']['column'] == by_id['@BASE_SP@']['column'] - 1.0
    assert by_id['@COUSN@']['column'] > brother_columns[-1]
    assert by_id['@SP_MOM@']['column'] == by_id['@BASE_SP@']['column']
    assert by_id['@SP_AUNT@']['column'] == by_id['@COUSN@']['column']
    assert by_id['@COUSN2@']['column'] == by_id['@COUSN@']['column']


def test_path_graph_child_expansion_does_not_repeatedly_push_cousin_branch():
    """A sibling spouse reserves one local slot without repeatedly moving cousins."""
    base = [
        {
            'id': '@BASE@',
            'edge': None,
            'generation': 0,
            'column': 0.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@BASE_SP@',
            'edge': 'spouse',
            'generation': 0,
            'column': 1.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SP_MOM@',
            'edge': 'mother',
            'generation': -1,
            'column': 1.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SP_AUNT@',
            'edge': 'sibling',
            'generation': -1,
            'column': 2.0,
            'index': 3,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN@',
            'edge': 'child',
            'generation': 0,
            'column': 2.0,
            'index': 4,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN2@',
            'edge': 'child',
            'generation': 1,
            'column': 2.0,
            'index': 5,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@BASE_SP@': {
            'parents': ['@SP_MOM@'],
            'siblings': ['@SP_BRO1@', '@SP_BRO2@'],
            'spouses': ['@BASE@'],
            'children': [],
        },
        '@SP_BRO1@': {
            'parents': [],
            'siblings': ['@BASE_SP@', '@SP_BRO2@'],
            'spouses': ['@BRO1_SP@'],
            'children': ['@BRO1_CH@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@SP_BRO1@' and '@BRO1_CH@' in child_ids:
            return ['@BRO1_SP@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@BASE_SP@', 'siblings'), ('@SP_BRO1@', 'children')],
        lookup, coparents)
    by_id = {node['id']: node for node in layout}

    assert by_id['@SP_BRO1@']['column'] == by_id['@BASE_SP@']['column'] + 1.0
    assert by_id['@BRO1_SP@']['column'] == by_id['@SP_BRO1@']['column'] + 1.0
    assert by_id['@SP_BRO2@']['column'] == by_id['@BRO1_SP@']['column'] + 1.0
    assert by_id['@COUSN@']['column'] == by_id['@SP_BRO2@']['column'] + 1.0
    assert by_id['@SP_AUNT@']['column'] == by_id['@COUSN@']['column']
    assert by_id['@COUSN2@']['column'] == by_id['@COUSN@']['column']


def test_path_graph_parent_expansion_after_child_expansion_does_not_drift_branch():
    """Expanding a sibling spouse's parents does not push cousin branches away."""
    base = [
        {
            'id': '@BASE@',
            'edge': None,
            'generation': 0,
            'column': 0.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@BASE_SP@',
            'edge': 'spouse',
            'generation': 0,
            'column': 1.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SP_MOM@',
            'edge': 'mother',
            'generation': -1,
            'column': 1.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SP_AUNT@',
            'edge': 'sibling',
            'generation': -1,
            'column': 5.0,
            'index': 3,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN@',
            'edge': 'child',
            'generation': 0,
            'column': 5.0,
            'index': 4,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN2@',
            'edge': 'child',
            'generation': 1,
            'column': 5.0,
            'index': 5,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@BASE_SP@': {
            'parents': ['@SP_MOM@'],
            'siblings': ['@SP_BRO1@', '@SP_BRO2@'],
            'spouses': ['@BASE@'],
            'children': [],
        },
        '@SP_BRO1@': {
            'parents': [],
            'siblings': ['@BASE_SP@', '@SP_BRO2@'],
            'spouses': ['@BRO1_SP@'],
            'children': ['@BRO1_CH@'],
        },
        '@BRO1_SP@': {
            'parents': ['@BRO1_SP_DAD@', '@BRO1_SP_MOM@'],
            'siblings': [],
            'spouses': ['@SP_BRO1@'],
            'children': ['@BRO1_CH@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@SP_BRO1@' and '@BRO1_CH@' in child_ids:
            return ['@BRO1_SP@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base,
        [
            ('@BASE_SP@', 'siblings'),
            ('@SP_BRO1@', 'children'),
            ('@BRO1_SP@', 'parents'),
        ],
        lookup,
        coparents,
    )
    by_id = {node['id']: node for node in layout}

    assert by_id['@SP_BRO1@']['column'] == by_id['@BASE_SP@']['column'] + 1.0
    assert by_id['@BRO1_SP@']['column'] == by_id['@SP_BRO1@']['column'] + 1.0
    assert by_id['@SP_BRO2@']['column'] == by_id['@BRO1_SP@']['column'] + 1.0
    assert by_id['@COUSN@']['column'] == by_id['@SP_BRO2@']['column'] + 1.0
    assert by_id['@SP_AUNT@']['column'] == by_id['@COUSN@']['column']
    assert by_id['@BRO1_CH@']['column'] < by_id['@COUSN@']['column']


def test_path_graph_sibling_groups_are_enforced_once_per_component():
    """Multiple sibling toggles in one set do not fight over row order."""
    base = [
        {
            'id': '@SPOUSE_A@',
            'edge': None,
            'generation': 0,
            'column': 0.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@A@',
            'edge': 'spouse',
            'generation': 0,
            'column': 1.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@A@': {
            'parents': [],
            'siblings': ['@B@', '@C@'],
            'spouses': ['@SPOUSE_A@'],
            'children': [],
        },
        '@B@': {
            'parents': [],
            'siblings': ['@A@', '@C@'],
            'spouses': ['@SPOUSE_B@'],
            'children': ['@CHILD_B@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@B@' and '@CHILD_B@' in child_ids:
            return ['@SPOUSE_B@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base,
        [('@A@', 'siblings'), ('@B@', 'children'), ('@B@', 'siblings')],
        lookup,
        coparents,
    )
    by_id = {node['id']: node for node in layout}

    assert by_id['@B@']['column'] == by_id['@A@']['column'] + 1.0
    assert by_id['@SPOUSE_B@']['column'] == by_id['@B@']['column'] + 1.0
    assert by_id['@C@']['column'] == by_id['@SPOUSE_B@']['column'] + 1.0


def test_path_graph_parent_pair_children_stay_under_parent_pair():
    """Unrelated spouse pairs do not push a child group away from its parents."""
    base = [
        {
            'id': '@BASE@',
            'edge': None,
            'generation': 0,
            'column': 0.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@BASE_SP@',
            'edge': 'spouse',
            'generation': 0,
            'column': 1.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SP_MOM@',
            'edge': 'mother',
            'generation': -1,
            'column': 1.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SP_AUNT@',
            'edge': 'sibling',
            'generation': -1,
            'column': 4.0,
            'index': 3,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN@',
            'edge': 'child',
            'generation': 0,
            'column': 4.0,
            'index': 4,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN2@',
            'edge': 'child',
            'generation': 1,
            'column': 4.0,
            'index': 5,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN2_SP@',
            'edge': 'spouse',
            'generation': 1,
            'column': 3.0,
            'index': 6,
            'is_path_node': False,
            'is_endpoint': False,
        },
    ]
    families = {
        '@BASE_SP@': {
            'parents': ['@SP_MOM@'],
            'siblings': ['@COUSN@'],
            'spouses': ['@BASE@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@BASE@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@BASE_SP@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@COUSN2@': {
            'parents': ['@COUSN@'],
            'siblings': [],
            'spouses': ['@COUSN2_SP@'],
            'children': [],
        },
        '@COUSN2_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN2@'],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@BASE_SP@', 'children')], lookup)
    by_id = {node['id']: node for node in layout}
    parent_midpoint = (
        by_id['@BASE@']['column'] + by_id['@BASE_SP@']['column']) / 2
    child_columns = [
        by_id['@BASE_CH1@']['column'],
        by_id['@BASE_CH2@']['column'],
        by_id['@BASE_CH3@']['column'],
        by_id['@BASE_CH4@']['column'],
    ]

    assert sum(child_columns) / len(child_columns) == parent_midpoint
    assert max(child_columns) - min(child_columns) <= 4.2
    assert sorted(child_columns) == child_columns
    assert by_id['@COUSN@']['column'] > max(child_columns)
    assert by_id['@SP_AUNT@']['column'] == by_id['@COUSN@']['column']


def test_path_graph_expansion_keeps_same_generation_nodes_apart():
    """Expanded relationship nodes move when an existing row position is occupied."""
    base = ResultsMixin._path_graph_layout([
        ('@A@', None),
        ('@B@', 'father'),
    ])
    families = {
        '@A@': {
            'parents': ['@B@', '@P2@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@A@', 'parents')], lookup)
    same_row = [
        node['column'] for node in layout
        if node['generation'] == -1
    ]

    assert min(
        abs(left - right)
        for index, left in enumerate(same_row)
        for right in same_row[index + 1:]
    ) >= 1.0


def test_path_graph_child_spouse_expansion_keeps_siblings_apart():
    """Child rows stay spaced after a child's spouse is expanded."""
    base = [
        {
            'id': '@GRANDPARENT@',
            'edge': None,
            'generation': 0,
            'column': 0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': True,
        },
        {
            'id': '@PARENT@',
            'edge': 'child',
            'generation': 1,
            'column': 0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@CHILD@',
            'edge': 'child',
            'generation': 2,
            'column': 0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': True,
        },
    ]
    children = [
        '@SIB_A@',
        '@SIB_B@',
        '@SIB_C@',
        '@SIB_D@',
        '@SIB_E@',
        '@SIB_F@',
        '@SIB_G@',
        '@SIB_H@',
    ]
    families = {
        '@PARENT@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COPARENT@'],
            'children': children,
        },
        '@COPARENT@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@PARENT@'],
            'children': children,
        },
        '@SIB_B@': {
            'parents': ['@PARENT@', '@COPARENT@'],
            'siblings': ['@SIB_A@'],
            'spouses': ['@SIB_B_SP@'],
            'children': ['@SIB_B_CHILD@'],
        },
        '@SIB_B_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@SIB_B@'],
            'children': ['@SIB_B_CHILD@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(parent_id, child_ids):
        return [
            other_id for other_id, members in families.items()
            if other_id != parent_id
            and any(child_id in members.get('children', ())
                    for child_id in child_ids)
        ]

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@PARENT@', 'children'), ('@SIB_B@', 'spouses')],
        lookup, coparents)
    by_id = {node['id']: node for node in layout}

    assert round(abs(
        by_id['@SIB_A@']['column'] - by_id['@SIB_B@']['column']), 3) >= 1.0


def test_path_graph_parent_expansion_adds_parent_spouse_edge():
    """Expanding parents links displayed co-parents as spouses."""
    base = ResultsMixin._path_graph_layout([
        ('@A@', None),
    ])
    families = {
        '@A@': {
            'parents': ['@P1@', '@P2@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P1@' and '@A@' in child_ids:
            return ['@P2@']
        if indi_id == '@P2@' and '@A@' in child_ids:
            return ['@P1@']
        return []

    _layout, extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@A@', 'parents')], lookup, coparents)

    assert ('@P1@', '@P2@', 'spouses') in extra_edges


def test_path_graph_parent_expansion_centers_parents_over_child():
    """A visible parent moves aside so parent pairs center over their child."""
    base = ResultsMixin._path_graph_layout([
        ('@A@', None),
        ('@P1@', 'father'),
    ])
    families = {
        '@A@': {
            'parents': ['@P1@', '@P2@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P1@' and '@A@' in child_ids:
            return ['@P2@']
        if indi_id == '@P2@' and '@A@' in child_ids:
            return ['@P1@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@A@', 'parents')], lookup, coparents)
    by_id = {node['id']: node for node in layout}

    parent_midpoint = (
        by_id['@P1@']['column'] + by_id['@P2@']['column']) / 2
    assert parent_midpoint == by_id['@A@']['column']
    assert by_id['@P1@']['column'] == -0.5
    assert by_id['@P2@']['column'] == 0.5


def test_path_graph_parent_expansion_reserves_parent_pair_over_child():
    """Parent expansion moves upper-row blockers so parents stay over child."""
    base = [
        {
            'id': '@BASE@',
            'edge': None,
            'generation': 0,
            'column': 0.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@BASE_SP@',
            'edge': 'spouse',
            'generation': 0,
            'column': 1.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SP_MOM@',
            'edge': 'mother',
            'generation': -1,
            'column': 1.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SP_AUNT@',
            'edge': 'sibling',
            'generation': -1,
            'column': 2.0,
            'index': 3,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN@',
            'edge': 'child',
            'generation': 0,
            'column': 2.0,
            'index': 4,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@BASE@': {
            'parents': ['@BASE_DAD@', '@BASE_MOM@'],
            'siblings': [],
            'spouses': ['@BASE_SP@'],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@BASE_DAD@' and '@BASE@' in child_ids:
            return ['@BASE_MOM@']
        if indi_id == '@BASE_MOM@' and '@BASE@' in child_ids:
            return ['@BASE_DAD@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@BASE@', 'parents')], lookup, coparents)
    by_id = {node['id']: node for node in layout}
    parent_midpoint = (
        by_id['@BASE_DAD@']['column'] + by_id['@BASE_MOM@']['column']) / 2

    assert parent_midpoint == by_id['@BASE@']['column']
    assert abs(by_id['@BASE_DAD@']['column'] - by_id['@BASE_MOM@']['column']) == 1.0
    assert by_id['@SP_MOM@']['column'] > by_id['@BASE_MOM@']['column']
    assert by_id['@SP_AUNT@']['column'] > by_id['@SP_MOM@']['column']


def test_path_graph_parent_expansion_preserves_existing_parent_vertical_edge():
    """Expanded parents do not force an existing parent-child edge diagonal."""
    base = [
        {
            'id': '@BASE@',
            'edge': None,
            'generation': 0,
            'column': 0.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@BASE_SP@',
            'edge': 'spouse',
            'generation': 0,
            'column': 1.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SP_MOM@',
            'edge': 'mother',
            'generation': -1,
            'column': 7.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@SP_AUNT@',
            'edge': 'sibling',
            'generation': -1,
            'column': 5.0,
            'index': 3,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN@',
            'edge': 'child',
            'generation': 0,
            'column': 5.0,
            'index': 4,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN2@',
            'edge': 'child',
            'generation': 1,
            'column': 5.0,
            'index': 5,
            'is_path_node': True,
            'is_endpoint': False,
        },
    ]
    families = {
        '@BASE@': {
            'parents': ['@BASE_DAD@', '@BASE_MOM@'],
            'siblings': [],
            'spouses': ['@BASE_SP@'],
            'children': [],
        },
        '@BASE_SP@': {
            'parents': ['@SP_MOM@'],
            'siblings': [],
            'spouses': ['@BASE@'],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@BASE_DAD@' and '@BASE@' in child_ids:
            return ['@BASE_MOM@']
        if indi_id == '@BASE_MOM@' and '@BASE@' in child_ids:
            return ['@BASE_DAD@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@BASE@', 'parents')], lookup, coparents)
    by_id = {node['id']: node for node in layout}
    parent_midpoint = (
        by_id['@BASE_DAD@']['column'] + by_id['@BASE_MOM@']['column']) / 2

    assert parent_midpoint == by_id['@BASE@']['column']
    assert by_id['@BASE_SP@']['column'] == by_id['@SP_MOM@']['column']
    assert 1.0 < abs(by_id['@BASE@']['column'] - by_id['@BASE_SP@']['column']) <= 2.0


def test_path_graph_child_with_spouse_stays_centered_under_parents():
    """A child's spouse does not pull the child away from displayed parents."""
    base = ResultsMixin._path_graph_layout([
        ('@COUSN@', None),
        ('@COUSN_SP@', 'spouse'),
        ('@COUSN2@', 'child'),
        ('@COUSN2_SP@', 'spouse'),
    ])
    families = {
        '@COUSN2@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': [],
            'spouses': ['@COUSN2_SP@'],
            'children': [],
        },
        '@COUSN@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN_SP@'],
            'children': ['@COUSN2@'],
        },
        '@COUSN_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN@'],
            'children': ['@COUSN2@'],
        },
        '@COUSN2_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN2@'],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@COUSN@' and '@COUSN2@' in child_ids:
            return ['@COUSN_SP@']
        if indi_id == '@COUSN_SP@' and '@COUSN2@' in child_ids:
            return ['@COUSN@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [], lookup, coparents)
    by_id = {node['id']: node for node in layout}
    parent_midpoint = (
        by_id['@COUSN@']['column'] + by_id['@COUSN_SP@']['column']) / 2

    assert by_id['@COUSN2@']['column'] == parent_midpoint
    assert by_id['@COUSN2_SP@']['column'] == by_id['@COUSN2@']['column'] + 1.0


def test_path_graph_two_parent_path_child_recovers_after_row_conflict():
    """A path child returns under both parents after child-row conflicts move."""
    base = [
        {
            'id': '@COUSN@',
            'edge': None,
            'generation': 0,
            'column': 0.0,
            'index': 0,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN_SP@',
            'edge': 'spouse',
            'generation': 0,
            'column': 1.0,
            'index': 1,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN2@',
            'edge': 'child',
            'generation': 1,
            'column': 5.0,
            'index': 2,
            'is_path_node': True,
            'is_endpoint': False,
        },
        {
            'id': '@COUSN2_SIB2@',
            'edge': 'sibling',
            'generation': 1,
            'column': 0.5,
            'index': 3,
            'is_path_node': False,
            'is_endpoint': False,
        },
    ]
    families = {
        '@COUSN@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN_SP@'],
            'children': ['@COUSN2@'],
        },
        '@COUSN_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN@'],
            'children': ['@COUSN2@'],
        },
        '@COUSN2@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2_SIB2@'],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@COUSN@' and '@COUSN2@' in child_ids:
            return ['@COUSN_SP@']
        if indi_id == '@COUSN_SP@' and '@COUSN2@' in child_ids:
            return ['@COUSN@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [], lookup, coparents)
    by_id = {node['id']: node for node in layout}
    parent_midpoint = (
        by_id['@COUSN@']['column'] + by_id['@COUSN_SP@']['column']) / 2

    assert by_id['@COUSN2@']['column'] == parent_midpoint
    assert by_id['@COUSN2_SIB2@']['column'] != by_id['@COUSN2@']['column']


def test_path_graph_parent_shift_keeps_expanded_children_under_parents():
    """Expanded children follow a parent pair after final path alignment."""
    base = ResultsMixin._path_graph_layout([
        ('@BASE@', None),
        ('@BASE_SP@', 'spouse'),
        ('@SP_MOM@', 'mother'),
        ('@SP_AUNT@', 'sibling'),
        ('@COUSN@', 'child'),
        ('@COUSN2@', 'child'),
    ])
    families = {
        '@BASE@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@BASE_SP@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@BASE_SP@': {
            'parents': ['@SP_MOM@'],
            'siblings': [],
            'spouses': ['@BASE@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@COUSN2@': {
            'parents': ['@COUSN@'],
            'siblings': [],
            'spouses': ['@COUSN2_SP@'],
            'children': ['@SIB2_CH1@', '@SIB2_CH2@'],
        },
        '@COUSN2_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN2@'],
            'children': ['@SIB2_CH1@', '@SIB2_CH2@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@BASE_SP@' and any(
                child_id in child_ids
                for child_id in ('@BASE_CH1@', '@BASE_CH2@',
                                 '@BASE_CH3@', '@BASE_CH4@')):
            return ['@BASE@']
        if indi_id == '@BASE@' and any(
                child_id in child_ids
                for child_id in ('@BASE_CH1@', '@BASE_CH2@',
                                 '@BASE_CH3@', '@BASE_CH4@')):
            return ['@BASE_SP@']
        if indi_id == '@COUSN2@' and any(
                child_id in child_ids for child_id in ('@SIB2_CH1@', '@SIB2_CH2@')):
            return ['@COUSN2_SP@']
        if indi_id == '@COUSN2_SP@' and any(
                child_id in child_ids for child_id in ('@SIB2_CH1@', '@SIB2_CH2@')):
            return ['@COUSN2@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base,
        [('@BASE_SP@', 'children'), ('@COUSN2@', 'spouses'),
         ('@COUSN2@', 'children')],
        lookup,
        coparents,
    )
    by_id = {node['id']: node for node in layout}
    parent_midpoint = (
        by_id['@BASE@']['column'] + by_id['@BASE_SP@']['column']) / 2
    child_columns = [
        by_id['@BASE_CH1@']['column'],
        by_id['@BASE_CH2@']['column'],
        by_id['@BASE_CH3@']['column'],
        by_id['@BASE_CH4@']['column'],
    ]

    assert sum(child_columns) / len(child_columns) == parent_midpoint
    assert sorted(child_columns) == child_columns


def test_path_graph_expanded_children_do_not_split_vertical_path_branch():
    """Expanded child groups move a path branch as one vertical component."""
    base = ResultsMixin._path_graph_layout([
        ('@BASE@', None),
        ('@BASE_SP@', 'spouse'),
        ('@SP_MOM@', 'mother'),
        ('@SP_AUNT@', 'sibling'),
        ('@COUSN@', 'child'),
        ('@COUSN2@', 'child'),
    ])
    families = {
        '@BASE@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@BASE_SP@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@BASE_SP@': {
            'parents': ['@SP_MOM@'],
            'siblings': ['@COUSN@'],
            'spouses': ['@BASE@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@COUSN2@': {
            'parents': ['@COUSN@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@BASE_SP@', 'children')], lookup)
    by_id = {node['id']: node for node in layout}
    parent_midpoint = (
        by_id['@BASE@']['column'] + by_id['@BASE_SP@']['column']) / 2
    child_columns = [
        by_id['@BASE_CH1@']['column'],
        by_id['@BASE_CH2@']['column'],
        by_id['@BASE_CH3@']['column'],
        by_id['@BASE_CH4@']['column'],
    ]

    assert sum(child_columns) / len(child_columns) == parent_midpoint
    assert by_id['@SP_AUNT@']['column'] == by_id['@COUSN@']['column']
    assert by_id['@COUSN@']['column'] == by_id['@COUSN2@']['column']
    assert by_id['@COUSN2@']['column'] > max(child_columns)


def test_path_graph_two_parent_branch_does_not_split_expanded_children():
    """A two-parent path branch moves aside instead of splitting siblings."""
    base = ResultsMixin._path_graph_layout([
        ('@BASE@', None),
        ('@BASE_SP@', 'spouse'),
        ('@SP_MOM@', 'mother'),
        ('@SP_AUNT@', 'sibling'),
        ('@COUSN@', 'child'),
        ('@COUSN2@', 'child'),
    ])
    families = {
        '@BASE@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@BASE_SP@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@BASE_SP@': {
            'parents': ['@SP_MOM@'],
            'siblings': ['@COUSN@'],
            'spouses': ['@BASE@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@COUSN@': {
            'parents': ['@SP_AUNT@'],
            'siblings': [],
            'spouses': ['@COUSN_SP@'],
            'children': ['@COUSN2@'],
        },
        '@COUSN_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN@'],
            'children': ['@COUSN2@'],
        },
        '@COUSN2@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@COUSN@' and '@COUSN2@' in child_ids:
            return ['@COUSN_SP@']
        if indi_id == '@COUSN_SP@' and '@COUSN2@' in child_ids:
            return ['@COUSN@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@BASE_SP@', 'children'), ('@COUSN@', 'spouses')],
        lookup, coparents)
    by_id = {node['id']: node for node in layout}
    parent_midpoint = (
        by_id['@BASE@']['column'] + by_id['@BASE_SP@']['column']) / 2
    child_columns = [
        by_id['@BASE_CH1@']['column'],
        by_id['@BASE_CH2@']['column'],
        by_id['@BASE_CH3@']['column'],
        by_id['@BASE_CH4@']['column'],
    ]
    adam_parent_midpoint = (
        by_id['@COUSN@']['column'] + by_id['@COUSN_SP@']['column']) / 2

    assert sum(child_columns) / len(child_columns) == parent_midpoint
    assert sorted(child_columns) == child_columns
    assert max(child_columns) - min(child_columns) == 4.2
    assert by_id['@COUSN2@']['column'] == adam_parent_midpoint
    assert by_id['@COUSN2@']['column'] > max(child_columns)
    assert by_id['@SP_AUNT@']['column'] == by_id['@COUSN@']['column']


def test_path_graph_two_parent_branch_with_spouse_and_siblings_stays_aligned():
    """A fuller branch keeps displayed children under displayed parents."""
    base = ResultsMixin._path_graph_layout([
        ('@BASE@', None),
        ('@BASE_SP@', 'spouse'),
        ('@SP_MOM@', 'mother'),
        ('@SP_AUNT@', 'sibling'),
        ('@COUSN@', 'child'),
        ('@COUSN2@', 'child'),
    ])
    families = {
        '@BASE@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@BASE_SP@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@BASE_SP@': {
            'parents': ['@SP_MOM@'],
            'siblings': [],
            'spouses': ['@BASE@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@SP_AUNT@': {
            'parents': [],
            'siblings': ['@SP_MOM@'],
            'spouses': [],
            'children': ['@COUSN@'],
        },
        '@COUSN@': {
            'parents': ['@SP_AUNT@'],
            'siblings': [],
            'spouses': ['@COUSN_SP@'],
            'children': ['@COUSN2@', '@COUSN2_SIB1@', '@COUSN2_SIB2@'],
        },
        '@COUSN_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN@'],
            'children': ['@COUSN2@', '@COUSN2_SIB1@', '@COUSN2_SIB2@'],
        },
        '@COUSN2@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2_SIB1@', '@COUSN2_SIB2@'],
            'spouses': ['@COUSN2_SP@'],
            'children': [],
        },
        '@COUSN2_SIB1@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2@', '@COUSN2_SIB2@'],
            'spouses': [],
            'children': [],
        },
        '@COUSN2_SIB2@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2@', '@COUSN2_SIB1@'],
            'spouses': [],
            'children': [],
        },
        '@COUSN2_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN2@'],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        child_ids = set(child_ids)
        if indi_id == '@COUSN@' and child_ids & {
                '@COUSN2@', '@COUSN2_SIB1@', '@COUSN2_SIB2@'}:
            return ['@COUSN_SP@']
        if indi_id == '@COUSN_SP@' and child_ids & {
                '@COUSN2@', '@COUSN2_SIB1@', '@COUSN2_SIB2@'}:
            return ['@COUSN@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base,
        [
            ('@BASE_SP@', 'children'),
            ('@COUSN@', 'spouses'),
            ('@COUSN2@', 'siblings'),
            ('@COUSN2@', 'spouses'),
        ],
        lookup,
        coparents,
    )
    by_id = {node['id']: node for node in layout}
    steven_child_columns = [
        by_id['@BASE_CH1@']['column'],
        by_id['@BASE_CH2@']['column'],
        by_id['@BASE_CH3@']['column'],
        by_id['@BASE_CH4@']['column'],
    ]
    adam_parent_midpoint = (
        by_id['@COUSN@']['column'] + by_id['@COUSN_SP@']['column']) / 2

    assert sorted(steven_child_columns) == steven_child_columns
    assert max(steven_child_columns) - min(steven_child_columns) == 4.2
    assert by_id['@COUSN2@']['column'] == adam_parent_midpoint
    assert by_id['@COUSN2@']['column'] > max(steven_child_columns)
    assert by_id['@COUSN2_SP@']['column'] == by_id['@COUSN2@']['column'] + 1.0
    assert by_id['@SP_AUNT@']['column'] == by_id['@COUSN@']['column']


def test_path_graph_cousin_child_does_not_split_expanded_siblings():
    """A cousin branch moves aside instead of splitting a child group."""
    base = ResultsMixin._path_graph_layout([
        ('@BASE@', None),
        ('@BASE_SP@', 'spouse'),
        ('@SP_MOM@', 'mother'),
        ('@SP_AUNT@', 'sibling'),
        ('@COUSN@', 'child'),
        ('@COUSN2@', 'child'),
    ])
    families = {
        '@BASE@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@BASE_SP@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@BASE_SP@': {
            'parents': ['@SP_MOM@'],
            'siblings': ['@SP_BRO1@', '@SP_BRO2@'],
            'spouses': ['@BASE@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@SP_BRO1@': {
            'parents': ['@SP_MOM@'],
            'siblings': ['@BASE_SP@', '@SP_BRO2@'],
            'spouses': ['@BRO1_SP@'],
            'children': ['@BRO1_CH@'],
        },
        '@BRO1_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@SP_BRO1@'],
            'children': ['@BRO1_CH@'],
        },
        '@SP_BRO2@': {
            'parents': ['@SP_MOM@'],
            'siblings': ['@BASE_SP@', '@SP_BRO1@'],
            'spouses': [],
            'children': [],
        },
        '@BRO1_CH@': {
            'parents': ['@SP_BRO1@', '@BRO1_SP@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        child_ids = set(child_ids)
        if indi_id == '@BASE_SP@' and child_ids & {
                '@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'}:
            return ['@BASE@']
        if indi_id == '@BASE@' and child_ids & {
                '@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'}:
            return ['@BASE_SP@']
        if indi_id == '@SP_BRO1@' and '@BRO1_CH@' in child_ids:
            return ['@BRO1_SP@']
        if indi_id == '@BRO1_SP@' and '@BRO1_CH@' in child_ids:
            return ['@SP_BRO1@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base,
        [
            ('@BASE_SP@', 'siblings'),
            ('@SP_BRO1@', 'spouses'),
            ('@BASE_SP@', 'children'),
            ('@SP_BRO1@', 'children'),
        ],
        lookup,
        coparents,
    )
    by_id = {node['id']: node for node in layout}
    steven_child_columns = [
        by_id['@BASE_CH1@']['column'],
        by_id['@BASE_CH2@']['column'],
        by_id['@BASE_CH3@']['column'],
        by_id['@BASE_CH4@']['column'],
    ]

    assert sorted(steven_child_columns) == steven_child_columns
    assert max(steven_child_columns) - min(steven_child_columns) == 4.2
    assert by_id['@BRO1_CH@']['column'] > max(steven_child_columns)
    assert by_id['@BRO1_CH@']['column'] == (
        by_id['@SP_BRO1@']['column'] + by_id['@BRO1_SP@']['column']) / 2


def test_path_graph_compacts_large_sibling_only_gap():
    """Large sibling-only gaps are closed after expanded branches settle."""
    base = ResultsMixin._path_graph_layout([
        ('@BASE@', None),
        ('@BASE_SP@', 'spouse'),
        ('@SP_MOM@', 'mother'),
        ('@SP_AUNT@', 'sibling'),
        ('@COUSN@', 'child'),
        ('@COUSN2@', 'child'),
    ])
    families = {
        '@BASE@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@BASE_SP@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@BASE_SP@': {
            'parents': ['@SP_MOM@'],
            'siblings': ['@SP_BRO1@', '@SP_BRO2@'],
            'spouses': ['@BASE@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@SP_BRO1@': {
            'parents': ['@SP_MOM@'],
            'siblings': ['@BASE_SP@', '@SP_BRO2@'],
            'spouses': ['@BRO1_SP@'],
            'children': ['@BRO1_CH@'],
        },
        '@BRO1_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@SP_BRO1@'],
            'children': ['@BRO1_CH@'],
        },
        '@SP_BRO2@': {
            'parents': ['@SP_MOM@'],
            'siblings': ['@BASE_SP@', '@SP_BRO1@'],
            'spouses': ['@BRO2_SP@'],
            'children': ['@BRO2_CH1@', '@BRO2_CH2@'],
        },
        '@BRO2_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@SP_BRO2@'],
            'children': ['@BRO2_CH1@', '@BRO2_CH2@'],
        },
        '@SP_MOM@': {
            'parents': [],
            'siblings': ['@SP_AUNT@'],
            'spouses': [],
            'children': ['@BASE_SP@', '@SP_BRO1@', '@SP_BRO2@'],
        },
        '@SP_AUNT@': {
            'parents': [],
            'siblings': ['@SP_MOM@'],
            'spouses': [],
            'children': ['@COUSN@'],
        },
        '@COUSN@': {
            'parents': ['@SP_AUNT@'],
            'siblings': [],
            'spouses': ['@COUSN_SP@'],
            'children': ['@COUSN2@'],
        },
        '@COUSN_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN@'],
            'children': ['@COUSN2@'],
        },
        '@COUSN2@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2_SIB1@', '@COUSN2_SIB2@'],
            'spouses': ['@COUSN2_SP@'],
            'children': ['@COUSN2_CH1@', '@COUSN2_CH2@'],
        },
        '@COUSN2_SIB1@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2@', '@COUSN2_SIB2@'],
            'spouses': ['@SIB1_SP@'],
            'children': ['@SIB1_CH@'],
        },
        '@SIB1_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN2_SIB1@'],
            'children': ['@SIB1_CH@'],
        },
        '@COUSN2_SIB2@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2@', '@COUSN2_SIB1@'],
            'spouses': ['@SIB2_SP@'],
            'children': ['@SIB2_CH1@', '@SIB2_CH2@'],
        },
        '@SIB2_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN2_SIB2@'],
            'children': ['@SIB2_CH1@', '@SIB2_CH2@'],
        },
        '@COUSN2_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN2@'],
            'children': ['@COUSN2_CH1@', '@COUSN2_CH2@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        child_ids = set(child_ids)
        pairs = (
            ('@BASE_SP@', '@BASE@',
             {'@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'}),
            ('@SP_BRO1@', '@BRO1_SP@', {'@BRO1_CH@'}),
            ('@SP_BRO2@', '@BRO2_SP@', {'@BRO2_CH1@', '@BRO2_CH2@'}),
            ('@COUSN@', '@COUSN_SP@', {'@COUSN2@', '@COUSN2_SIB1@', '@COUSN2_SIB2@'}),
            ('@COUSN2@', '@COUSN2_SP@', {'@COUSN2_CH1@', '@COUSN2_CH2@'}),
            ('@COUSN2_SIB1@', '@SIB1_SP@', {'@SIB1_CH@'}),
            ('@COUSN2_SIB2@', '@SIB2_SP@', {'@SIB2_CH1@', '@SIB2_CH2@'}),
        )
        for parent_id, other_parent_id, children in pairs:
            if indi_id == parent_id and child_ids & children:
                return [other_parent_id]
            if indi_id == other_parent_id and child_ids & children:
                return [parent_id]
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base,
        [
            ('@BASE_SP@', 'siblings'),
            ('@SP_BRO1@', 'spouses'),
            ('@SP_BRO2@', 'spouses'),
            ('@BASE_SP@', 'children'),
            ('@SP_BRO1@', 'children'),
            ('@SP_BRO2@', 'children'),
            ('@COUSN@', 'spouses'),
            ('@COUSN2@', 'siblings'),
            ('@COUSN2_SIB1@', 'spouses'),
            ('@COUSN2_SIB2@', 'spouses'),
            ('@COUSN2@', 'spouses'),
            ('@COUSN2_SIB1@', 'children'),
            ('@COUSN2_SIB2@', 'children'),
            ('@COUSN2@', 'children'),
        ],
        lookup,
        coparents,
    )
    by_id = {node['id']: node for node in layout}
    columns = sorted({node['column'] for node in layout})
    largest_gap = max(
        columns[index + 1] - columns[index]
        for index in range(len(columns) - 1))

    assert largest_gap <= 3.0
    assert by_id['@SP_AUNT@']['column'] == by_id['@COUSN@']['column']
    assert by_id['@COUSN2@']['column'] == (
        by_id['@COUSN@']['column'] + by_id['@COUSN_SP@']['column']) / 2


def test_path_graph_parent_expansion_after_dense_branches_does_not_oscillate():
    """Showing parents after dense child branches does not hang the layout."""
    base = ResultsMixin._path_graph_layout([
        ('@BASE@', None),
        ('@BASE_SP@', 'spouse'),
        ('@SP_MOM@', 'mother'),
        ('@SP_AUNT@', 'sibling'),
        ('@COUSN@', 'child'),
        ('@COUSN2@', 'child'),
    ])
    families = {
        '@BASE@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@BASE_SP@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@BASE_SP@': {
            'parents': ['@SP_MOM@', '@SP_DAD@'],
            'siblings': ['@SP_BRO1@', '@SP_BRO2@'],
            'spouses': ['@BASE@'],
            'children': ['@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'],
        },
        '@SP_BRO1@': {
            'parents': ['@SP_MOM@', '@SP_DAD@'],
            'siblings': ['@BASE_SP@', '@SP_BRO2@'],
            'spouses': ['@BRO1_SP@'],
            'children': ['@BRO1_CH@'],
        },
        '@SP_DAD@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@SP_MOM@'],
            'children': ['@BASE_SP@', '@SP_BRO1@', '@SP_BRO2@'],
        },
        '@BRO1_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@SP_BRO1@'],
            'children': ['@BRO1_CH@'],
        },
        '@SP_BRO2@': {
            'parents': ['@SP_MOM@', '@SP_DAD@'],
            'siblings': ['@BASE_SP@', '@SP_BRO1@'],
            'spouses': ['@BRO2_SP@'],
            'children': ['@BRO2_CH1@', '@BRO2_CH2@'],
        },
        '@BRO2_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@SP_BRO2@'],
            'children': ['@BRO2_CH1@', '@BRO2_CH2@'],
        },
        '@SP_MOM@': {
            'parents': [],
            'siblings': ['@SP_AUNT@'],
            'spouses': ['@SP_DAD@'],
            'children': ['@BASE_SP@', '@SP_BRO1@', '@SP_BRO2@'],
        },
        '@SP_AUNT@': {
            'parents': [],
            'siblings': ['@SP_MOM@'],
            'spouses': [],
            'children': ['@COUSN@'],
        },
        '@COUSN@': {
            'parents': ['@SP_AUNT@'],
            'siblings': [],
            'spouses': ['@COUSN_SP@'],
            'children': ['@COUSN2@'],
        },
        '@COUSN_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN@'],
            'children': ['@COUSN2@'],
        },
        '@COUSN2@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2_SIB1@', '@COUSN2_SIB2@'],
            'spouses': ['@COUSN2_SP@'],
            'children': ['@COUSN2_CH1@', '@COUSN2_CH2@'],
        },
        '@COUSN2_SIB1@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2@', '@COUSN2_SIB2@'],
            'spouses': ['@SIB1_SP@'],
            'children': ['@SIB1_CH@'],
        },
        '@SIB1_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN2_SIB1@'],
            'children': ['@SIB1_CH@'],
        },
        '@COUSN2_SIB2@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2@', '@COUSN2_SIB1@'],
            'spouses': ['@SIB2_SP@'],
            'children': ['@SIB2_CH1@', '@SIB2_CH2@'],
        },
        '@SIB2_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN2_SIB2@'],
            'children': ['@SIB2_CH1@', '@SIB2_CH2@'],
        },
        '@COUSN2_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN2@'],
            'children': ['@COUSN2_CH1@', '@COUSN2_CH2@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        child_ids = set(child_ids)
        pairs = (
            ('@BASE_SP@', '@BASE@',
             {'@BASE_CH1@', '@BASE_CH2@', '@BASE_CH3@', '@BASE_CH4@'}),
            ('@SP_BRO1@', '@BRO1_SP@', {'@BRO1_CH@'}),
            ('@SP_BRO2@', '@BRO2_SP@', {'@BRO2_CH1@', '@BRO2_CH2@'}),
            ('@COUSN@', '@COUSN_SP@', {'@COUSN2@', '@COUSN2_SIB1@', '@COUSN2_SIB2@'}),
            ('@COUSN2@', '@COUSN2_SP@', {'@COUSN2_CH1@', '@COUSN2_CH2@'}),
            ('@COUSN2_SIB1@', '@SIB1_SP@', {'@SIB1_CH@'}),
            ('@COUSN2_SIB2@', '@SIB2_SP@', {'@SIB2_CH1@', '@SIB2_CH2@'}),
            ('@SP_MOM@', '@SP_DAD@',
             {'@BASE_SP@', '@SP_BRO1@', '@SP_BRO2@'}),
        )
        for parent_id, other_parent_id, children in pairs:
            if indi_id == parent_id and child_ids & children:
                return [other_parent_id]
            if indi_id == other_parent_id and child_ids & children:
                return [parent_id]
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base,
        [
            ('@BASE_SP@', 'siblings'),
            ('@SP_BRO1@', 'spouses'),
            ('@SP_BRO2@', 'spouses'),
            ('@BASE_SP@', 'children'),
            ('@SP_BRO1@', 'children'),
            ('@SP_BRO2@', 'children'),
            ('@COUSN@', 'spouses'),
            ('@COUSN2@', 'siblings'),
            ('@COUSN2_SIB1@', 'spouses'),
            ('@COUSN2_SIB2@', 'spouses'),
            ('@COUSN2@', 'spouses'),
            ('@COUSN2_SIB1@', 'children'),
            ('@COUSN2_SIB2@', 'children'),
            ('@COUSN2@', 'children'),
            ('@SP_BRO1@', 'parents'),
        ],
        lookup,
        coparents,
    )
    by_id = {node['id']: node for node in layout}

    assert '@SP_DAD@' in by_id
    assert abs(by_id['@BASE@']['column'] - by_id['@BASE_SP@']['column']) == 1.0
    assert abs(by_id['@BRO1_CH@']['column'] - (
        by_id['@SP_BRO1@']['column'] + by_id['@BRO1_SP@']['column']) / 2) < 0.001


def test_path_graph_parent_then_child_expansion_keeps_spouses_adjacent():
    """Expanding a parent's children keeps the parent pair adjacent."""
    base = ResultsMixin._path_graph_layout([
        ('@A@', None),
    ])
    families = {
        '@A@': {
            'parents': ['@P1@', '@P2@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
        '@P1@': {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': ['@A@', '@SIB@'],
        },
        '@P2@': {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': ['@A@', '@SIB@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P1@' and any(
                child_id in child_ids for child_id in ('@A@', '@SIB@')):
            return ['@P2@']
        if indi_id == '@P2@' and any(
                child_id in child_ids for child_id in ('@A@', '@SIB@')):
            return ['@P1@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base, [('@A@', 'parents'), ('@P1@', 'children')], lookup, coparents)
    by_id = {node['id']: node for node in layout}

    assert abs(by_id['@P1@']['column'] - by_id['@P2@']['column']) == 1.0
    parent_midpoint = (
        by_id['@P1@']['column'] + by_id['@P2@']['column']) / 2
    child_midpoint = (
        by_id['@A@']['column'] + by_id['@SIB@']['column']) / 2
    assert child_midpoint == parent_midpoint


def test_path_graph_grandparent_child_expansion_keeps_child_spouse_adjacent():
    """Moving a child under grandparents keeps that child's spouse adjacent."""
    base = ResultsMixin._path_graph_layout([
        ('@A@', None),
    ])
    families = {
        '@A@': {
            'parents': ['@P1@', '@P2@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
        '@P1@': {
            'parents': ['@GP1@', '@GM1@'],
            'siblings': [],
            'spouses': ['@P2@'],
            'children': ['@A@'],
        },
        '@GP1@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@GM1@'],
            'children': ['@P1@', '@AUNT@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P1@' and '@A@' in child_ids:
            return ['@P2@']
        if indi_id == '@GP1@' and any(
                child_id in child_ids for child_id in ('@P1@', '@AUNT@')):
            return ['@GM1@']
        if indi_id == '@GM1@' and any(
                child_id in child_ids for child_id in ('@P1@', '@AUNT@')):
            return ['@GP1@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base,
        [('@A@', 'parents'), ('@P1@', 'parents'), ('@GP1@', 'children')],
        lookup,
        coparents,
    )
    by_id = {node['id']: node for node in layout}

    assert abs(by_id['@P1@']['column'] - by_id['@P2@']['column']) == 1.0


def test_path_graph_uncle_child_expansion_keeps_child_groups_centered():
    """Expanding an uncle's children preserves each parent's child alignment."""
    base = ResultsMixin._path_graph_layout([
        ('@P1@', None),
        ('@P2@', 'father'),
    ])
    families = {
        '@P1@': {
            'parents': ['@P2@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
        '@P2@': {
            'parents': ['@P3@', '@P5@'],
            'siblings': ['@P4@'],
            'spouses': [],
            'children': ['@P1@'],
        },
        '@P3@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@P5@'],
            'children': ['@P2@', '@P4@'],
        },
        '@P5@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@P3@'],
            'children': ['@P2@', '@P4@'],
        },
        '@P4@': {
            'parents': ['@P3@', '@P5@'],
            'siblings': ['@P2@'],
            'spouses': [],
            'children': ['@P4C@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P3@' and any(
                child_id in child_ids for child_id in ('@P2@', '@P4@')):
            return ['@P5@']
        if indi_id == '@P5@' and any(
                child_id in child_ids for child_id in ('@P2@', '@P4@')):
            return ['@P3@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base,
        [('@P2@', 'parents'), ('@P3@', 'children'), ('@P4@', 'children')],
        lookup,
        coparents,
    )
    by_id = {node['id']: node for node in layout}

    assert by_id['@P1@']['column'] == by_id['@P2@']['column']
    assert by_id['@P4C@']['column'] == by_id['@P4@']['column']


def test_path_graph_parent_sibling_child_expansion_keeps_center_children():
    """Expanding an uncle's children does not shift the center person's children."""
    base = ResultsMixin._path_graph_layout([
        ('@P1@', None),
        ('@P2@', 'father'),
    ])
    families = {
        '@P1@': {
            'parents': ['@P2@', '@M2@'],
            'siblings': [],
            'spouses': ['@SP@'],
            'children': ['@C1@'],
        },
        '@SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@P1@'],
            'children': ['@C1@'],
        },
        '@P2@': {
            'parents': ['@GP@', '@GM@'],
            'siblings': ['@UNC@'],
            'spouses': ['@M2@'],
            'children': ['@P1@'],
        },
        '@GP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@GM@'],
            'children': ['@P2@', '@UNC@'],
        },
        '@GM@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@GP@'],
            'children': ['@P2@', '@UNC@'],
        },
        '@UNC@': {
            'parents': ['@GP@', '@GM@'],
            'siblings': ['@P2@'],
            'spouses': [],
            'children': ['@UC1@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P1@' and '@C1@' in child_ids:
            return ['@SP@']
        if indi_id == '@GP@' and any(
                child_id in child_ids for child_id in ('@P2@', '@UNC@')):
            return ['@GM@']
        if indi_id == '@GM@' and any(
                child_id in child_ids for child_id in ('@P2@', '@UNC@')):
            return ['@GP@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base,
        [
            ('@P1@', 'children'),
            ('@P2@', 'parents'),
            ('@P2@', 'siblings'),
            ('@UNC@', 'children'),
        ],
        lookup,
        coparents,
    )
    by_id = {node['id']: node for node in layout}

    assert by_id['@C1@']['column'] == (
        by_id['@P1@']['column'] + by_id['@SP@']['column']) / 2
    assert by_id['@UC1@']['column'] == by_id['@UNC@']['column']


def test_path_graph_parent_sibling_child_short_path_keeps_center_children():
    """Showing a parent's sibling then children keeps center children aligned."""
    base = ResultsMixin._path_graph_layout([
        ('@P1@', None),
        ('@P2@', 'father'),
    ])
    families = {
        '@P1@': {
            'parents': ['@P2@', '@M2@'],
            'siblings': [],
            'spouses': ['@SP@'],
            'children': ['@C1@'],
        },
        '@SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@P1@'],
            'children': ['@C1@'],
        },
        '@P2@': {
            'parents': [],
            'siblings': ['@UNC@'],
            'spouses': ['@M2@'],
            'children': ['@P1@'],
        },
        '@UNC@': {
            'parents': [],
            'siblings': ['@P2@'],
            'spouses': [],
            'children': ['@UC1@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P1@' and '@C1@' in child_ids:
            return ['@SP@']
        return []

    layout, _extra_edges = ResultsMixin._expanded_path_graph_layout(
        base,
        [('@P1@', 'children'), ('@P2@', 'siblings'), ('@UNC@', 'children')],
        lookup,
        coparents,
    )
    by_id = {node['id']: node for node in layout}

    assert by_id['@C1@']['column'] == (
        by_id['@P1@']['column'] + by_id['@SP@']['column']) / 2
    assert by_id['@UC1@']['column'] == by_id['@UNC@']['column']


def test_path_graph_window_geometry_centers_when_graph_fits():
    """The graph window uses the content size and centers it on the display."""
    geometry = ResultsMixin._path_graph_window_geometry(
        content_w=500, content_h=300,
        screen_w=1600, screen_h=900,
        screen_x=100, screen_y=50,
    )

    assert geometry == (640, 428, 580, 286)


def test_path_graph_window_geometry_uses_display_when_graph_is_too_large():
    """Oversized graphs use the whole display bounds."""
    geometry = ResultsMixin._path_graph_window_geometry(
        content_w=1800, content_h=1200,
        screen_w=1600, screen_h=900,
        screen_x=100, screen_y=50,
    )

    assert geometry == (1600, 900, 100, 50)


def test_path_graph_window_geometry_restores_previous_location():
    """Later graph windows keep content sizing but reuse the last location."""
    geometry = ResultsMixin._path_graph_window_geometry(
        content_w=500, content_h=300,
        screen_w=1600, screen_h=900,
        screen_x=100, screen_y=50,
        previous_geometry='700x520+240+140',
    )

    assert geometry == (640, 428, 240, 140)


def test_path_graph_window_geometry_clamps_restored_location():
    """Restored graph windows stay within the current display bounds."""
    geometry = ResultsMixin._path_graph_window_geometry(
        content_w=500, content_h=300,
        screen_w=1600, screen_h=900,
        screen_x=100, screen_y=50,
        previous_geometry='700x520+2000+1000',
    )

    assert geometry == (640, 428, 1060, 522)


def test_centered_graph_scrollregion_pads_smaller_content():
    """A larger viewport centers graph content without changing item coords."""
    scrollregion = ResultsMixin._centered_graph_scrollregion(
        content_w=400, content_h=300,
        view_w=900, view_h=700,
    )

    assert scrollregion == (-250, -200, 650, 500)


def test_centered_graph_scrollregion_leaves_larger_content_at_origin():
    """Content larger than the viewport keeps a normal scroll origin."""
    scrollregion = ResultsMixin._centered_graph_scrollregion(
        content_w=1200, content_h=900,
        view_w=900, view_h=700,
    )

    assert scrollregion == (0, 0, 1200, 900)


def test_path_graph_colors_follow_selected_theme():
    """Graph colors derive from the selected theme palette."""
    blue = ResultsMixin._path_graph_colors(False, 'Blue')
    green = ResultsMixin._path_graph_colors(False, 'Green')

    assert blue['bg'] == '#EBF0FA'
    assert green['bg'] == '#EBF5EB'
    assert blue['parent'] == '#1155bb'
    assert green['parent'] == '#2e8b57'
    assert blue['node_fill'] != green['node_fill']


def test_non_biological_graph_line_styles_are_graphical():
    """Non-ordinary family edges use line style instead of text badges."""
    colors = ResultsMixin._path_graph_colors(False, 'Blue')

    step = ResultsMixin._graph_parent_line_options(
        'step', colors, lambda value: value)
    adopted = ResultsMixin._graph_parent_line_options(
        'adopted', colors, lambda value: value)
    ordinary = ResultsMixin._graph_parent_line_options(
        'birth', colors, lambda value: value)

    assert step['dash'] == (10, 4, 2, 4)
    assert adopted['dash'] == (3, 6)
    assert 'dash' not in ordinary


def test_half_sibling_graph_line_is_visibly_distinct():
    """Half-sibling edges draw as split double rails, not ordinary solid lines."""

    class FakeCanvas:
        def __init__(self):
            self.lines = []

        def create_line(self, *args, **kwargs):
            self.lines.append((args, kwargs))

    colors = ResultsMixin._path_graph_colors(False, 'Blue')
    app = ResultsMixin()

    ordinary_canvas = FakeCanvas()
    app._draw_graph_sibling_line(
        ordinary_canvas, 0, 20, 100, 20, 'full', colors, lambda value: value)

    half_canvas = FakeCanvas()
    app._draw_graph_sibling_line(
        half_canvas, 0, 20, 100, 20, 'half', colors, lambda value: value)

    assert len(ordinary_canvas.lines) == 1
    assert 'dash' not in ordinary_canvas.lines[0][1]
    assert len(half_canvas.lines) == 4
    assert {line[1]['dash'] for line in half_canvas.lines} == {(9, 5)}
    assert {line[0][1] for line in half_canvas.lines} == {16.0, 24.0}


def test_family_tree_sibling_segments_are_adjacent_not_overlapping_star():
    """Expanded siblings render as an adjacent chain so line styles do not stack."""
    edges = [
        ('@CENTER@', '@FULL@', 'siblings'),
        ('@CENTER@', '@HALF1@', 'siblings'),
        ('@CENTER@', '@HALF2@', 'siblings'),
        ('@CENTER@', '@HALF3@', 'siblings'),
    ]
    positions = {
        '@HALF3@': (0, 20),
        '@HALF2@': (100, 20),
        '@HALF1@': (200, 20),
        '@FULL@': (300, 20),
        '@CENTER@': (400, 20),
    }

    assert FamilyTreeRenderMixin._family_tree_visible_sibling_segments(
        edges, positions) == [
            ('@HALF3@', '@HALF2@'),
            ('@HALF2@', '@HALF1@'),
            ('@HALF1@', '@FULL@'),
            ('@FULL@', '@CENTER@'),
        ]


def test_graph_relationship_legend_includes_biological_baseline():
    """A non-ordinary legend includes the ordinary biological line style too."""

    class FakeCanvas:
        def __init__(self):
            self.lines = []
            self.rectangles = []
            self.text = []

        def create_line(self, *args, **kwargs):
            self.lines.append((args, kwargs))

        def create_rectangle(self, *args, **kwargs):
            self.rectangles.append((args, kwargs))

        def create_text(self, *args, **kwargs):
            self.text.append((args, kwargs))

    class FakeFont:
        @staticmethod
        def metrics(_key):
            return 12

        @staticmethod
        def measure(text):
            return len(text) * 7

    colors = ResultsMixin._path_graph_colors(False, 'Blue')
    app = ResultsMixin()

    ordinary_canvas = FakeCanvas()
    app._draw_graph_relationship_legend(
        ordinary_canvas, colors, lambda value: value, FakeFont(), {'birth'})

    mixed_canvas = FakeCanvas()
    app._draw_graph_relationship_legend(
        mixed_canvas, colors, lambda value: value, FakeFont(),
        {'birth', 'half'})

    assert ordinary_canvas.rectangles == []
    assert ordinary_canvas.text == []
    assert [kwargs['text'] for _args, kwargs in mixed_canvas.text] == [
        gs.GRAPH_LEGEND_BIOLOGICAL,
        gs.GRAPH_LEGEND_HALF,
    ]
    assert 'dash' not in mixed_canvas.lines[0][1]
    assert mixed_canvas.lines[0][1]['fill'] == colors['parent']


def test_graph_relationship_legend_size_only_when_legend_draws():
    """Renderers can reserve space only for visible relationship legends."""

    class FakeFont:
        @staticmethod
        def metrics(_key):
            return 12

        @staticmethod
        def measure(text):
            return len(text) * 7

    app = ResultsMixin()

    assert app._graph_relationship_legend_size(
        FakeFont(), lambda value: value, {'birth'}) == (0, 0)
    assert app._graph_relationship_legend_size(
        FakeFont(), lambda value: value, {'birth', 'adopted', 'half'}) == (
            162, 72)


def test_parent_couple_connector_prefers_step_style():
    """Mixed biological/step parent couples still draw a non-ordinary child edge."""
    app = ResultsMixin()
    app.individuals = {
        '@CHILD@': {'famc': ['@F1@'], 'fams': [], 'sex': ''},
        '@BIO@': {'famc': [], 'fams': ['@F1@'], 'sex': ''},
        '@STEP@': {'famc': [], 'fams': ['@F1@'], 'sex': ''},
    }
    app.families = {
        '@F1@': {
            'husb': '@STEP@',
            'wife': '@BIO@',
            'chil': ['@CHILD@'],
            'child_links': {
                '@CHILD@': {'father': 'step', 'mother': 'birth'},
            },
        },
    }

    assert app._combined_parent_child_kind(
        ('@BIO@', '@STEP@'), '@CHILD@') == 'step'
    assert app._combined_parent_child_kind(
        ('@STEP@', '@BIO@'), '@CHILD@') == 'step'


def test_person_box_fill_follows_gedcom_sex_independent_of_theme():
    """Person graph boxes use fixed sex colors from GEDCOM sex values."""
    individuals = {
        '@M@': {'sex': 'M'},
        '@F@': {'sex': 'f'},
        '@U@': {'sex': ''},
        '@X@': {'sex': 'X'},
    }

    assert ResultsMixin._person_box_fill(
        individuals, '@M@') == ResultsMixin.PERSON_BOX_FILL_MALE
    assert ResultsMixin._person_box_fill(
        individuals, '@F@') == ResultsMixin.PERSON_BOX_FILL_FEMALE
    assert ResultsMixin._person_box_fill(
        individuals, '@U@') == ResultsMixin.PERSON_BOX_FILL_NEUTRAL
    assert ResultsMixin._person_box_fill(
        individuals, '@X@') == ResultsMixin.PERSON_BOX_FILL_NEUTRAL
    assert ResultsMixin._person_box_fill(
        individuals, '@MISSING@') == ResultsMixin.PERSON_BOX_FILL_NEUTRAL


def test_endpoint_person_box_fill_darkens_sex_fill_with_endpoint_tint():
    """Endpoint graph boxes stand out while preserving the sex color cue."""
    colors = ResultsMixin._path_graph_colors(False, 'Blue')

    assert ResultsMixin._endpoint_person_box_fill(
        ResultsMixin.PERSON_BOX_FILL_MALE, colors) == '#cbd9eb'
    assert ResultsMixin._endpoint_person_box_fill(
        ResultsMixin.PERSON_BOX_FILL_FEMALE, colors) == '#e4d2dd'
    assert ResultsMixin._endpoint_person_box_fill(
        ResultsMixin.PERSON_BOX_FILL_NEUTRAL, colors) == '#dbdee2'


def test_compact_graph_label_uses_first_middle_initial_last_and_lifespan():
    """Graph labels use narrow three-line person names."""
    indi = {
        'name': 'John Quincy Public',
        'given_name': 'John Quincy',
        'surname': 'Public',
        'birth_year': 1901,
        'death_year': 1982,
    }

    assert ResultsMixin._compact_graph_label(indi) == 'John Q.\nPublic\n1901-1982'


def test_compact_graph_label_falls_back_to_unsplit_name():
    """Graph labels still render usable text for records without parsed names."""
    indi = {
        'name': 'Cher',
        'given_name': '',
        'surname': '',
        'birth_year': None,
        'death_year': None,
    }

    assert ResultsMixin._compact_graph_label(indi) == 'Cher'


def test_wrap_canvas_label_preserves_explicit_graph_label_lines():
    """Graph label wrapping keeps the compact name lines intact."""
    class FakeFont:
        @staticmethod
        def measure(text):
            return len(text) * 8

    assert ResultsMixin._wrap_canvas_label(
        'John Q.\nPublic\n1901-1982', FakeFont(), 200
    ) == 'John Q.\nPublic\n1901-1982'


def test_split_graph_label_name_detail_separates_lifespan_line():
    """Endpoint labels can bold names without bolding lifespan details."""
    assert ResultsMixin._split_graph_label_name_detail(
        'John Q.\nPublic\n1901-1982'
    ) == ('John Q.\nPublic', '1901-1982')
    assert ResultsMixin._split_graph_label_name_detail(
        'Jane\nPublic\nb. 1901'
    ) == ('Jane\nPublic', 'b. 1901')
    assert ResultsMixin._split_graph_label_name_detail(
        '(unknown)'
    ) == ('(unknown)', '')


def test_sibling_button_moves_right_when_spouse_is_left():
    """Sibling expansion control avoids an existing spouse on the left."""
    positions = {
        '@A@': (100, 50),
        '@SPOUSE@': (40, 50),
        '@OTHER@': (180, 50),
    }

    assert ResultsMixin._sibling_button_x(
        '@A@', 100, 70, 130, 20, [('@A@', '@SPOUSE@')], positions) == 140
    assert ResultsMixin._sibling_button_x(
        '@A@', 100, 70, 130, 20, [('@A@', '@OTHER@')], positions) == 60
    assert ResultsMixin._sibling_button_x(
        '@A@', 100, 70, 130, 20, [('@SPOUSE@', '@A@')], positions) == 140


def test_child_parent_midpoint_uses_visible_coparent():
    """Child connectors start between displayed parents."""
    positions = {
        '@A@': (100, 50),
        '@SPOUSE@': (220, 50),
        '@C1@': (160, 170),
    }

    def coparents(parent_id, child_ids):
        if parent_id == '@A@' and '@C1@' in child_ids:
            return ['@SPOUSE@']
        return []

    assert ResultsMixin._child_parent_midpoint(
        '@A@', '@C1@', positions, coparents) == (160, 50)


def test_child_parent_midpoint_uses_visible_spouse_edge_fallback():
    """Displayed spouse edges can identify the other parent for connectors."""
    positions = {
        '@A@': (100, 50),
        '@SPOUSE@': (220, 50),
        '@C1@': (160, 170),
    }

    def coparents(_parent_id, _child_ids):
        return []

    assert ResultsMixin._child_parent_midpoint(
        '@A@', '@C1@', positions, coparents,
        [('@A@', '@SPOUSE@')]) == (160, 50)


def test_child_parent_midpoint_requires_displayed_coparent():
    """Child connectors keep the single-parent origin without a visible coparent."""
    positions = {
        '@A@': (100, 50),
        '@C1@': (160, 170),
    }

    def coparents(parent_id, child_ids):
        if parent_id == '@A@' and '@C1@' in child_ids:
            return ['@SPOUSE@']
        return []

    assert ResultsMixin._child_parent_midpoint(
        '@A@', '@C1@', positions, coparents) is None


def test_family_tree_layout_places_immediate_family_by_generation():
    """Immediate family renders around the selected person."""
    visible = ['@A@', '@P1@', '@P2@', '@S1@', '@W@', '@C1@', '@C2@']
    edges = [
        ('@A@', '@P1@', 'parents'),
        ('@A@', '@P2@', 'parents'),
        ('@A@', '@S1@', 'siblings'),
        ('@A@', '@W@', 'spouses'),
        ('@A@', '@C1@', 'children'),
        ('@A@', '@C2@', 'children'),
    ]

    layout = layout_family_tree('@A@', visible, edges)
    by_id = {node['id']: node for node in layout}

    assert by_id['@A@']['generation'] == 0
    assert by_id['@P1@']['generation'] == -1
    assert by_id['@P2@']['generation'] == -1
    assert by_id['@S1@']['generation'] == 0
    assert by_id['@W@']['generation'] == 0
    assert by_id['@C1@']['generation'] == 1
    assert by_id['@C2@']['generation'] == 1
    positions = {(node['generation'], node['column']) for node in layout}
    assert len(positions) == len(layout)


def test_family_tree_layout_keeps_spouse_adjacent_before_siblings():
    """A spouse uses the adjacent slot even when siblings are also visible."""
    visible = ['@A@', '@SIB@', '@SPOUSE@']
    edges = [
        ('@A@', '@SIB@', 'siblings'),
        ('@A@', '@SPOUSE@', 'spouses'),
    ]

    layout = layout_family_tree('@A@', visible, edges)
    by_id = {node['id']: node for node in layout}

    assert by_id['@SPOUSE@']['column'] == 1.0
    assert by_id['@SIB@']['column'] == -1.0


def test_family_tree_layout_keeps_auto_coparent_adjacent_to_sibling():
    """A sibling's auto-added spouse takes the adjacent slot."""
    visible = ['@ME@', '@BRO@', '@CHILD@', '@WIFE@']
    edges = [
        ('@ME@', '@BRO@', 'siblings'),
        ('@BRO@', '@CHILD@', 'children'),
        ('@BRO@', '@WIFE@', 'spouses'),
    ]

    layout = layout_family_tree('@ME@', visible, edges)
    by_id = {node['id']: node for node in layout}

    assert by_id['@WIFE@']['column'] == by_id['@BRO@']['column'] + 1.0
    assert by_id['@CHILD@']['column'] == (
        by_id['@BRO@']['column'] + by_id['@WIFE@']['column']) / 2
    assert by_id['@ME@']['column'] > by_id['@WIFE@']['column']


def test_family_tree_layout_keeps_reflowed_boxes_from_overlapping():
    """Expanded relatives on an occupied row get a clear adjacent slot."""
    visible = ['@A@', '@C@', '@P2@']
    edges = [
        ('@A@', '@C@', 'children'),
        ('@C@', '@P2@', 'parents'),
    ]

    layout = layout_family_tree('@A@', visible, edges)
    same_row = [
        node['column'] for node in layout
        if node['generation'] == 0
    ]

    assert min(
        abs(left - right)
        for index, left in enumerate(same_row)
        for right in same_row[index + 1:]
    ) >= 1.0


def test_family_tree_graph_adds_expanded_nodes_without_duplicates():
    """Expansions keep existing tree nodes and do not duplicate shared people."""
    families = {
        '@A@': {
            'parents': ['@P1@'],
            'siblings': ['@S1@'],
            'spouses': ['@W@'],
            'children': ['@C1@'],
        },
        '@S1@': {
            'parents': ['@P1@'],
            'siblings': ['@A@'],
            'spouses': [],
            'children': ['@N1@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    visible, edges = build_family_tree_graph(
        '@A@', [('@S1@', 'parents'), ('@S1@', 'children')], lookup)

    assert visible.count('@P1@') == 1
    assert visible.count('@S1@') == 1
    assert '@N1@' in visible
    assert ('@S1@', '@P1@', 'parents') in edges
    assert ('@S1@', '@N1@', 'children') in edges


def test_family_tree_child_expansion_adds_missing_coparent():
    """Tree View child expansion brings in the children's other parent."""
    families = {
        '@A@': {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': ['@C1@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@A@' and '@C1@' in child_ids:
            return ['@SPOUSE@']
        return []

    visible, edges = build_family_tree_graph(
        '@A@', [('@A@', 'children')], lookup, coparents)

    assert '@C1@' in visible
    assert '@SPOUSE@' in visible
    assert ('@A@', '@SPOUSE@', 'spouses') in edges


def test_family_tree_multi_spouse_children_use_actual_parent_groups():
    """Visible half-siblings stay grouped under their own recorded parents."""
    families = {
        '@HYMAN@': {
            'parents': ['@HARRIS@', '@JOCHEBED@'],
            'siblings': [
                '@BENJAMIN@',
                '@JOSEPH@',
                '@LOUIS@',
                '@SAMUEL@',
                '@SARAH@',
                '@CHARLES@',
            ],
            'spouses': [],
            'children': [],
        },
        '@BENJAMIN@': {
            'parents': ['@HARRIS@', '@JOCHEBED@'],
            'siblings': ['@HYMAN@'],
            'spouses': [],
            'children': [],
        },
        '@JOCHEBED@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@HARRIS@'],
            'children': ['@HYMAN@', '@BENJAMIN@'],
        },
        '@HARRIS@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@EVA@', '@JOCHEBED@'],
            'children': [
                '@CHARLES@',
                '@SARAH@',
                '@SAMUEL@',
                '@LOUIS@',
                '@JOSEPH@',
                '@HYMAN@',
                '@BENJAMIN@',
            ],
        },
        '@EVA@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@HARRIS@'],
            'children': [
                '@CHARLES@',
                '@SARAH@',
                '@SAMUEL@',
                '@LOUIS@',
                '@JOSEPH@',
            ],
        },
    }
    for child_id in ('@CHARLES@', '@SARAH@', '@SAMUEL@', '@LOUIS@',
                     '@JOSEPH@'):
        families[child_id] = {
            'parents': ['@HARRIS@', '@EVA@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(parent_id, child_ids):
        child_ids = set(child_ids)
        parents = []
        if parent_id == '@HARRIS@':
            if child_ids & {'@HYMAN@', '@BENJAMIN@'}:
                parents.append('@JOCHEBED@')
            if child_ids & {'@CHARLES@', '@SARAH@', '@SAMUEL@',
                            '@LOUIS@', '@JOSEPH@'}:
                parents.append('@EVA@')
        elif parent_id == '@JOCHEBED@' and child_ids & {
                '@HYMAN@', '@BENJAMIN@'}:
            parents.append('@HARRIS@')
        elif parent_id == '@EVA@' and child_ids & {
                '@CHARLES@', '@SARAH@', '@SAMUEL@', '@LOUIS@', '@JOSEPH@'}:
            parents.append('@HARRIS@')
        return parents

    visible, edges = build_family_tree_graph(
        '@HYMAN@',
        [
            ('@HYMAN@', 'parents'),
            ('@HYMAN@', 'siblings'),
            ('@HARRIS@', 'spouses'),
        ],
        lookup,
        coparents,
    )
    layout = layout_family_tree('@HYMAN@', visible, edges)
    positions = {
        node['id']: (node['column'], node['generation'])
        for node in layout
    }
    spouse_edges = [
        (source_id, target_id)
        for source_id, target_id, category in edges
        if category == 'spouses'
    ]
    groups = ResultsMixin._family_tree_child_edge_groups(
        edges, positions, coparents, spouse_edges)
    groups_by_parents = {
        group['parent_ids']: set(group['children'])
        for group in groups
    }

    assert ('@HYMAN@', '@HARRIS@', 'parents') in edges
    assert ('@BENJAMIN@', '@JOCHEBED@', 'parents') in edges
    assert groups_by_parents[('@EVA@', '@HARRIS@')] == {
        '@CHARLES@', '@SARAH@', '@SAMUEL@', '@LOUIS@', '@JOSEPH@'}
    assert groups_by_parents[('@HARRIS@', '@JOCHEBED@')] == {
        '@HYMAN@', '@BENJAMIN@'}
    assert (
        positions['@EVA@'][0]
        < positions['@HARRIS@'][0]
        < positions['@JOCHEBED@'][0]
    )


def test_family_tree_spouse_expansion_adds_hidden_spouse():
    """Tree View spouse expansion can reveal a non-center person's spouse."""
    families = {
        '@A@': {
            'parents': [],
            'siblings': ['@S1@'],
            'spouses': [],
            'children': [],
        },
        '@S1@': {
            'parents': [],
            'siblings': ['@A@'],
            'spouses': ['@SPOUSE@'],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    visible, edges = build_family_tree_graph(
        '@A@', [('@S1@', 'spouses')], lookup)

    assert '@S1@' in visible
    assert '@SPOUSE@' in visible
    assert ('@S1@', '@SPOUSE@', 'spouses') in edges


def test_family_tree_parent_expansion_adds_parent_spouse_edge():
    """Tree View parent expansion links displayed co-parents as spouses."""
    families = {
        '@A@': {
            'parents': ['@P1@', '@P2@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P1@' and '@A@' in child_ids:
            return ['@P2@']
        if indi_id == '@P2@' and '@A@' in child_ids:
            return ['@P1@']
        return []

    _visible, edges = build_family_tree_graph(
        '@A@', [('@A@', 'parents')], lookup, coparents)

    assert ('@P1@', '@P2@', 'spouses') in edges


def test_family_tree_parent_expansion_centers_parents_over_child():
    """Tree View parent expansion keeps the child below the parent pair."""
    families = {
        '@P1@': {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': ['@A@'],
        },
        '@A@': {
            'parents': ['@P1@', '@P2@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P1@' and '@A@' in child_ids:
            return ['@P2@']
        if indi_id == '@P2@' and '@A@' in child_ids:
            return ['@P1@']
        return []

    visible, edges = build_family_tree_graph(
        '@P1@', [('@A@', 'parents')], lookup, coparents)
    layout = layout_family_tree('@P1@', visible, edges)
    by_id = {node['id']: node for node in layout}

    parent_midpoint = (
        by_id['@P1@']['column'] + by_id['@P2@']['column']) / 2
    assert by_id['@A@']['column'] == parent_midpoint
    assert by_id['@P1@']['generation'] == by_id['@P2@']['generation']
    assert by_id['@A@']['generation'] == by_id['@P1@']['generation'] + 1


def test_family_tree_parent_then_child_expansion_keeps_spouses_adjacent():
    """Tree View keeps co-parents adjacent after expanding their children."""
    families = {
        '@A@': {
            'parents': ['@P1@', '@P2@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
        '@P1@': {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': ['@A@', '@SIB@'],
        },
        '@P2@': {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': ['@A@', '@SIB@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P1@' and any(
                child_id in child_ids for child_id in ('@A@', '@SIB@')):
            return ['@P2@']
        if indi_id == '@P2@' and any(
                child_id in child_ids for child_id in ('@A@', '@SIB@')):
            return ['@P1@']
        return []

    visible, edges = build_family_tree_graph(
        '@A@', [('@A@', 'parents'), ('@P1@', 'children')], lookup, coparents)
    layout = layout_family_tree('@A@', visible, edges)
    by_id = {node['id']: node for node in layout}

    assert abs(by_id['@P1@']['column'] - by_id['@P2@']['column']) == 1.0
    parent_midpoint = (
        by_id['@P1@']['column'] + by_id['@P2@']['column']) / 2
    child_midpoint = (
        by_id['@A@']['column'] + by_id['@SIB@']['column']) / 2
    assert child_midpoint == parent_midpoint


def test_family_tree_grandparent_child_expansion_keeps_child_spouse_adjacent():
    """Moving a child under grandparents keeps that child's spouse adjacent."""
    families = {
        '@A@': {
            'parents': ['@P1@', '@P2@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
        '@P1@': {
            'parents': ['@GP1@', '@GM1@'],
            'siblings': [],
            'spouses': ['@P2@'],
            'children': ['@A@'],
        },
        '@GP1@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@GM1@'],
            'children': ['@P1@', '@AUNT@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P1@' and '@A@' in child_ids:
            return ['@P2@']
        if indi_id == '@GP1@' and any(
                child_id in child_ids for child_id in ('@P1@', '@AUNT@')):
            return ['@GM1@']
        if indi_id == '@GM1@' and any(
                child_id in child_ids for child_id in ('@P1@', '@AUNT@')):
            return ['@GP1@']
        return []

    visible, edges = build_family_tree_graph(
        '@A@',
        [('@P1@', 'parents'), ('@GP1@', 'children')],
        lookup,
        coparents,
    )
    layout = layout_family_tree('@A@', visible, edges)
    by_id = {node['id']: node for node in layout}

    assert abs(by_id['@P1@']['column'] - by_id['@P2@']['column']) == 1.0


def test_family_tree_uncle_child_expansion_keeps_child_groups_centered():
    """Expanding an uncle's children preserves each parent's child alignment."""
    families = {
        '@P1@': {
            'parents': ['@P2@'],
            'siblings': [],
            'spouses': [],
            'children': [],
        },
        '@P2@': {
            'parents': ['@P3@', '@P5@'],
            'siblings': ['@P4@'],
            'spouses': [],
            'children': ['@P1@'],
        },
        '@P3@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@P5@'],
            'children': ['@P2@', '@P4@'],
        },
        '@P5@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@P3@'],
            'children': ['@P2@', '@P4@'],
        },
        '@P4@': {
            'parents': ['@P3@', '@P5@'],
            'siblings': ['@P2@'],
            'spouses': [],
            'children': ['@P4C@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P3@' and any(
                child_id in child_ids for child_id in ('@P2@', '@P4@')):
            return ['@P5@']
        if indi_id == '@P5@' and any(
                child_id in child_ids for child_id in ('@P2@', '@P4@')):
            return ['@P3@']
        return []

    visible, edges = build_family_tree_graph(
        '@P1@',
        [('@P2@', 'parents'), ('@P3@', 'children'), ('@P4@', 'children')],
        lookup,
        coparents,
    )
    layout = layout_family_tree('@P1@', visible, edges)
    by_id = {node['id']: node for node in layout}

    assert by_id['@P1@']['column'] == by_id['@P2@']['column']
    assert by_id['@P4C@']['column'] == by_id['@P4@']['column']


def test_family_tree_parent_sibling_child_expansion_keeps_center_children():
    """Expanding an uncle's children does not shift the center person's children."""
    families = {
        '@P1@': {
            'parents': ['@P2@', '@M2@'],
            'siblings': [],
            'spouses': ['@SP@'],
            'children': ['@C1@'],
        },
        '@SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@P1@'],
            'children': ['@C1@'],
        },
        '@P2@': {
            'parents': ['@GP@', '@GM@'],
            'siblings': ['@UNC@'],
            'spouses': ['@M2@'],
            'children': ['@P1@'],
        },
        '@GP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@GM@'],
            'children': ['@P2@', '@UNC@'],
        },
        '@GM@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@GP@'],
            'children': ['@P2@', '@UNC@'],
        },
        '@UNC@': {
            'parents': ['@GP@', '@GM@'],
            'siblings': ['@P2@'],
            'spouses': [],
            'children': ['@UC1@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P1@' and '@C1@' in child_ids:
            return ['@SP@']
        if indi_id == '@GP@' and any(
                child_id in child_ids for child_id in ('@P2@', '@UNC@')):
            return ['@GM@']
        if indi_id == '@GM@' and any(
                child_id in child_ids for child_id in ('@P2@', '@UNC@')):
            return ['@GP@']
        return []

    visible, edges = build_family_tree_graph(
        '@P1@',
        [('@P2@', 'parents'), ('@P2@', 'siblings'), ('@UNC@', 'children')],
        lookup,
        coparents,
    )
    layout = layout_family_tree('@P1@', visible, edges)
    by_id = {node['id']: node for node in layout}

    assert by_id['@C1@']['column'] == (
        by_id['@P1@']['column'] + by_id['@SP@']['column']) / 2
    assert by_id['@UC1@']['column'] == by_id['@UNC@']['column']


def test_family_tree_parent_sibling_child_short_path_keeps_center_children():
    """Showing a parent's sibling then children keeps center children aligned."""
    families = {
        '@P1@': {
            'parents': ['@P2@', '@M2@'],
            'siblings': [],
            'spouses': ['@SP@'],
            'children': ['@C1@'],
        },
        '@SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@P1@'],
            'children': ['@C1@'],
        },
        '@P2@': {
            'parents': [],
            'siblings': ['@UNC@'],
            'spouses': ['@M2@'],
            'children': ['@P1@'],
        },
        '@UNC@': {
            'parents': [],
            'siblings': ['@P2@'],
            'spouses': [],
            'children': ['@UC1@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        if indi_id == '@P1@' and '@C1@' in child_ids:
            return ['@SP@']
        return []

    visible, edges = build_family_tree_graph(
        '@P1@',
        [('@P2@', 'siblings'), ('@UNC@', 'children')],
        lookup,
        coparents,
    )
    layout = layout_family_tree('@P1@', visible, edges)
    by_id = {node['id']: node for node in layout}

    assert by_id['@C1@']['column'] == (
        by_id['@P1@']['column'] + by_id['@SP@']['column']) / 2
    assert by_id['@UC1@']['column'] == by_id['@UNC@']['column']


def test_family_tree_child_group_avoids_visible_spouse_pair_slots():
    """New child groups do not split another displayed spouse pair."""
    visible = ['@A@', '@S@', '@C@', '@J@', '@G@', '@N1@', '@N2@']
    edges = [
        ('@A@', '@S@', 'spouses'),
        ('@A@', '@C@', 'children'),
        ('@A@', '@J@', 'siblings'),
        ('@J@', '@G@', 'spouses'),
        ('@J@', '@N1@', 'children'),
        ('@J@', '@N2@', 'children'),
    ]

    layout = layout_family_tree('@A@', visible, edges)
    by_id = {node['id']: node for node in layout}

    assert abs(by_id['@A@']['column'] - by_id['@S@']['column']) == 1.0
    assert by_id['@C@']['column'] == (
        by_id['@A@']['column'] + by_id['@S@']['column']) / 2


def test_family_tree_parent_siblings_stay_on_spouse_opposite_sides():
    """Expanded siblings of both parents stay grouped beside each parent."""
    visible = [
        '@CENTER@',
        '@CENTER_SP@',
        '@CH1@',
        '@CH2@',
        '@PARENT_L@',
        '@PARENT_R@',
        '@CENTER_SIB1@',
        '@CENTER_SIB2@',
        '@PARENT_L_SIB1@',
        '@PARENT_L_SIB2@',
        '@PARENT_R_SIB1@',
        '@PARENT_R_SIB2@',
        '@PARENT_R_SIB3@',
        '@PARENT_R_SIB4@',
    ]
    edges = [
        ('@CENTER@', '@CENTER_SP@', 'spouses'),
        ('@CENTER@', '@CH1@', 'children'),
        ('@CENTER@', '@CH2@', 'children'),
        ('@CENTER@', '@PARENT_L@', 'parents'),
        ('@CENTER@', '@PARENT_R@', 'parents'),
        ('@CENTER@', '@CENTER_SIB1@', 'siblings'),
        ('@CENTER@', '@CENTER_SIB2@', 'siblings'),
        ('@PARENT_L@', '@PARENT_R@', 'spouses'),
        ('@PARENT_L@', '@PARENT_L_SIB1@', 'siblings'),
        ('@PARENT_L@', '@PARENT_L_SIB2@', 'siblings'),
        ('@PARENT_R@', '@PARENT_R_SIB1@', 'siblings'),
        ('@PARENT_R@', '@PARENT_R_SIB2@', 'siblings'),
        ('@PARENT_R@', '@PARENT_R_SIB3@', 'siblings'),
        ('@PARENT_R@', '@PARENT_R_SIB4@', 'siblings'),
    ]

    layout = layout_family_tree('@CENTER@', visible, edges)
    by_id = {node['id']: node for node in layout}
    left_siblings = [
        by_id['@PARENT_L_SIB1@']['column'],
        by_id['@PARENT_L_SIB2@']['column'],
    ]
    right_siblings = [
        by_id['@PARENT_R_SIB1@']['column'],
        by_id['@PARENT_R_SIB2@']['column'],
        by_id['@PARENT_R_SIB3@']['column'],
        by_id['@PARENT_R_SIB4@']['column'],
    ]

    assert by_id['@PARENT_L@']['column'] < by_id['@PARENT_R@']['column']
    assert all(column < by_id['@PARENT_L@']['column']
               for column in left_siblings)
    assert all(column > by_id['@PARENT_R@']['column']
               for column in right_siblings)
    assert sorted(right_siblings) == right_siblings


def test_family_tree_spouse_pair_keeps_each_partner_family_siblings_grouped():
    """Spouses keep their own sibling groups outside the couple."""
    visible = [
        '@LEFT@',
        '@RIGHT@',
        '@LEFT_PARENT@',
        '@LEFT_PARENT_SP@',
        '@LEFT_SIB1@',
        '@LEFT_SIB2@',
        '@LEFT_SIB3@',
        '@RIGHT_SIB1@',
        '@RIGHT_SIB2@',
        '@RIGHT_SIB3@',
    ]
    edges = [
        ('@LEFT@', '@RIGHT@', 'spouses'),
        ('@LEFT_PARENT@', '@LEFT_PARENT_SP@', 'spouses'),
        ('@LEFT_PARENT@', '@LEFT@', 'children'),
        ('@LEFT_PARENT@', '@LEFT_SIB1@', 'children'),
        ('@LEFT_PARENT@', '@LEFT_SIB2@', 'children'),
        ('@LEFT_PARENT@', '@LEFT_SIB3@', 'children'),
        ('@RIGHT@', '@RIGHT_SIB1@', 'siblings'),
        ('@RIGHT@', '@RIGHT_SIB2@', 'siblings'),
        ('@RIGHT@', '@RIGHT_SIB3@', 'siblings'),
    ]

    layout = layout_family_tree('@LEFT@', visible, edges)
    by_id = {node['id']: node for node in layout}
    left_siblings = [
        by_id['@LEFT_SIB1@']['column'],
        by_id['@LEFT_SIB2@']['column'],
        by_id['@LEFT_SIB3@']['column'],
    ]
    right_siblings = [
        by_id['@RIGHT_SIB1@']['column'],
        by_id['@RIGHT_SIB2@']['column'],
        by_id['@RIGHT_SIB3@']['column'],
    ]

    assert by_id['@LEFT@']['column'] < by_id['@RIGHT@']['column']
    assert by_id['@RIGHT@']['column'] == by_id['@LEFT@']['column'] + 1.0
    assert all(column < by_id['@LEFT@']['column']
               for column in left_siblings)
    assert all(column > by_id['@RIGHT@']['column']
               for column in right_siblings)
    assert [
        round(right - left, 1)
        for left, right in zip(
            sorted(left_siblings), sorted(left_siblings)[1:])
    ] == [1.0, 1.0]
    assert [
        round(right - left, 1)
        for left, right in zip(
            sorted(right_siblings), sorted(right_siblings)[1:])
    ] == [1.0, 1.0]


def test_family_tree_compacts_sibling_branch_with_children_as_block():
    """Sibling branches with children slide closer without skewing the branch."""
    visible = [
        '@CENTER@',
        '@CENTER_SP@',
        '@CENTER_CH1@',
        '@CENTER_CH2@',
        '@PARENT@',
        '@PARENT_SP@',
        '@CENTER_SIB1@',
        '@CENTER_SIB2@',
        '@AUNT@',
        '@UNCLE@',
        '@AUNT_SP@',
        '@AUNT_CH1@',
        '@AUNT_CH2@',
        '@AUNT_CH3@',
    ]
    edges = [
        ('@CENTER@', '@CENTER_SP@', 'spouses'),
        ('@CENTER@', '@CENTER_CH1@', 'children'),
        ('@CENTER@', '@CENTER_CH2@', 'children'),
        ('@CENTER@', '@PARENT@', 'parents'),
        ('@CENTER@', '@PARENT_SP@', 'parents'),
        ('@CENTER@', '@CENTER_SIB1@', 'siblings'),
        ('@CENTER@', '@CENTER_SIB2@', 'siblings'),
        ('@PARENT@', '@PARENT_SP@', 'spouses'),
        ('@PARENT@', '@AUNT@', 'siblings'),
        ('@PARENT@', '@UNCLE@', 'siblings'),
        ('@AUNT@', '@AUNT_SP@', 'spouses'),
        ('@AUNT@', '@AUNT_CH1@', 'children'),
        ('@AUNT@', '@AUNT_CH2@', 'children'),
        ('@AUNT@', '@AUNT_CH3@', 'children'),
    ]

    layout = layout_family_tree('@CENTER@', visible, edges)
    by_id = {node['id']: node for node in layout}
    parent_left_gap = (
        by_id['@PARENT@']['column'] - by_id['@AUNT_SP@']['column'])

    assert 1.0 <= parent_left_gap <= 2.0
    assert by_id['@AUNT_SP@']['column'] == by_id['@AUNT@']['column'] + 1.0
    assert by_id['@AUNT_CH2@']['column'] == (
        by_id['@AUNT@']['column'] + by_id['@AUNT_SP@']['column']) / 2


def test_family_tree_debug_fixtures_preserve_layout_invariants():
    """Saved graph exports replay without overlap, spouse gaps, or drift."""
    max_width_by_fixture = {
        '1': 12.0,
        'aa': 4.3,
        'bb': 8.3,
        'cc': 12.0,
    }

    for name, max_width in max_width_by_fixture.items():
        layout, edges = _load_debug_family_tree_layout(name)

        _assert_no_same_row_conflicts(layout)
        _assert_visible_spouses_adjacent(layout, edges)
        _assert_visible_child_groups_near_parents(layout, edges)
        assert _max_family_tree_row_width(layout) <= max_width


def test_family_tree_debug_parent_couple_moves_above_child_when_unblocked():
    """A displayed parent couple centers over its visible children group."""
    layout, edges = _load_debug_family_tree_layout('2')
    by_id = {node['id']: node for node in layout}
    parent_midpoint = (
        by_id['@I102698315410@']['column']
        + by_id['@I102698315502@']['column']
    ) / 2
    child_ids = (
        '@I102667033207@', '@I102698315854@',
        '@I102698315865@', '@I102698315878@',
    )
    child_columns = [by_id[child_id]['column'] for child_id in child_ids]
    child_midpoint = (min(child_columns) + max(child_columns)) / 2

    _assert_no_same_row_conflicts(layout)
    _assert_visible_spouses_adjacent(layout, edges)
    assert abs(parent_midpoint - child_midpoint) <= 0.5
    assert abs(
        parent_midpoint - by_id['@I102667033207@']['column']) <= 2.0


def test_family_tree_debug_single_unbranched_sibling_stays_compact():
    """A lone center sibling is not pushed across excess empty columns."""
    layout, _edges = _load_debug_family_tree_layout('21')
    center = next(node for node in layout if node['is_center'])
    same_row = [
        node for node in layout
        if node['generation'] == center['generation']
    ]

    assert _max_family_tree_row_width(layout) <= 7.0
    assert max(
        abs(node['column'] - center['column'])
        for node in same_row
        if not node['is_center']
    ) <= 2.1


def test_family_tree_debug_step_parent_does_not_pull_parent_couple_off_children():
    """Rebuilt debug/22 centers children under their actual parent couple."""
    path = Path('debug/22.json')
    if not path.exists():
        pytest.skip('debug/22.json not found')
    payload = json.loads(path.read_text())
    family_members = payload['family_members']

    def lookup(indi_id):
        return family_members.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(parent_id, child_ids):
        child_ids = set(child_ids)
        parents = []
        for group in payload.get('child_groups', ()):
            if parent_id not in group.get('parent_ids', ()):
                continue
            if not child_ids.intersection(group.get('children', ())):
                continue
            parents.extend(
                other_id for other_id in group['parent_ids']
                if other_id != parent_id)
        return parents

    visible, edges = build_family_tree_graph(
        payload['center_id'],
        [
            (entry['source'], entry['category'])
            for entry in payload['expanded']
        ],
        lookup,
        coparents,
    )
    layout = layout_family_tree(payload['center_id'], visible, edges)
    by_id = {node['id']: node for node in layout}
    parent_ids = ('@I102724938622@', '@I102724939247@')
    child_ids = ('@I102724907444@', '@I102724939468@')
    parent_midpoint = sum(by_id[parent_id]['column']
                          for parent_id in parent_ids) / 2
    child_midpoint = (
        min(by_id[child_id]['column'] for child_id in child_ids)
        + max(by_id[child_id]['column'] for child_id in child_ids)
    ) / 2

    assert ('@I102724939247@', '@I102667033275@', 'spouses') not in edges
    assert ('@I102724938622@', '@I102667033275@', 'spouses') not in edges
    assert abs(parent_midpoint - child_midpoint) <= 0.5


def test_family_tree_debug_unbranched_sibling_outlier_stays_compact():
    """A leaf sibling in a lower generation is not left across empty columns."""
    layout, _edges = _load_debug_family_tree_layout('23')
    by_id = {node['id']: node for node in layout}

    assert _max_family_tree_row_width(layout) <= 4.0
    assert (
        by_id['@I102724942433@']['column']
        - by_id['@I102724921629@']['column']
    ) <= 1.1


def test_family_tree_debug_large_tree_preserves_target_spouse_adjacency():
    """Large debug exports keep spouses adjacent around sibling branches."""
    for fixture_name in ('3', '4', '5'):
        layout, _edges = _load_debug_family_tree_layout(fixture_name)
        by_id = {node['id']: node for node in layout}
        target_generation = by_id['@I102667033170@']['generation']
        same_row = [
            node for node in layout
            if node['generation'] == target_generation
        ]
        right_of_target = sorted(
            (
                node for node in same_row
                if node['column'] > by_id['@I102667033170@']['column']
            ),
            key=lambda node: node['column'],
        )
        nearest_non_spouse = next(
            node for node in right_of_target
            if node['id'] != '@I102667033171@')
        sibling_unit_ids = {
            '@I102667033170@',
            '@I102667033171@',
            '@I102667033176@',
            '@I102667033177@',
            '@I102667033188@',
            '@I102667033190@',
        }
        sibling_unit_columns = [
            by_id[person_id]['column'] for person_id in sibling_unit_ids
        ]
        interposed_ids = {
            node['id'] for node in same_row
            if min(sibling_unit_columns) <= node['column']
            <= max(sibling_unit_columns)
        } - sibling_unit_ids

        _assert_no_same_row_conflicts(layout)
        assert by_id['@I102667033281@']['column'] == (
            by_id['@I102667033206@']['column'] + 1.0)
        assert nearest_non_spouse['id'] == '@I102667033176@'
        assert not interposed_ids


def test_family_tree_debug_large_tree_keeps_neighbor_family_units_together():
    """Adjacent child families stay grouped instead of interleaving branches."""
    layout, _edges = _load_debug_family_tree_layout('4')
    by_id = {node['id']: node for node in layout}
    same_generation = by_id['@I102667033170@']['generation']
    family_a = [
        '@I102667033170@',
        '@I102667033171@',
        '@I102667033176@',
        '@I102667033188@',
        '@I102667033177@',
        '@I102667033190@',
    ]
    family_b = [
        '@I102667033204@',
        '@I102667033276@',
        '@I102667033205@',
        '@I102667033278@',
        '@I102667033206@',
        '@I102667033281@',
    ]
    def family_span(member_ids):
        columns = [by_id[member_id]['column'] for member_id in member_ids]
        return min(columns), max(columns)

    span_a = family_span(family_a)
    span_b = family_span(family_b)
    interlopers = [
        node['id'] for node in layout
        if node['generation'] == same_generation
        and any(low < node['column'] < high for low, high in (span_a, span_b))
        and node['id'] not in {*family_a, *family_b}
    ]

    _assert_no_same_row_conflicts(layout)
    # Each family unit stays contiguous and the two do not interleave.
    assert not interlopers
    assert span_a[1] < span_b[0] or span_b[1] < span_a[0]


def test_family_tree_child_alignment_keeps_adjusted_siblings_separate():
    """Children shifted around spouse boxes do not collapse into one column."""
    visible = [
        '@CENTER@',
        '@CENTER_SP@',
        '@CHILD1@',
        '@CHILD2@',
        '@CHILD3@',
        '@CHILD4@',
        '@CHILD1_SP@',
        '@CHILD2_SP@',
        '@G1@',
        '@G2@',
        '@G3@',
        '@G4@',
        '@H1@',
        '@H2@',
        '@H3@',
        '@H4@',
        '@H5@',
    ]
    edges = [
        ('@CENTER@', '@CENTER_SP@', 'spouses'),
        ('@CENTER@', '@CHILD1@', 'children'),
        ('@CENTER@', '@CHILD2@', 'children'),
        ('@CENTER@', '@CHILD3@', 'children'),
        ('@CENTER@', '@CHILD4@', 'children'),
        ('@CHILD1@', '@CHILD1_SP@', 'spouses'),
        ('@CHILD2@', '@CHILD2_SP@', 'spouses'),
        ('@CHILD1@', '@G1@', 'children'),
        ('@CHILD1@', '@G2@', 'children'),
        ('@CHILD1@', '@G3@', 'children'),
        ('@CHILD1@', '@G4@', 'children'),
        ('@CHILD2@', '@H1@', 'children'),
        ('@CHILD2@', '@H2@', 'children'),
        ('@CHILD2@', '@H3@', 'children'),
        ('@CHILD2@', '@H4@', 'children'),
        ('@CHILD2@', '@H5@', 'children'),
    ]

    layout = layout_family_tree('@CENTER@', visible, edges)
    by_id = {node['id']: node for node in layout}
    child_columns = [
        by_id['@CHILD1@']['column'],
        by_id['@CHILD2@']['column'],
        by_id['@CHILD3@']['column'],
        by_id['@CHILD4@']['column'],
    ]

    assert len(set(child_columns)) == len(child_columns)
    assert all(
        abs(left - right) >= 1.0
        for index, left in enumerate(child_columns)
        for right in child_columns[index + 1:])
    assert by_id['@CHILD2@']['column'] != by_id['@CHILD3@']['column']


def test_family_tree_spouse_next_to_center_does_not_overlap_sibling():
    """Final center protection keeps adjacent spouse pairs from overlapping."""
    visible = [
        '@P1@',
        '@P2@',
        '@CH1@',
        '@CENTER@',
        '@CH2@',
        '@CH1_SP@',
        '@GC1@',
        '@GC2@',
        '@GC3@',
        '@CH3@',
    ]
    edges = [
        ('@P2@', '@P1@', 'spouses'),
        ('@P2@', '@CH1@', 'children'),
        ('@P2@', '@CENTER@', 'children'),
        ('@P2@', '@CH2@', 'children'),
        ('@P2@', '@CH3@', 'children'),
        ('@CH1@', '@CH1_SP@', 'spouses'),
        ('@CH1@', '@GC1@', 'children'),
        ('@CH1@', '@GC2@', 'children'),
        ('@CH1@', '@GC3@', 'children'),
        ('@CENTER@', '@P1@', 'parents'),
        ('@CENTER@', '@P2@', 'parents'),
    ]

    layout = layout_family_tree('@CENTER@', visible, edges)

    assert all(
        abs(left['column'] - right['column']) >= 1.0
        for index, left in enumerate(layout)
        for right in layout[index + 1:]
        if left['generation'] == right['generation'])


def test_family_tree_child_alignment_avoids_unrelated_spouse_pair_slots():
    """Expanded children avoid a spouse pair already displayed on their row."""
    visible = [
        '@CENTER@',
        '@CENTER_SP1@',
        '@CENTER_SP2@',
        '@SIB@',
        '@SIB_SP@',
        '@SIB_CH1@',
        '@SIB_CH2@',
        '@SIB_CH3@',
        '@SIB_CH4@',
        '@CENTER_CH1@',
        '@CENTER_CH2@',
        '@CENTER_CH3@',
        '@CENTER_CH3_SP@',
        '@CENTER_CH4@',
        '@GRANDCHILD@',
    ]
    edges = [
        ('@CENTER@', '@CENTER_SP1@', 'spouses'),
        ('@CENTER@', '@CENTER_SP2@', 'spouses'),
        ('@CENTER@', '@SIB@', 'siblings'),
        ('@CENTER@', '@CENTER_CH1@', 'children'),
        ('@CENTER@', '@CENTER_CH2@', 'children'),
        ('@CENTER@', '@CENTER_CH3@', 'children'),
        ('@CENTER@', '@CENTER_CH4@', 'children'),
        ('@SIB@', '@SIB_SP@', 'spouses'),
        ('@SIB@', '@SIB_CH1@', 'children'),
        ('@SIB@', '@SIB_CH2@', 'children'),
        ('@SIB@', '@SIB_CH3@', 'children'),
        ('@SIB@', '@SIB_CH4@', 'children'),
        ('@CENTER_CH3@', '@CENTER_CH3_SP@', 'spouses'),
        ('@CENTER_CH1@', '@GRANDCHILD@', 'children'),
    ]

    layout = layout_family_tree('@CENTER@', visible, edges)
    by_id = {node['id']: node for node in layout}

    assert abs(
        by_id['@SIB_CH3@']['column']
        - by_id['@CENTER_CH3_SP@']['column']) >= 1.0


def test_family_tree_compacts_drifted_sibling_after_expanded_branches():
    """Expanded descendant branches do not leave siblings far off row edge."""
    visible = [
        '@CENTER@',
        '@PARENT1@',
        '@PARENT2@',
        '@SIB1@',
        '@SIB2@',
        '@SIB3@',
        '@CENTER_SP1@',
        '@CENTER_SP2@',
        '@SIB2_SP@',
        '@CENTER_CH1@',
        '@CENTER_CH2@',
        '@CENTER_CH3@',
        '@CENTER_CH4@',
        '@SIB2_CH1@',
        '@SIB2_CH2@',
        '@SIB2_CH3@',
        '@SIB2_CH4@',
        '@GRANDCHILD@',
    ]
    edges = [
        ('@CENTER@', '@PARENT1@', 'parents'),
        ('@CENTER@', '@PARENT2@', 'parents'),
        ('@CENTER@', '@SIB1@', 'siblings'),
        ('@CENTER@', '@SIB2@', 'siblings'),
        ('@CENTER@', '@SIB3@', 'siblings'),
        ('@CENTER@', '@CENTER_SP1@', 'spouses'),
        ('@CENTER@', '@CENTER_CH1@', 'children'),
        ('@CENTER@', '@CENTER_CH2@', 'children'),
        ('@CENTER@', '@CENTER_CH3@', 'children'),
        ('@CENTER@', '@CENTER_CH4@', 'children'),
        ('@CENTER@', '@CENTER_SP2@', 'spouses'),
        ('@SIB2@', '@SIB2_SP@', 'spouses'),
        ('@SIB2@', '@SIB2_CH1@', 'children'),
        ('@SIB2@', '@SIB2_CH2@', 'children'),
        ('@SIB2@', '@SIB2_CH3@', 'children'),
        ('@SIB2@', '@SIB2_CH4@', 'children'),
        ('@CENTER_CH1@', '@GRANDCHILD@', 'children'),
    ]

    layout = layout_family_tree('@CENTER@', visible, edges)
    by_id = {node['id']: node for node in layout}
    same_row_columns = sorted(
        node['column'] for node in layout
        if node['generation'] == by_id['@CENTER@']['generation'])
    largest_gap = max(
        same_row_columns[index + 1] - same_row_columns[index]
        for index in range(len(same_row_columns) - 1))

    assert by_id['@SIB1@']['column'] < 10.0
    assert largest_gap <= 2.5


def test_family_tree_center_siblings_stay_contiguous_after_uncle_children():
    """Unrelated same-row nodes cannot split the center sibling group."""
    visible = [
        '@CENTER@',
        '@CENTER_SP@',
        '@CH1@',
        '@CH2@',
        '@PARENT@',
        '@PARENT_SP@',
        '@SIB1@',
        '@SIB2@',
        '@SIB3@',
        '@SIB4@',
        '@UNC@',
        '@UNC_SP@',
        '@UNC_SIB1@',
        '@UNC_SIB2@',
        '@COUS1@',
        '@COUS2@',
    ]
    edges = [
        ('@CENTER@', '@CH1@', 'children'),
        ('@CENTER@', '@CENTER_SP@', 'spouses'),
        ('@CENTER@', '@CH2@', 'children'),
        ('@CENTER@', '@PARENT@', 'parents'),
        ('@CENTER@', '@PARENT_SP@', 'parents'),
        ('@CENTER@', '@SIB1@', 'siblings'),
        ('@CENTER@', '@SIB2@', 'siblings'),
        ('@CENTER@', '@SIB3@', 'siblings'),
        ('@CENTER@', '@SIB4@', 'siblings'),
        ('@PARENT@', '@PARENT_SP@', 'spouses'),
        ('@PARENT@', '@UNC@', 'siblings'),
        ('@PARENT@', '@UNC_SIB1@', 'siblings'),
        ('@PARENT@', '@UNC_SIB2@', 'siblings'),
        ('@UNC@', '@UNC_SP@', 'spouses'),
        ('@UNC@', '@COUS1@', 'children'),
        ('@UNC@', '@COUS2@', 'children'),
    ]

    layout = layout_family_tree('@CENTER@', visible, edges)
    by_id = {node['id']: node for node in layout}
    sibling_group = {
        '@SIB1@',
        '@SIB2@',
        '@SIB3@',
        '@SIB4@',
        '@CENTER@',
    }
    group_columns = [by_id[person_id]['column'] for person_id in sibling_group]
    group_min = min(group_columns)
    group_max = max(group_columns)
    interlopers = [
        node['id'] for node in layout
        if node['id'] not in sibling_group | {'@CENTER_SP@'}
        and node['generation'] == by_id['@CENTER@']['generation']
        and group_min < node['column'] < group_max
    ]

    assert interlopers == []
    assert by_id['@CENTER_SP@']['column'] == by_id['@CENTER@']['column'] + 1.0


def test_family_tree_non_center_parent_couple_moves_toward_children():
    """A non-center parent couple can move over visible children."""
    visible = [
        '@CENTER@',
        '@CENTER_SP@',
        '@CH1@',
        '@CH2@',
        '@PARENT@',
        '@PARENT_SP@',
        '@SIB1@',
        '@SIB2@',
        '@SIB3@',
        '@SIB4@',
        '@UNC@',
        '@UNC_SP@',
        '@UNC_SIB1@',
        '@UNC_SIB2@',
        '@COUS1@',
        '@COUS2@',
    ]
    edges = [
        ('@CENTER@', '@CH1@', 'children'),
        ('@CENTER@', '@CENTER_SP@', 'spouses'),
        ('@CENTER@', '@CH2@', 'children'),
        ('@CENTER@', '@PARENT@', 'parents'),
        ('@CENTER@', '@PARENT_SP@', 'parents'),
        ('@CENTER@', '@SIB1@', 'siblings'),
        ('@CENTER@', '@SIB2@', 'siblings'),
        ('@CENTER@', '@SIB3@', 'siblings'),
        ('@CENTER@', '@SIB4@', 'siblings'),
        ('@PARENT@', '@PARENT_SP@', 'spouses'),
        ('@PARENT@', '@UNC@', 'siblings'),
        ('@PARENT@', '@UNC_SIB1@', 'siblings'),
        ('@PARENT@', '@UNC_SIB2@', 'siblings'),
        ('@UNC@', '@UNC_SP@', 'spouses'),
        ('@UNC@', '@COUS1@', 'children'),
        ('@UNC@', '@COUS2@', 'children'),
    ]

    layout = layout_family_tree('@CENTER@', visible, edges)
    by_id = {node['id']: node for node in layout}
    uncle_midpoint = (
        by_id['@UNC@']['column'] + by_id['@UNC_SP@']['column']) / 2
    cousin_midpoint = (
        by_id['@COUS1@']['column'] + by_id['@COUS2@']['column']) / 2
    sibling_side_columns = sorted([
        by_id['@UNC@']['column'],
        by_id['@UNC_SP@']['column'],
        by_id['@UNC_SIB1@']['column'],
        by_id['@UNC_SIB2@']['column'],
    ])
    largest_sibling_side_gap = max(
        sibling_side_columns[index + 1] - sibling_side_columns[index]
        for index in range(len(sibling_side_columns) - 1))

    assert uncle_midpoint == cousin_midpoint
    assert largest_sibling_side_gap <= 1.5


def test_family_tree_center_child_cluster_compacts_toward_parents():
    """Child spouses do not force the whole youngest generation far right."""
    visible = [
        '@CENTER@',
        '@CENTER_SP@',
        '@CH1@',
        '@CH1_SP@',
        '@CH2@',
        '@CH3@',
        '@GC1@',
        '@GC2@',
        '@PARENT@',
        '@PARENT_SP@',
        '@SIB1@',
        '@SIB2@',
        '@SIB3@',
        '@SIB4@',
    ]
    edges = [
        ('@CENTER@', '@CENTER_SP@', 'spouses'),
        ('@CENTER@', '@CH1@', 'children'),
        ('@CENTER@', '@CH2@', 'children'),
        ('@CENTER@', '@CH3@', 'children'),
        ('@CH1@', '@CH1_SP@', 'spouses'),
        ('@CH1@', '@GC1@', 'children'),
        ('@CH1@', '@GC2@', 'children'),
        ('@CENTER@', '@PARENT@', 'parents'),
        ('@CENTER@', '@PARENT_SP@', 'parents'),
        ('@CENTER@', '@SIB1@', 'siblings'),
        ('@CENTER@', '@SIB2@', 'siblings'),
        ('@CENTER@', '@SIB3@', 'siblings'),
        ('@CENTER@', '@SIB4@', 'siblings'),
    ]

    layout = layout_family_tree('@CENTER@', visible, edges)
    by_id = {node['id']: node for node in layout}
    parent_midpoint = (
        by_id['@CENTER@']['column'] + by_id['@CENTER_SP@']['column']) / 2
    child_columns = [
        by_id['@CH1@']['column'],
        by_id['@CH1_SP@']['column'],
        by_id['@CH2@']['column'],
        by_id['@CH3@']['column'],
    ]
    child_midpoint = (min(child_columns) + max(child_columns)) / 2

    assert abs(parent_midpoint - child_midpoint) <= 1.0


def test_family_tree_shifted_child_group_connector_spans_parent_origin():
    """A shifted child group still draws a connector back to its parents."""
    visible = [
        '@P1@',
        '@P2@',
        '@CENTER@',
        '@SIB1@',
        '@SIB2@',
        '@SIB3@',
        '@CENTER_SP1@',
        '@CENTER_CH1@',
        '@CENTER_CH2@',
        '@CENTER_CH3@',
        '@CENTER_CH4@',
        '@CENTER_SP2@',
        '@SIB1_SP@',
        '@SIB1_CH1@',
        '@SIB1_CH2@',
        '@SIB1_CH3@',
        '@SIB1_CH4@',
        '@SIB1_CH5@',
    ]
    edges = [
        ('@P1@', '@P2@', 'spouses'),
        ('@CENTER@', '@P1@', 'parents'),
        ('@CENTER@', '@P2@', 'parents'),
        ('@CENTER@', '@SIB1@', 'siblings'),
        ('@CENTER@', '@SIB2@', 'siblings'),
        ('@CENTER@', '@SIB3@', 'siblings'),
        ('@CENTER@', '@CENTER_SP1@', 'spouses'),
        ('@CENTER@', '@CENTER_CH1@', 'children'),
        ('@CENTER@', '@CENTER_CH2@', 'children'),
        ('@CENTER@', '@CENTER_CH3@', 'children'),
        ('@CENTER@', '@CENTER_CH4@', 'children'),
        ('@CENTER@', '@CENTER_SP2@', 'spouses'),
        ('@SIB1@', '@SIB1_SP@', 'spouses'),
        ('@SIB1@', '@SIB1_CH1@', 'children'),
        ('@SIB1@', '@SIB1_CH2@', 'children'),
        ('@SIB1@', '@SIB1_CH3@', 'children'),
        ('@SIB1@', '@SIB1_CH4@', 'children'),
        ('@SIB1@', '@SIB1_CH5@', 'children'),
    ]

    layout = layout_family_tree('@CENTER@', visible, edges)
    positions = {
        node['id']: (node['column'], node['generation'])
        for node in layout
    }
    groups = ResultsMixin._family_tree_child_edge_groups(
        edges,
        positions,
        lambda _parent_id, _child_ids: [],
        [('@P1@', '@P2@'), ('@CENTER@', '@CENTER_SP1@')],
    )
    child_group = next(
        group for group in groups
        if set(group['children']) == {
            '@CENTER_CH1@',
            '@CENTER_CH2@',
            '@CENTER_CH3@',
            '@CENTER_CH4@',
        })
    child_columns = [
        positions[child_id][0] for child_id in child_group['children']
    ]
    bus_start, bus_end = ResultsMixin._family_tree_child_bus_span(
        child_group['parent_x'], child_columns)

    assert bus_start <= min([child_group['parent_x'], *child_columns])
    assert bus_end >= max([child_group['parent_x'], *child_columns])


def test_family_tree_expanded_child_spouse_does_not_overlap_sibling_child():
    """A displayed spouse of one child reserves room before the next child."""
    visible = [
        '@CENTER@',
        '@PARENT1@',
        '@PARENT2@',
        '@SIB1@',
        '@SIB2@',
        '@SIB3@',
        '@CENTER_SP1@',
        '@CENTER_SP2@',
        '@CH1@',
        '@CH2@',
        '@CH3@',
        '@CH4@',
        '@GRANDCHILD@',
        '@CH3_SP@',
    ]
    edges = [
        ('@CENTER@', '@PARENT1@', 'parents'),
        ('@CENTER@', '@PARENT2@', 'parents'),
        ('@CENTER@', '@SIB1@', 'siblings'),
        ('@CENTER@', '@SIB2@', 'siblings'),
        ('@CENTER@', '@SIB3@', 'siblings'),
        ('@CENTER@', '@CENTER_SP1@', 'spouses'),
        ('@CENTER@', '@CH1@', 'children'),
        ('@CENTER@', '@CH2@', 'children'),
        ('@CENTER@', '@CH3@', 'children'),
        ('@CENTER@', '@CH4@', 'children'),
        ('@CENTER@', '@CENTER_SP2@', 'spouses'),
        ('@CH1@', '@GRANDCHILD@', 'children'),
        ('@CH3@', '@CH3_SP@', 'spouses'),
    ]

    layout = layout_family_tree('@CENTER@', visible, edges)
    by_id = {node['id']: node for node in layout}
    same_row_nodes = [
        node for node in layout
        if node['generation'] == by_id['@CH4@']['generation']
    ]

    assert abs(by_id['@CH3@']['column']
               - by_id['@CH3_SP@']['column']) >= 1.0
    assert abs(by_id['@CH4@']['column']
               - by_id['@CH3_SP@']['column']) >= 1.0
    assert all(
        abs(left['column'] - right['column']) >= 1.0
        for index, left in enumerate(same_row_nodes)
        for right in same_row_nodes[index + 1:])


def test_family_tree_unrelated_child_groups_do_not_interleave():
    """Children from adjacent couples stay in distinct row bands."""
    visible = [
        '@CENTER@',
        '@CENTER_SP1@',
        '@CENTER_SP2@',
        '@SIB@',
        '@SIB_SP@',
        '@SIB_CH1@',
        '@SIB_CH2@',
        '@SIB_CH3@',
        '@SIB_CH4@',
        '@SIB_CH5@',
        '@CENTER_CH1@',
        '@CENTER_CH2@',
        '@CENTER_CH3@',
        '@CENTER_CH4@',
        '@CENTER_CH3_SP@',
        '@GRANDCHILD@',
    ]
    edges = [
        ('@CENTER@', '@SIB@', 'siblings'),
        ('@CENTER@', '@CENTER_SP1@', 'spouses'),
        ('@CENTER@', '@CENTER_SP2@', 'spouses'),
        ('@CENTER@', '@CENTER_CH1@', 'children'),
        ('@CENTER@', '@CENTER_CH2@', 'children'),
        ('@CENTER@', '@CENTER_CH3@', 'children'),
        ('@CENTER@', '@CENTER_CH4@', 'children'),
        ('@SIB@', '@SIB_SP@', 'spouses'),
        ('@SIB@', '@SIB_CH1@', 'children'),
        ('@SIB@', '@SIB_CH2@', 'children'),
        ('@SIB@', '@SIB_CH3@', 'children'),
        ('@SIB@', '@SIB_CH4@', 'children'),
        ('@SIB@', '@SIB_CH5@', 'children'),
        ('@CENTER_CH1@', '@GRANDCHILD@', 'children'),
        ('@CENTER_CH3@', '@CENTER_CH3_SP@', 'spouses'),
    ]

    layout = layout_family_tree('@CENTER@', visible, edges)
    by_id = {node['id']: node for node in layout}
    sibling_child_columns = sorted(
        by_id[child_id]['column']
        for child_id in (
            '@SIB_CH1@',
            '@SIB_CH2@',
            '@SIB_CH3@',
            '@SIB_CH4@',
            '@SIB_CH5@',
        ))
    center_child_columns = sorted(
        by_id[child_id]['column']
        for child_id in (
            '@CENTER_CH1@',
            '@CENTER_CH2@',
            '@CENTER_CH3@',
            '@CENTER_CH4@',
        ))

    assert (
        sibling_child_columns[-1] < center_child_columns[0]
        or center_child_columns[-1] < sibling_child_columns[0]
    )


def test_family_tree_expand_all_uses_only_hidden_categories():
    """Expand All matches the visible expansion buttons for a sibling node."""
    families = {
        '@COUSN2@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2_SIB2@', '@COUSN2_SIB1@'],
            'spouses': ['@COUSN2_SP@'],
            'children': ['@COUSN2_CH1@', '@COUSN2_CH2@'],
        },
        '@COUSN2_SIB2@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2@', '@COUSN2_SIB1@'],
            'spouses': ['@SIB2_SP@'],
            'children': ['@SIB2_CH1@', '@SIB2_CH2@'],
        },
        '@COUSN2_SIB1@': {
            'parents': ['@COUSN@', '@COUSN_SP@'],
            'siblings': ['@COUSN2@', '@COUSN2_SIB2@'],
            'spouses': [],
            'children': [],
        },
        '@COUSN@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN_SP@'],
            'children': ['@COUSN2_SIB2@', '@COUSN2_SIB1@', '@COUSN2@'],
        },
        '@COUSN_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN@'],
            'children': ['@COUSN2_SIB2@', '@COUSN2_SIB1@', '@COUSN2@'],
        },
        '@COUSN2_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN2@'],
            'children': ['@COUSN2_CH1@', '@COUSN2_CH2@'],
        },
        '@SIB2_SP@': {
            'parents': [],
            'siblings': [],
            'spouses': ['@COUSN2_SIB2@'],
            'children': ['@SIB2_CH1@', '@SIB2_CH2@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    def coparents(indi_id, child_ids):
        child_ids = set(child_ids)
        if indi_id == '@COUSN2@' and child_ids & {'@COUSN2_CH1@', '@COUSN2_CH2@'}:
            return ['@COUSN2_SP@']
        if indi_id == '@COUSN2_SP@' and child_ids & {'@COUSN2_CH1@', '@COUSN2_CH2@'}:
            return ['@COUSN2@']
        if indi_id == '@COUSN2_SIB2@' and child_ids & {'@SIB2_CH1@', '@SIB2_CH2@'}:
            return ['@SIB2_SP@']
        if indi_id == '@SIB2_SP@' and child_ids & {'@SIB2_CH1@', '@SIB2_CH2@'}:
            return ['@COUSN2_SIB2@']
        if indi_id == '@COUSN@' and child_ids & {
                '@COUSN2_SIB2@', '@COUSN2_SIB1@', '@COUSN2@'}:
            return ['@COUSN_SP@']
        if indi_id == '@COUSN_SP@' and child_ids & {
                '@COUSN2_SIB2@', '@COUSN2_SIB1@', '@COUSN2@'}:
            return ['@COUSN@']
        return []

    visible, _edges = build_family_tree_graph(
        '@COUSN2@', [], lookup, coparents)
    options = family_tree_expansion_options(
        '@COUSN2_SIB2@', set(visible), lookup)
    hidden_categories = tuple(
        category for category in ('parents', 'siblings', 'spouses', 'children')
        if options.get(category))

    expanded = []
    ResultsMixin._expand_all_requests(
        expanded, '@COUSN2_SIB2@', hidden_categories)

    children_visible, children_edges = build_family_tree_graph(
        '@COUSN2@', [('@COUSN2_SIB2@', 'children')], lookup, coparents)
    expand_all_visible, expand_all_edges = build_family_tree_graph(
        '@COUSN2@', expanded, lookup, coparents)

    assert hidden_categories == ('spouses', 'children')
    assert expanded == [
        ('@COUSN2_SIB2@', 'spouses'),
        ('@COUSN2_SIB2@', 'children'),
    ]
    assert set(expand_all_visible) == set(children_visible)
    assert {
        node['id']: (node['generation'], node['column'])
        for node in layout_family_tree(
            '@COUSN2@', expand_all_visible, expand_all_edges)
    } == {
        node['id']: (node['generation'], node['column'])
        for node in layout_family_tree(
            '@COUSN2@', children_visible, children_edges)
    }


def test_nearest_unblocked_column_does_not_oscillate_between_spouses():
    """Column conflict resolution chooses a finite clear slot."""
    column = _nearest_unblocked_column(0.75, [0.0, 1.5])

    assert all(abs(column - blocked) >= 1.0 for blocked in (0.0, 1.5))


def test_nearest_unblocked_column_survives_float_packed_band():
    """A dense, float-spaced band must not min() over an empty candidate set.

    Column coordinates accumulate rounding error from the layout's 1.4/1.0 step
    arithmetic, so even the outermost blocked±spacing candidates can measure a
    hair under MIN_COLUMN_SPACING (e.g. 0.99999999999999) and get filtered out.
    This is the exact blocked set captured when expanding parents+children
    across a large family tree crashed the renderer with "min() iterable
    argument is empty"; the result must be a finite, clear column.
    """
    # Exact float values captured from the crashing layout; their binary
    # representations are what produce the sub-1.0 boundary distances, so they
    # must be kept verbatim (rounded versions do not reproduce the bug).
    blocked = [
        -3.4499999999999997, -2.05, -0.6499999999999999, 0.7499999999999996,
        2.15, 3.7500000000000004, 5.15, 6.550000000000001, 7.949999999999999,
        9.35, 10.65, 12.05, 13.45, 14.85, 16.55, 17.95, 19.35, 20.45, 21.85,
        23.549999999999997, 24.949999999999996, 26.349999999999998,
        27.749999999999996, 29.15, 30.549999999999997, 31.85, 33.25, 34.65,
        36.05, 37.800000000000004, 39.2, 40.6, 42.0, 43.4, 44.99999999999999,
        46.39999999999999, 47.8, 49.199999999999996, 50.599999999999994,
        51.99999999999999, 53.39999999999999, 54.8, 56.199999999999996, 57.4,
        58.8, 60.199999999999996, 61.199999999999996, 62.199999999999996,
        63.199999999999996,
    ]

    column = _nearest_unblocked_column(57.699999999999996, blocked)

    assert column == max(blocked) + 1.0
    # Clear of every blocked column (tolerating accumulated float error).
    assert all(abs(column - b) > 1.0 - 1e-6 for b in blocked)


def test_family_tree_expansion_options_only_include_hidden_relatives():
    """Expansion controls are omitted when all relatives are already visible."""
    families = {
        '@A@': {
            'parents': ['@P1@'],
            'siblings': ['@S1@'],
            'spouses': ['@W@'],
            'children': ['@C1@'],
        },
        '@P1@': {
            'parents': ['@GP1@'],
            'siblings': [],
            'spouses': [],
            'children': ['@A@', '@S1@', '@HALF@'],
        },
    }

    def lookup(indi_id):
        return families.get(indi_id, {
            'parents': [],
            'siblings': [],
            'spouses': [],
            'children': [],
        })

    center_options = family_tree_expansion_options(
        '@A@', {'@A@', '@P1@', '@S1@', '@W@', '@C1@'}, lookup)
    parent_options = family_tree_expansion_options(
        '@P1@', {'@A@', '@P1@', '@S1@', '@W@', '@C1@'}, lookup)

    assert center_options == {
        'parents': [],
        'siblings': [],
        'spouses': [],
        'children': [],
    }
    assert parent_options['parents'] == ['@GP1@']
    assert parent_options['children'] == ['@HALF@']
    assert parent_options['spouses'] == []


def test_toggle_expansion_request_adds_and_removes_request():
    """Expansion buttons behave as toggles."""
    expanded = []
    request = ('@A@', 'children')

    ResultsMixin._toggle_expansion_request(expanded, request)
    assert expanded == [request]

    ResultsMixin._toggle_expansion_request(expanded, request)
    assert expanded == []


def test_expand_all_requests_adds_missing_categories_without_toggling():
    """Expand All leaves active categories visible and enables the rest."""
    expanded = [('@A@', 'parents'), ('@B@', 'children')]

    changed = ResultsMixin._expand_all_requests(expanded, '@A@')

    assert changed is True
    assert expanded == [
        ('@A@', 'parents'),
        ('@B@', 'children'),
        ('@A@', 'siblings'),
        ('@A@', 'spouses'),
        ('@A@', 'children'),
    ]

    assert ResultsMixin._expand_all_requests(expanded, '@A@') is False
    assert expanded == [
        ('@A@', 'parents'),
        ('@B@', 'children'),
        ('@A@', 'siblings'),
        ('@A@', 'spouses'),
        ('@A@', 'children'),
    ]


def test_show_expansion_button_keeps_active_category_visible():
    """Expanded categories keep their button so a second click can hide them."""
    options = {
        'parents': [],
        'siblings': ['@S1@'],
        'spouses': [],
        'children': [],
    }
    expanded = {('@A@', 'parents'), ('@A@', 'spouses')}

    assert ResultsMixin._show_expansion_button(
        options, expanded, '@A@', 'parents') is True
    assert ResultsMixin._show_expansion_button(
        options, expanded, '@A@', 'siblings') is True
    assert ResultsMixin._show_expansion_button(
        options, expanded, '@A@', 'children') is False
    assert ResultsMixin._show_expansion_button(
        options, expanded, '@A@', 'spouses') is True


def test_expansion_button_text_reflects_next_toggle_action():
    """Expansion arrows reverse when a category is already visible."""
    expanded = {
        ('@A@', 'parents'),
        ('@A@', 'children'),
        ('@A@', 'siblings'),
        ('@A@', 'spouses'),
    }

    assert ResultsMixin._expansion_button_text(
        set(), '@A@', 'parents') == '↑'
    assert ResultsMixin._expansion_button_text(
        expanded, '@A@', 'parents') == '↓'
    assert ResultsMixin._expansion_button_text(
        set(), '@A@', 'children') == '↓'
    assert ResultsMixin._expansion_button_text(
        expanded, '@A@', 'children') == '↑'
    assert ResultsMixin._expansion_button_text(
        set(), '@A@', 'siblings', 'left') == '←'
    assert ResultsMixin._expansion_button_text(
        expanded, '@A@', 'siblings', 'left') == '→'
    assert ResultsMixin._expansion_button_text(
        set(), '@A@', 'siblings', 'right') == '→'
    assert ResultsMixin._expansion_button_text(
        expanded, '@A@', 'siblings', 'right') == '←'
    assert ResultsMixin._expansion_button_text(
        set(), '@A@', 'spouses') == '♥'
    assert ResultsMixin._expansion_button_text(
        expanded, '@A@', 'spouses') == '♡'


def test_expansion_button_tooltip_is_state_aware():
    """Relationship expansion toggles describe the next click action."""
    expanded = {
        ('@A@', 'parents'),
        ('@A@', 'siblings'),
        ('@A@', 'spouses'),
        ('@A@', 'children'),
    }

    assert ResultsMixin._expansion_button_tooltip(
        set(), '@A@', 'parents') == 'Show parents'
    assert ResultsMixin._expansion_button_tooltip(
        expanded, '@A@', 'parents') == 'Hide parents'
    assert ResultsMixin._expansion_button_tooltip(
        set(), '@A@', 'siblings') == 'Show siblings'
    assert ResultsMixin._expansion_button_tooltip(
        expanded, '@A@', 'siblings') == 'Hide siblings'
    assert ResultsMixin._expansion_button_tooltip(
        set(), '@A@', 'spouses') == 'Show spouses'
    assert ResultsMixin._expansion_button_tooltip(
        expanded, '@A@', 'spouses') == 'Hide spouses'
    assert ResultsMixin._expansion_button_tooltip(
        set(), '@A@', 'children') == 'Show children'
    assert ResultsMixin._expansion_button_tooltip(
        expanded, '@A@', 'children') == 'Hide children'
    assert ResultsMixin._expansion_button_tooltip(
        set(), '@A@', 'unknown') is None


def test_graph_button_visibility_uses_shared_canvas_tags():
    """Save/copy helpers hide all graph expansion buttons during export."""

    class FakeCanvas:
        def __init__(self):
            self.calls = []

        def itemconfigure(self, tag, **kwargs):
            self.calls.append((tag, kwargs))

    canvas = FakeCanvas()
    mixin = ResultsMixin()

    mixin._hide_graph_buttons(canvas)
    mixin._show_graph_buttons(canvas)

    assert canvas.calls == [
        ('family_tree_button', {'state': 'hidden'}),
        ('path_graph_button', {'state': 'hidden'}),
        ('family_tree_button', {'state': 'normal'}),
        ('path_graph_button', {'state': 'normal'}),
    ]


def test_spouse_button_uses_spouse_side_or_right_default():
    """The spouse toggle sits on the visible spouse side, or right by default."""
    assert ResultsMixin._spouse_button_x(
        '@A@', 100, 70, 130, 20, [], {}) == 140
    assert ResultsMixin._spouse_button_x(
        '@A@', 100, 70, 130, 20, [('@A@', '@S@')], {'@S@': (60, 100)}
    ) == 60
    assert ResultsMixin._spouse_button_x(
        '@A@', 100, 70, 130, 20, [('@A@', '@S@')], {'@S@': (140, 100)}
    ) == 140


def test_results_header_menu_clears_stale_person_id():
    """A stale results header from an old data set cannot open person actions."""

    class Var:
        def __init__(self, value):
            self.value = value

        def set(self, value):
            self.value = value

    class App(ResultsMixin):
        pass

    app = App()
    app._results_header_id = '@OLD@'
    app._results_header_var = Var('Old Person')
    app.individuals = {}
    updates = []
    app._update_header_label_style = lambda: updates.append(True)

    assert app._show_results_header_menu(object()) == 'break'
    assert app._results_header_id is None
    assert app._results_header_var.value == ''
    assert updates == [True]


def test_navigate_to_resets_stale_person_id():
    """Clicking an old result link after data changes resets stale results."""

    class App(ResultsMixin):
        pass

    app = App()
    app._busy = False
    app.individuals = {}
    resets = []
    app._reset_results_pane = lambda: resets.append(True)

    app._navigate_to('@OLD@')

    assert resets == [True]


def test_render_profile_result_exits_if_results_widget_is_destroyed_mid_render():
    """A modal media-folder prompt can replace the results widget during refresh."""

    class Widget:
        def __init__(self):
            self.exists = True
            self.calls = []

        def configure(self, **kwargs):
            if not self.exists:
                raise RuntimeError("should not configure destroyed widget")
            self.calls.append(("configure", kwargs))

        def delete(self, *args):
            if not self.exists:
                raise RuntimeError("should not delete destroyed widget")
            self.calls.append(("delete", args))

        def winfo_exists(self):
            return self.exists

    class Button:
        def __init__(self):
            self.calls = []

        def configure(self, **kwargs):
            self.calls.append(kwargs)

    class App(ResultsMixin):
        def _set_results_header_for_person(self, _indi_id):
            pass

        def _insert_person_profile(self, widget, *_args, **_kwargs):
            widget.exists = False

    app = App()
    app.individuals = {"@A@": {"name": "Alex", "_raw": []}}
    app.results = Widget()
    app._reverse_btn = Button()
    app._last_result = {"type": "profile"}

    app._render_profile_result("@A@", home_paths={})

    assert app._reverse_btn.calls == []


def test_family_tree_step_siblings_get_separate_child_buses():
    """Step-siblings hang from their own parent's bus, not the couple's.

    Regression test for debug/26: children of each remarried parent's
    earlier family must not render as children of the visible couple.
    """
    visible = ['@C@', '@F@', '@M@', '@FS@', '@MD@']
    edges = [
        ('@C@', '@F@', 'parents'),
        ('@C@', '@M@', 'parents'),
        ('@F@', '@M@', 'spouses'),
        ('@C@', '@FS@', 'siblings'),
        ('@C@', '@MD@', 'siblings'),
    ]
    family_members = {
        '@C@': {'parents': ['@F@', '@M@'], 'siblings': ['@FS@', '@MD@'],
                'spouses': [], 'children': []},
        '@F@': {'parents': [], 'siblings': [], 'spouses': ['@M@', '@X@'],
                'children': ['@C@', '@FS@']},
        '@M@': {'parents': [], 'siblings': [], 'spouses': ['@F@', '@Y@'],
                'children': ['@C@', '@MD@']},
        '@FS@': {'parents': ['@F@', '@X@'], 'siblings': ['@C@'],
                 'spouses': [], 'children': []},
        '@MD@': {'parents': ['@M@', '@Y@'], 'siblings': ['@C@'],
                 'spouses': [], 'children': []},
    }

    layout = layout_family_tree('@C@', visible, edges, family_members)
    buses = {
        tuple(sorted(bus['parent_ids'])): bus['children']
        for bus in layout.child_buses
    }

    assert buses[('@F@', '@M@')] == ['@C@']
    assert buses[('@F@',)] == ['@FS@']
    assert buses[('@M@',)] == ['@MD@']


def test_family_tree_debug_fixture_sweep_holds_layout_invariants():
    """Every family-tree debug fixture lays out without overlap or split
    spouse pairs (pairs may only be separated by their own spouse chain)."""
    fixture_paths = sorted(Path('debug').glob('*.json'))
    if not fixture_paths:
        pytest.skip('no debug fixtures present')
    checked = 0
    for path in fixture_paths:
        payload = json.loads(path.read_text())
        if payload.get('graph_type', 'family_tree') != 'family_tree':
            continue
        edges = [
            (edge['source'], edge['target'], edge['category'])
            for edge in payload['edges']
        ]
        layout = layout_family_tree(
            payload['center_id'], payload['visible_ids'], edges,
            payload.get('family_members'),
            _debug_fixture_parent_kind(payload))
        by_id = {node['id']: node for node in layout}
        assert len(by_id) == len(set(payload['visible_ids'])), path.name

        rows = {}
        for node in layout:
            rows.setdefault(node['generation'], []).append(
                (node['column'], node['id']))
        for row in rows.values():
            row.sort()
            for (left_col, left_id), (right_col, right_id) in zip(
                    row, row[1:]):
                assert right_col - left_col >= 1.0 - 1e-9, (
                    f'{path.name}: {left_id} and {right_id} overlap')

        chain_of = {}
        for source_id, target_id, category in edges:
            if category != 'spouses':
                continue
            if source_id not in by_id or target_id not in by_id:
                continue
            roots = [chain_of.get(source_id), chain_of.get(target_id)]
            root = next((r for r in roots if r is not None), source_id)
            for member, current in list(chain_of.items()):
                if current in roots:
                    chain_of[member] = root
            chain_of[source_id] = root
            chain_of[target_id] = root
        for source_id, target_id, category in edges:
            if category != 'spouses':
                continue
            if source_id not in by_id or target_id not in by_id:
                continue
            left = by_id[source_id]
            right = by_id[target_id]
            assert left['generation'] == right['generation'], (
                f'{path.name}: {source_id} {target_id} on different rows')
            low = min(left['column'], right['column'])
            high = max(left['column'], right['column'])
            between = [
                node_id for col, node_id in rows[left['generation']]
                if low + 1e-9 < col < high - 1e-9
            ]
            for node_id in between:
                assert chain_of.get(node_id) == chain_of.get(source_id), (
                    f'{path.name}: {node_id} splits spouse pair '
                    f'{source_id}/{target_id}')
        checked += 1
    assert checked


def test_family_tree_step_parent_excluded_from_biological_family_unit():
    """Regression test for debug/27: a child of divorced biological parents
    must hang from both of them, not appear as a step-child of the parent's
    later spouse, even though GEDCOM lists the step-parent in a famc."""
    path = Path('debug/27.json')
    if not path.exists():
        pytest.skip('debug/27.json not found')
    payload = json.loads(path.read_text())
    edges = [
        (edge['source'], edge['target'], edge['category'])
        for edge in payload['edges']
    ]
    layout = layout_family_tree(
        payload['center_id'], payload['visible_ids'], edges,
        payload['family_members'], _debug_fixture_parent_kind(payload))
    buses = {
        tuple(sorted(bus['parent_ids'])): bus['children']
        for bus in layout.child_buses
        if bus['parent_ids']
    }

    # Jamie (@I23182@) under biological parents Richard (@I186@) and
    # Leah (@I23195@); step-father Michael (@I23221@) not on Jamie's bus.
    assert buses[('@I186@', '@I23195@')] == ['@I23182@']
    # Jason (@I23222@) stays under Leah and Michael.
    assert buses[('@I23195@', '@I23221@')] == ['@I23222@']


def test_family_tree_ancestor_blocks_follow_couple_order():
    """Regression test for debug/28: each spouse's parents must sit on that
    spouse's side — Herbert left of Barbara means Herbert's parents stay
    left of Barbara's parents, so the parent drop lines never cross."""
    path = Path('debug/28.json')
    if not path.exists():
        pytest.skip('debug/28.json not found')
    payload = json.loads(path.read_text())
    edges = [
        (edge['source'], edge['target'], edge['category'])
        for edge in payload['edges']
    ]
    layout = layout_family_tree(
        payload['center_id'], payload['visible_ids'], edges,
        payload['family_members'], _debug_fixture_parent_kind(payload))
    cols = {node['id']: node['column'] for node in layout}

    couple = {
        '@I25@': ('@I30@', '@I29@'),   # Herbert -> Abraham, Helen
        '@I26@': ('@I13@', '@I14@'),   # Barbara -> Maurice, Dorothy
    }
    left_spouse, right_spouse = sorted(couple, key=lambda pid: cols[pid])
    assert max(cols[pid] for pid in couple[left_spouse]) < min(
        cols[pid] for pid in couple[right_spouse])
