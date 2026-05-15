"""Tests for result-pane path rendering helpers."""

from gedcom_gui_results import ResultsMixin


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
        ('@HERBERT@', None),
        ('@ABRAHAM@', 'father'),
        ('@HYMAN@', 'father'),
        ('@HARRIS@', 'father'),
        ('@LOUIS@', 'child'),
        ('@ANNIE@', 'spouse'),
    ]

    simplified = ResultsMixin._simplify_path_for_graph(path)

    assert simplified == [
        ('@HERBERT@', None),
        ('@ABRAHAM@', 'father'),
        ('@HYMAN@', 'father'),
        ('@LOUIS@', 'sibling'),
        ('@ANNIE@', 'spouse'),
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


def test_path_graph_colors_follow_selected_theme():
    """Graph colors derive from the selected theme palette."""
    blue = ResultsMixin._path_graph_colors(False, 'Blue')
    green = ResultsMixin._path_graph_colors(False, 'Green')

    assert blue['bg'] == '#EBF0FA'
    assert green['bg'] == '#EBF5EB'
    assert blue['parent'] == '#1155bb'
    assert green['parent'] == '#2e8b57'
    assert blue['node_fill'] != green['node_fill']
