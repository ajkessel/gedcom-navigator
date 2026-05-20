#!/usr/bin/env python3
"""
gedcom_gui_graph_render.py

Compatibility mixin that combines graph rendering helper groups.
"""

from gedcom_gui_family_tree_render import FamilyTreeRenderMixin
from gedcom_gui_graph_common import GraphCommonMixin
from gedcom_gui_path_graph import PathGraphMixin


class GraphRenderMixin(PathGraphMixin, FamilyTreeRenderMixin, GraphCommonMixin):
    """Combined graph rendering mixin used by ResultsMixin."""
