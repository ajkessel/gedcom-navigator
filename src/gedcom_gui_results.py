#!/usr/bin/env python3
"""
gedcom_gui_results.py

Result rendering, path reversal, person navigation, and family-summary helpers.
"""

import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

import customtkinter as ctk

from gedcom_display import describe
from gedcom_gui_graph_layout import GraphLayoutMixin
from gedcom_gui_graph_render import GraphRenderMixin
from gedcom_relationship import (
    describe_relationship,
    get_ancestor_depths,
    get_descendant_depths,
)
from gedcom_strings import *  # pylint: disable=unused-wildcard-import
from gedcom_theme import get_link_color, ttk_colors
from gedcom_tooltip import TextTagTooltip


class ResultsMixin(GraphRenderMixin, GraphLayoutMixin):
    """Render search results and handle result-pane navigation."""

    def _reverse_results(self):
        """Toggle reversed display of the current results."""
        if not self._last_result:
            return
        self._results_reversed = not self._results_reversed
        self._reverse_btn.configure(
            text=BTN_REVERSE_RESTORE if self._results_reversed else BTN_REVERSE)
        kind = self._last_result['type']
        if kind == 'dna_matches':
            self._render_results(
                self._last_result['start_id'],
                self._last_result.get('results', []),
                home_paths=self._last_result.get('home_paths'),
            )
        elif kind == 'path':
            self._render_path_results(
                self._last_result['start_id'],
                self._last_result['end_id'],
                self._last_result.get('paths', []),
                self._last_result.get('truncated', False),
            )

    def _render_results(self, start_id, results, home_paths=None):
        """Render DNA match search results and family context."""
        if self._last_result and self._last_result.get('type') == 'dna_matches':
            self._last_result['results'] = results
            self._last_result['home_paths'] = home_paths
        w = self.results
        tw = w._textbox
        w.configure(state='normal')
        w.delete('1.0', 'end')
        self._clear_person_tags(w)

        tw.update_idletasks()
        sep_width = max(tw.winfo_width() - 4, 100)
        is_dark = ctk.get_appearance_mode() == 'Dark'
        sep_color = '#DCE4EE' if is_dark else '#1a1a1a'

        tag_to_id = {}
        tw.tag_configure('person_link', foreground=self._link_color)
        tw.tag_bind('person_link', '<Enter>',
                    lambda *_: tw.config(cursor='hand2'))
        tw.tag_bind('person_link', '<Leave>',
                    lambda *_: tw.config(cursor=''))
        tw.tag_configure('relationship_link',
                         foreground=self._link_color, underline=1)

        relationship_tooltip = getattr(self, '_relationship_tooltip', None)
        if (relationship_tooltip is None or
                not relationship_tooltip.is_for(tw)):
            relationship_tooltip = TextTagTooltip(tw, TIP_RELATIONSHIP)
            self._relationship_tooltip = relationship_tooltip
        tw.tag_bind('relationship_link', '<Enter>',
                    lambda e: (tw.config(cursor='hand2'),
                               relationship_tooltip.on_enter(e)))
        tw.tag_bind('relationship_link', '<Motion>',
                    relationship_tooltip.on_enter)
        tw.tag_bind('relationship_link', '<Leave>',
                    lambda e: (tw.config(cursor=''),
                               relationship_tooltip.on_leave(e)))

        def _on_person_click(event):
            idx = tw.index(f'@{event.x},{event.y}')
            for t in tw.tag_names(idx):
                if t.startswith('pers_'):
                    iid = tag_to_id.get(t)
                    if iid:
                        self._navigate_to(iid)
                    break
        tw.tag_bind('person_link', '<Button-1>', _on_person_click)

        def nl(text='', bold=False):
            w.insert('end', text + '\n', ('bold',) if bold else ())

        def hr():
            sep = tk.Frame(tw, height=2, width=sep_width,
                           bg=sep_color, bd=0, relief='flat')
            tw.window_create('end', window=sep)
            tw.insert('end', '\n')

        def person(indi_id, prefix='', bold=False):
            base = ('bold',) if bold else ()
            if prefix:
                w.insert('end', prefix, base)
            tag = f'pers_{indi_id.strip("@")}'
            tag_to_id[tag] = indi_id
            w.insert('end', describe(self.individuals[indi_id], show_id=self.show_ids.get()),
                     base + ('person_link', tag))
            w.insert('end', '\n')

        def person_inline(indi_id, prefix='', suffix=''):
            if prefix:
                w.insert('end', prefix)
            tag = f'pers_{indi_id.strip("@")}'
            tag_to_id[tag] = indi_id
            w.insert('end', describe(self.individuals[indi_id],
                                     show_id=self.show_ids.get()),
                     ('person_link', tag))
            if suffix:
                w.insert('end', suffix)

        relationship_link_count = 0

        def relationship_line(rel, path, prefix=''):
            nonlocal relationship_link_count
            tag = f'path_graph_{relationship_link_count}'
            relationship_link_count += 1
            if prefix:
                w.insert('end', prefix)
            w.insert('end', RESULT_RELATIONSHIP.format(rel=rel),
                     ('relationship_link', tag))
            tw.tag_bind(
                tag, '<Button-1>',
                lambda _, p=tuple(path), r=rel: self._show_path_graph(p, r))
            w.insert('end', '\n')

        def common_ancestor_line(ancestor_ids, prefix='', item_prefix='    '):
            if prefix:
                w.insert('end', prefix)
            if not ancestor_ids:
                w.insert('end', RESULT_COMMON_ANCESTOR)
                w.insert('end', RESULT_COMMON_ANCESTOR_NONE)
                w.insert('end', '\n')
                return
            if len(ancestor_ids) == 1:
                w.insert('end', RESULT_COMMON_ANCESTOR)
                person_inline(ancestor_ids[0])
                w.insert('end', '\n')
                return
            w.insert('end', RESULT_COMMON_ANCESTORS + '\n')
            for ancestor_id in ancestor_ids:
                person_inline(ancestor_id, prefix=item_prefix)
                w.insert('end', '\n')

        result_detail_indent = "   "
        result_edge_indent = "       "
        home_edge_indent = "    "

        start = self.individuals[start_id]
        name = self._display_name(start)
        b, d = start.get('birth_year'), start.get('death_year')
        if b and d:
            lifespan = f" ({b}–{d})"
        elif b:
            lifespan = f" (b. {b})"
        elif d:
            lifespan = f" (d. {d})"
        else:
            lifespan = ""
        if self.show_ids.get():
            name += f" [{start_id.strip('@')}]"
        self._results_header_var.set(name + lifespan)
        self._results_header_id = start_id
        self._update_header_label_style()

        nl(RESULT_CLOSEST_MATCHES, bold=True)
        if start['dna_markers']:
            nl(RESULT_DNA_FLAGGED_NOTE)
            for m in start['dna_markers']:
                nl(f"    - {self._format_marker(m)}")
        nl()

        if not results:
            nl(RESULT_NO_DNA_FOUND)
        else:
            hr()
            if self._results_reversed:
                for rank, (dist, path) in enumerate(results, 1):
                    match_id = path[-1][0]
                    rev_path = self._reverse_path(path, self.individuals)
                    m_anc = get_ancestor_depths(
                        match_id, self.individuals, self.families)
                    m_desc = get_descendant_depths(
                        match_id, self.individuals, self.families)
                    rel = describe_relationship(
                        rev_path, self.individuals,
                        ancestors=m_anc, descendants=m_desc,
                        families=self.families)
                    person(match_id,
                           prefix=RESULT_RANK_PREFIX.format(rank=rank), bold=True)
                    relationship_line(
                        rel, rev_path, prefix=result_detail_indent)
                    common_ancestor_line(
                        self._model.find_common_ancestors(
                            rev_path[0][0], rev_path[-1][0]),
                        prefix=result_detail_indent,
                        item_prefix="     ")
                    nl(result_detail_indent + RESULT_PATH)
                    for i, (node_id, edge) in enumerate(rev_path):
                        if i == 0:
                            person(node_id, prefix="     ")
                        else:
                            person(node_id, prefix=self._path_edge_prefix(
                                edge, result_edge_indent))
                    nl(RESULT_DNA_MARKERS)
                    for m in self.individuals[match_id]['dna_markers']:
                        nl(f"     - {self._format_marker(m)}")
                    hr()
            else:
                ancestors = get_ancestor_depths(
                    start_id, self.individuals, self.families)
                descendants = get_descendant_depths(
                    start_id, self.individuals, self.families)
                for rank, (dist, path) in enumerate(results, 1):
                    end_id = path[-1][0]
                    person(end_id,
                           prefix=RESULT_RANK_PREFIX.format(rank=rank),
                           bold=True)
                    rel = describe_relationship(
                        path, self.individuals,
                        ancestors=ancestors, descendants=descendants,
                        families=self.families)
                    relationship_line(rel, path, prefix=result_detail_indent)
                    common_ancestor_line(
                        self._model.find_common_ancestors(
                            path[0][0], path[-1][0]),
                        prefix=result_detail_indent,
                        item_prefix="     ")
                    nl(result_detail_indent + RESULT_PATH)
                    for i, (node_id, edge) in enumerate(path):
                        if i == 0:
                            person(node_id, prefix="     ")
                        else:
                            person(node_id, prefix=self._path_edge_prefix(
                                edge, result_edge_indent))
                    nl(RESULT_DNA_MARKERS)
                    for m in self.individuals[end_id]['dna_markers']:
                        nl(f"     - {self._format_marker(m)}")
                    hr()

        # Family section
        nl(FAM_SECTION, bold=True)
        family_found = False
        parents, siblings, spouses, children = self._get_family_members(
            start_id)

        if parents:
            family_found = True
            nl(FAM_PARENTS)
            for pid in parents:
                person(pid, prefix="    ")
        if siblings:
            family_found = True
            nl(FAM_SIBLINGS)
            for sib_id in siblings:
                person(sib_id, prefix="    ")
        if spouses:
            family_found = True
            nl(FAM_SPOUSES if len(spouses) > 1 else FAM_SPOUSE)
            for sid in spouses:
                person(sid, prefix="    ")
        if children:
            family_found = True
            nl(FAM_CHILDREN)
            for child_id in children:
                person(child_id, prefix="    ")
        if not family_found:
            nl(FAM_NO_INFO)
        nl()

        # Home person relationship
        home_id = self._home_person_id
        if home_id and home_id != start_id and home_id in self.individuals:
            hr()
            nl(RESULT_PATH_SECTION, bold=True)
            person(home_id, prefix=RESULT_HOME)
            if not home_paths:
                nl(RESULT_NO_HOME_PATH)
            else:
                raw_path = home_paths[0]
                if self._results_reversed:
                    disp_path = self._reverse_path(raw_path, self.individuals)
                    h_anc = get_ancestor_depths(
                        home_id, self.individuals, self.families)
                    h_desc = get_descendant_depths(
                        home_id, self.individuals, self.families)
                    rel = describe_relationship(
                        disp_path, self.individuals,
                        ancestors=h_anc, descendants=h_desc,
                        families=self.families)
                else:
                    disp_path = raw_path
                    ancestors = get_ancestor_depths(
                        start_id, self.individuals, self.families)
                    descendants = get_descendant_depths(
                        start_id, self.individuals, self.families)
                    rel = describe_relationship(
                        disp_path, self.individuals,
                        ancestors=ancestors, descendants=descendants,
                        families=self.families)
                relationship_line(rel, disp_path)
                common_ancestor_line(self._model.find_common_ancestors(
                    disp_path[0][0], disp_path[-1][0]))
                nl(RESULT_PATH)
                for i, (node_id, edge) in enumerate(disp_path):
                    if i == 0:
                        person(node_id, prefix="  ")
                    else:
                        person(node_id, prefix=self._path_edge_prefix(
                            edge, home_edge_indent))
            nl()

        self._reverse_btn.configure(state='normal')
        w.configure(state='disabled')
    def _show_results_header_menu(self, event):
        """Show a right-click context menu on the results pane title bar."""
        indi_id = getattr(self, '_results_header_id', None)
        if not indi_id:
            return 'break'
        _menu_kw = {'font': tkfont.nametofont('TkMenuFont')} if sys.platform == 'win32' else {}
        menu = tk.Menu(self._results_header_label, tearoff=0, **_menu_kw)

        def _copy_name():
            self.root.clipboard_clear()
            self.root.clipboard_append(
                self._display_name(self.individuals[indi_id]))

        menu.add_command(
            label=RESULTS_HEADER_MENU_COPY_NAME,
            command=_copy_name)
        menu.add_command(
            label=RESULTS_HEADER_MENU_SHOW_PROFILE,
            command=lambda: self._show_person_for(indi_id, initial_view='profile'))
        menu.add_command(
            label=RESULTS_HEADER_MENU_SHOW_TREE,
            command=lambda: self._show_person_for(indi_id, initial_view='tree'))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass
        return 'break'
    def _copy_results(self):
        """Copy the current results text to the clipboard."""
        text = self.results.get('1.0', 'end').rstrip()
        if not text:
            return
        header = self._results_header_var.get().strip()
        if header:
            text = header + '\n\n' + text
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
    def _save_results(self):
        """Save the current results text to a user-selected text file."""
        text = self.results.get('1.0', 'end').rstrip()
        if not text:
            return
        header = self._results_header_var.get().strip()
        if header:
            text = header + '\n\n' + text
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title=DLG_SAVE_RESULTS,
            defaultextension='.txt',
            filetypes=[
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as results_file:
                results_file.write(text)
                results_file.write('\n')
        except OSError as exc:
            messagebox.showerror(
                ERR_SAVE_GRAPH_TITLE,
                ERR_SAVE_RESULTS_MSG.format(error=exc),
                parent=self.root,
            )
    def _clear_results(self):
        """Clear result output and reset search focus."""
        self.results.configure(state='normal')
        self.results.delete('1.0', 'end')
        self.results.configure(state='disabled')
        self._results_header_var.set('')
        self._results_header_id = None
        self._update_header_label_style()
        self.search_text.set('')
        self._last_result = None
        self._results_reversed = False
        self._reverse_btn.configure(state='disabled', text=BTN_REVERSE)
        self._kb_focus_search()
    def _format_marker(self, marker):
        """Strip the trailing (@ref@) from a DNA marker string when Show IDs is off."""
        if self.show_ids.get():
            return marker
        return re.sub(r'\s*\(@[^@]+@\)\s*$', '', marker)
    def _clear_person_tags(self, widget):
        """Remove generated person-link tags from a Text-like widget."""
        tw = getattr(widget, '_textbox', widget)
        for tag in tw.tag_names():
            if tag.startswith('pers_') or tag.startswith('path_graph_'):
                tw.tag_delete(tag)
    def _select_person_in_main_tree(self, indi_id):
        """Select a person in the main people list, clearing filters if needed."""
        self._active_id = indi_id
        if not self.tree.exists(indi_id):
            self.search_text.set('')
            self.filter_text.set('')
            self.show_flagged_only.set(False)
            self._populate_tree()
        if self.tree.exists(indi_id):
            self.tree.selection_set(indi_id)
            self.tree.see(indi_id)
            self.tree.focus(indi_id)
            return True

        # Person exceeds max_display even with no filters; clear stale
        # selections so action buttons fall back to _active_id.
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(*selection)
        return False
    def _nav_snapshot(self):
        """Return a snapshot of the current navigable state."""
        return {
            'last_result': dict(self._last_result) if self._last_result else None,
            'active_id': self._active_id,
            'results_reversed': self._results_reversed,
        }
    def _nav_restore(self, snapshot):
        """Apply a navigation snapshot and re-render results."""
        self._last_result = snapshot['last_result']
        self._active_id = snapshot['active_id']
        self._results_reversed = snapshot['results_reversed']
        self._reverse_btn.configure(
            text=BTN_REVERSE_RESTORE if self._results_reversed else BTN_REVERSE)
        if self._active_id:
            self._select_person_in_main_tree(self._active_id)
        kind = self._last_result.get('type') if self._last_result else None
        if kind == 'dna_matches':
            self._render_results(
                self._last_result['start_id'],
                self._last_result.get('results', []),
                home_paths=self._last_result.get('home_paths'),
            )
        elif kind == 'path':
            self._render_path_results(
                self._last_result['start_id'],
                self._last_result['end_id'],
                self._last_result.get('paths', []),
                self._last_result.get('truncated', False),
            )
    def _navigate_back(self):
        """Restore the previous navigation state, saving current state for forward."""
        if self._busy or not self._nav_history:
            return
        self._nav_forward.append(self._nav_snapshot())
        self._nav_restore(self._nav_history.pop())
    def _navigate_forward(self):
        """Restore the next navigation state, saving current state for back."""
        if self._busy or not self._nav_forward:
            return
        self._nav_history.append(self._nav_snapshot())
        self._nav_restore(self._nav_forward.pop())
    def _navigate_to(self, indi_id):
        """Select a person in the tree and refresh the results pane for them.

        If the right pane currently shows DNA matches, shows DNA matches for the
        new person.  If it shows a relationship path, finds the path from the new
        person to the same destination.
        """
        if self._busy:
            return

        if self._last_result:
            self._nav_history.append(self._nav_snapshot())
            self._nav_forward.clear()

        # reset "reverse" button and pull in default search parameters
        self._results_reversed = False
        self._reverse_btn.configure(text=BTN_REVERSE)
        try:
            top_n = int(self.top_n.get())
            max_depth = int(self.max_depth.get())
        except (tk.TclError, ValueError):
            return

        kind = self._last_result.get('type') if self._last_result else None

        # for a "path" search, find the path from the originally selected person
        if kind == 'path':
            # to the newly selected person
            start_id = self._last_result['start_id']
            self._show_progress()
            self._set_busy(True)

            def _do_path(cancel_event):
                return self._model.find_all_paths(
                    start_id, indi_id, top_n, max_depth,
                    cancel_event=cancel_event)

            def _on_cancel():
                self._hide_progress()
                self._set_busy(False)

            def _on_done(result, error):
                self._hide_search_popup()
                self._hide_progress()
                self._set_busy(False)
                if error:
                    messagebox.showerror(ERR_PARSE_TITLE, str(error))
                    return
                paths, truncated = result
                self._last_result = {
                    'type': 'path',
                    'start_id': start_id,
                    'end_id': indi_id,
                }
                self._render_path_results(start_id, indi_id, paths, truncated)

            self._run_background_task(
                _do_path,
                _on_done,
                popup_message=PROGRESS_FINDING_PATH,
                cancelable=True,
                on_cancel=_on_cancel,
            )
        # for a "DNA" search, find the closest DNA markers to the newly selected person
        else:
            self._select_person_in_main_tree(indi_id)
            self._show_progress()
            self._set_busy(True)

            def _do_dna(cancel_event):
                return self._find_dna_result_data(
                    indi_id, top_n, max_depth, cancel_event=cancel_event)

            def _on_cancel():
                self._hide_progress()
                self._set_busy(False)

            def _on_done(result, error):
                self._hide_search_popup()
                self._hide_progress()
                self._set_busy(False)
                if error:
                    messagebox.showerror(ERR_PARSE_TITLE, str(error))
                    return
                results, home_paths = result
                self._last_result = {
                    'type': 'dna_matches', 'start_id': indi_id}
                self._render_results(indi_id, results, home_paths=home_paths)

            self._run_background_task(
                _do_dna,
                _on_done,
                popup_message=(
                    PROGRESS_SEARCHING
                    if self._is_slow_search(max_depth, len(self.individuals))
                    else None
                ),
                cancelable=True,
                on_cancel=_on_cancel,
            )
    def _display_name(self, indi):
        """Return an individual's display name using the configured name order."""
        if self._name_order == 'last_first':
            surname = indi.get('surname', '')
            given = indi.get('given_name', '')
            if surname and given:
                return f"{surname}, {given}"
            if surname:
                return surname
        return indi['name'] or '(unknown)'
    def _get_family_members(self, indi_id):
        """Return (parents, siblings, spouses, children) lists for an individual."""
        indi = self.individuals[indi_id]
        parents, siblings, spouses, children = [], [], [], []
        for fam_id in indi['famc']:
            fam = self.families.get(fam_id)
            if not fam:
                continue
            for pid in (fam['husb'], fam['wife']):
                if pid and pid in self.individuals:
                    parents.append(pid)
            for sib_id in fam['chil']:
                if sib_id != indi_id and sib_id in self.individuals:
                    siblings.append(sib_id)
        for fam_id in indi['fams']:
            fam = self.families.get(fam_id)
            if not fam:
                continue
            spouse_id = fam['wife'] if fam['husb'] == indi_id else fam['husb']
            if spouse_id and spouse_id in self.individuals:
                spouses.append(spouse_id)
            for child_id in fam['chil']:
                if child_id in self.individuals:
                    children.append(child_id)
        return parents, siblings, spouses, children
