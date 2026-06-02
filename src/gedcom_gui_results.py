#!/usr/bin/env python3
"""
gedcom_gui_results.py

Result rendering, path reversal, person navigation, and family-summary helpers.
"""

import json
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

import customtkinter as ctk

from gedcom_display import describe, format_year
from gedcom_gui_graph_layout import GraphLayoutMixin
from gedcom_gui_graph_render import GraphRenderMixin
from gedcom_relationship import (
    PARENTAGE_ADOPTED,
    PARENTAGE_FOSTER,
    PARENTAGE_SEALING,
    PARENTAGE_STEP,
    biological_parent_ids,
    describe_relationship,
    get_ancestor_depths,
    get_descendant_depths,
    infer_step_sibling_ids,
    parent_child_relationship,
    sibling_relationship,
)
import gedcom_strings as gs
from gedcom_platform import filedialog_parent
from gedcom_tooltip import TextTagTooltip


class ResultsMixin(GraphRenderMixin, GraphLayoutMixin):
    """Render search results and handle result-pane navigation."""

    @staticmethod
    def _widget_exists(widget):
        """Return whether a Tk/CTk widget still exists."""
        try:
            winfo_exists = getattr(widget, 'winfo_exists', None)
            if winfo_exists is None:
                return True
            return bool(winfo_exists())
        except tk.TclError:
            return False

    def _set_results_header_for_person(self, indi_id):
        """Show the selected person's name in the Display Pane header."""
        start = self.individuals[indi_id]
        name = self._display_name(start)
        b, d = start.get('birth_year'), start.get('death_year')
        if b and d:
            lifespan = f" ({format_year(b)}–{format_year(d)})"
        elif b:
            lifespan = f" (b. {format_year(b)})"
        elif d:
            lifespan = f" (d. {format_year(d)})"
        else:
            lifespan = ""
        if self.show_ids.get():
            name += f" [{indi_id.strip('@')}]"
        self._results_header_var.set(name + lifespan)
        self._results_header_id = indi_id
        self._update_header_label_style()

    def _reverse_results(self):
        """Toggle reversed display of the current results."""
        if not self._last_result:
            return
        kind = self._last_result['type']
        if kind not in ('dna_matches', 'path'):
            return
        self._results_reversed = not self._results_reversed
        self._reverse_btn.configure(
            text=gs.BTN_REVERSE_RESTORE if self._results_reversed else gs.BTN_REVERSE)
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
                self._last_result.get('home_paths'),
            )

    def _render_profile_result(self, start_id, home_paths=None):
        """Render the selected person's profile in the Display Pane."""
        if start_id not in self.individuals:
            self._reset_results_pane()
            return
        if self._last_result and self._last_result.get('type') == 'profile':
            self._last_result['start_id'] = start_id
        w = self.results
        self._set_profile_gallery_button_visible(start_id)
        try:
            w.configure(state='normal')
            w.delete('1.0', 'end')
        except tk.TclError:
            return
        self._set_results_header_for_person(start_id)

        def _on_tag_click(tag_name):
            self.tag_keyword.set(tag_name)
            self.page_marker.set('')
            self.search_text.set('')
            self.filter_text.set('')
            self.show_flagged_only.set(True)

        home_path_data = home_paths
        if home_path_data is None:
            try:
                max_depth = int(self.max_depth.get())
            except (tk.TclError, ValueError):
                max_depth = 1
            home_path_data = self._profile_home_path_for_render(
                start_id, max_depth)
        if self._last_result and self._last_result.get('type') == 'profile':
            if not (isinstance(home_path_data, dict)
                    and home_path_data.get('loading')):
                self._last_result['home_paths'] = home_path_data

        self._insert_person_profile(
            w, start_id, self._navigate_to, tag_callback=_on_tag_click,
            home_paths=home_path_data)
        if not self._widget_exists(w):
            return
        self._reverse_btn.configure(state='disabled', text=gs.BTN_REVERSE)
        try:
            w.configure(state='disabled')
        except tk.TclError:
            return

    def _set_profile_gallery_button_visible(self, indi_id=None):
        """Show the Display Pane Gallery button for profile records with images."""
        button = getattr(self, '_profile_gallery_btn', None)
        if button is None:
            return
        visible = False
        if (self.display_mode.get() == 'profile' and indi_id
                and hasattr(self, '_profile_gallery_candidates')):
            visible = bool(self._profile_gallery_candidates(indi_id))
        try:
            if visible:
                button.grid()
            else:
                button.grid_remove()
        except tk.TclError:
            pass

    def _show_current_profile_gallery(self):
        """Open the gallery for the active Display Pane profile person."""
        if not self._last_result or self._last_result.get('type') != 'profile':
            return
        indi_id = self._last_result.get('start_id')
        if not indi_id:
            return
        self._show_profile_image_gallery(indi_id, parent=self.root)

    def _coerce_home_path_data(self, home_paths):
        """Normalize home-path payloads from old and new render callers."""
        if home_paths is None:
            return None
        if isinstance(home_paths, dict):
            return home_paths
        home_id = getattr(self, '_home_person_id', None)
        if not home_id or home_id not in self.individuals:
            return None
        return {'home_id': home_id, 'paths': home_paths}

    def _render_home_path_section(
            self, *home_path_args, nl, person, relationship_line,
            common_ancestor_line, separator=None, reverse=False):
        """Render the shared Path to Home Person section."""
        if len(home_path_args) == 1:
            home_paths = home_path_args[0]
        elif len(home_path_args) == 2:
            _start_id, home_paths = home_path_args
        else:
            raise TypeError(
                "_render_home_path_section expected home_paths "
                "or start_id, home_paths")
        home_data = self._coerce_home_path_data(home_paths)
        if not home_data:
            return False
        home_id = home_data['home_id']
        if separator is not None:
            separator()
        nl(gs.RESULT_PATH_SECTION, bold=True)
        person(home_id, prefix=gs.RESULT_HOME)
        if home_data.get('loading'):
            nl(gs.RESULT_HOME_PATH_LOADING)
            nl()
            return True
        paths = home_data.get('paths') or []
        if not paths:
            nl(gs.RESULT_NO_HOME_PATH)
            nl()
            return True

        raw_path = paths[0]
        if len(raw_path) <= 1:
            nl(gs.PATH_SAME_PERSON)
            nl()
            return True

        disp_path = (
            self._reverse_path(raw_path, self.individuals)
            if reverse else raw_path
        )
        rel_start_id = disp_path[0][0]
        ancestors = get_ancestor_depths(
            rel_start_id, self.individuals, self.families)
        descendants = get_descendant_depths(
            rel_start_id, self.individuals, self.families)
        rel = describe_relationship(
            disp_path, self.individuals,
            ancestors=ancestors, descendants=descendants,
            families=self.families)
        relationship_line(rel, disp_path)
        common_ancestor_line(self._model.find_common_ancestors(
            disp_path[0][0], disp_path[-1][0]))
        nl(gs.RESULT_PATH)
        for i, (node_id, edge) in enumerate(disp_path):
            if i == 0:
                person(node_id, prefix="  ")
            else:
                person(node_id, prefix=self._path_edge_prefix(edge, "    "))
        nl()
        return True

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
            relationship_tooltip = TextTagTooltip(tw, gs.TIP_RELATIONSHIP)
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
            w.insert('end', gs.RESULT_RELATIONSHIP.format(rel=rel),
                     ('relationship_link', tag))
            tw.tag_bind(
                tag, '<Button-1>',
                lambda _, p=tuple(path), r=rel: self._show_path_graph(p, r))
            w.insert('end', '\n')

        def common_ancestor_line(ancestor_ids, prefix='', item_prefix='    '):
            if prefix:
                w.insert('end', prefix)
            if not ancestor_ids:
                w.insert('end', gs.RESULT_COMMON_ANCESTOR)
                w.insert('end', gs.RESULT_COMMON_ANCESTOR_NONE)
                w.insert('end', '\n')
                return
            if len(ancestor_ids) == 1:
                w.insert('end', gs.RESULT_COMMON_ANCESTOR)
                person_inline(ancestor_ids[0])
                w.insert('end', '\n')
                return
            w.insert('end', gs.RESULT_COMMON_ANCESTORS + '\n')
            for ancestor_id in ancestor_ids:
                person_inline(ancestor_id, prefix=item_prefix)
                w.insert('end', '\n')

        result_detail_indent = "   "
        result_edge_indent = "       "
        start = self.individuals[start_id]
        self._set_results_header_for_person(start_id)

        nl(gs.RESULT_CLOSEST_MATCHES, bold=True)
        if start['dna_markers']:
            nl(gs.RESULT_DNA_FLAGGED_NOTE)
            for m in start['dna_markers']:
                nl(f"    - {self._format_marker(m)}")
        nl()

        if not results:
            nl(gs.RESULT_NO_DNA_FOUND)
        else:
            if self._results_reversed:
                for rank, (_, path) in enumerate(results, 1):
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
                           prefix=gs.RESULT_RANK_PREFIX.format(rank=rank), bold=True)
                    relationship_line(
                        rel, rev_path, prefix=result_detail_indent)
                    common_ancestor_line(
                        self._model.find_common_ancestors(
                            rev_path[0][0], rev_path[-1][0]),
                        prefix=result_detail_indent,
                        item_prefix="     ")
                    nl(result_detail_indent + gs.RESULT_PATH)
                    for i, (node_id, edge) in enumerate(rev_path):
                        if i == 0:
                            person(node_id, prefix="     ")
                        else:
                            person(node_id, prefix=self._path_edge_prefix(
                                edge, result_edge_indent))
                    nl(gs.RESULT_DNA_MARKERS)
                    for m in self.individuals[match_id]['dna_markers']:
                        nl(f"     - {self._format_marker(m)}")
                    hr()
            else:
                ancestors = get_ancestor_depths(
                    start_id, self.individuals, self.families)
                descendants = get_descendant_depths(
                    start_id, self.individuals, self.families)
                for rank, (_, path) in enumerate(results, 1):
                    end_id = path[-1][0]
                    person(end_id,
                           prefix=gs.RESULT_RANK_PREFIX.format(rank=rank),
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
                    nl(result_detail_indent + gs.RESULT_PATH)
                    for i, (node_id, edge) in enumerate(path):
                        if i == 0:
                            person(node_id, prefix="     ")
                        else:
                            person(node_id, prefix=self._path_edge_prefix(
                                edge, result_edge_indent))
                    nl(gs.RESULT_DNA_MARKERS)
                    for m in self.individuals[end_id]['dna_markers']:
                        nl(f"     - {self._format_marker(m)}")
                    hr()

        # Family section
        nl(gs.FAM_SECTION, bold=True)
        family_found = False
        parents, siblings, spouses, children = self._get_family_members(
            start_id)

        if parents:
            family_found = True
            nl(gs.FAM_PARENTS)
            for pid in parents:
                person(pid, prefix="    ")
        if siblings:
            family_found = True
            nl(gs.FAM_SIBLINGS)
            for sib_id in siblings:
                person(sib_id, prefix="    ")
        if spouses:
            family_found = True
            nl(gs.FAM_SPOUSES if len(spouses) > 1 else gs.FAM_SPOUSE)
            for sid in spouses:
                person(sid, prefix="    ")
        if children:
            family_found = True
            nl(gs.FAM_CHILDREN)
            for child_id in children:
                person(child_id, prefix="    ")
        if not family_found:
            nl(gs.FAM_NO_INFO)
        nl()

        self._render_home_path_section(
            home_paths,
            nl=nl,
            person=person,
            relationship_line=relationship_line,
            common_ancestor_line=common_ancestor_line,
            separator=hr,
            reverse=self._results_reversed,
        )

        self._reverse_btn.configure(state='normal')
        w.configure(state='disabled')
    def _show_results_header_menu(self, event):
        """Show a right-click context menu on the results pane title bar."""
        indi_id = getattr(self, '_results_header_id', None)
        if not indi_id:
            return 'break'
        if indi_id not in self.individuals:
            self._results_header_id = None
            self._results_header_var.set('')
            self._update_header_label_style()
            return 'break'
        _menu_kw = {'font': tkfont.nametofont('TkMenuFont')} if sys.platform == 'win32' else {}
        menu = tk.Menu(self._results_header_label, tearoff=0, **_menu_kw)

        def _copy_name():
            self.root.clipboard_clear()
            self.root.clipboard_append(
                self._display_name(self.individuals[indi_id]))
            if self.show_ids.get():
                self.root.clipboard_append(f" ({indi_id})")

        menu.add_command(
            label=gs.RESULTS_HEADER_MENU_COPY_NAME,
            command=_copy_name)
        menu.add_command(
            label=gs.RESULTS_HEADER_MENU_SHOW_PROFILE,
            command=lambda: self._show_person_for(indi_id, initial_view='profile'))
        menu.add_command(
            label=gs.RESULTS_HEADER_MENU_SHOW_TREE,
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
            parent=filedialog_parent(self.root),
            title=gs.DLG_SAVE_RESULTS,
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
                gs.ERR_SAVE_GRAPH_TITLE,
                gs.ERR_SAVE_RESULTS_MSG.format(error=exc),
                parent=self.root,
            )
    def _copy_paths_json(self):
        """Copy current path results as JSON to clipboard (debug mode only)."""
        if not self._last_result or self._last_result.get('type') != 'path':
            return
        from gedcom_display import describe as _describe
        from gedcom_relationship import (
            describe_relationship as _desc_rel,
            get_ancestor_depths,
            get_descendant_depths,
        )
        start_id = self._last_result.get('start_id', '')
        end_id = self._last_result.get('end_id', '')
        paths = self._last_result.get('paths', [])
        ancestors = get_ancestor_depths(start_id, self.individuals, self.families)
        descendants = get_descendant_depths(start_id, self.individuals, self.families)
        out = {
            'start': {'id': start_id,
                      'name': _describe(self.individuals.get(start_id, {}))},
            'end': {'id': end_id,
                    'name': _describe(self.individuals.get(end_id, {}))},
            'paths': [],
        }
        for path in paths:
            label = _desc_rel(path, self.individuals,
                              ancestors=ancestors,
                              descendants=descendants,
                              families=self.families)
            nodes = []
            for node_id, edge in path:
                indi = self.individuals.get(node_id, {})
                nodes.append({
                    'id': node_id,
                    'name': _describe(indi),
                    'sex': indi.get('sex', ''),
                    'edge': edge,
                })
            out['paths'].append({'label': label, 'nodes': nodes})
        self.root.clipboard_clear()
        self.root.clipboard_append(json.dumps(out, indent=2, ensure_ascii=False))

    def _reset_results_pane(self):
        """Reset invalid result state after the underlying person data changes."""
        self.results.configure(state='normal')
        self.results.delete('1.0', 'end')
        self.results.configure(state='disabled')
        self._results_header_var.set('')
        self._results_header_id = None
        self._update_header_label_style()
        self._last_result = None
        self._results_reversed = False
        self._reverse_btn.configure(state='disabled', text=gs.BTN_REVERSE)

    def _format_marker(self, marker):
        """Strip the trailing (@ref@) from a DNA marker string when Show IDs is off."""
        if self.show_ids.get():
            return marker
        return re.sub(r'\s*\(@[^@]+@\)\s*$', '', marker)
    def _clear_person_tags(self, widget):
        """Remove generated person-link tags from a Text-like widget."""
        tw = getattr(widget, '_textbox', widget)
        for tag in tw.tag_names():
            if (tag.startswith('pers_') or
                    tag.startswith('path_graph_') or
                    (tag.startswith('gedcom_url_') and
                     tag != 'gedcom_url_link')):
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
            old_suppress = getattr(self, '_suppress_display_refresh', False)
            self._suppress_display_refresh = True
            try:
                self.tree.selection_set(indi_id)
                self.tree.see(indi_id)
                self.tree.focus(indi_id)
            finally:
                self._suppress_display_refresh = old_suppress
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
            'display_mode': self.display_mode.get(),
            'display_path_target_id': getattr(self, '_display_path_target_id', None),
        }
    def _nav_restore(self, snapshot):
        """Apply a navigation snapshot and re-render results."""
        self._last_result = snapshot['last_result']
        self._active_id = snapshot['active_id']
        self._results_reversed = snapshot['results_reversed']
        self._display_path_target_id = snapshot.get('display_path_target_id')
        self._set_display_mode(
            snapshot.get('display_mode', 'profile'),
            refresh=False,
            prompt_for_path=False,
        )
        self._reverse_btn.configure(
            text=gs.BTN_REVERSE_RESTORE if self._results_reversed else gs.BTN_REVERSE)
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
                self._last_result.get('home_paths'),
            )
        elif kind == 'profile':
            self._render_profile_result(
                self._last_result['start_id'],
                self._last_result.get('home_paths'),
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
        if indi_id not in self.individuals:
            self._reset_results_pane()
            return

        if self._last_result:
            self._nav_history.append(self._nav_snapshot())
            self._nav_forward.clear()

        self._select_person_in_main_tree(indi_id)

        # reset "reverse" button and refresh the active Display Pane mode
        self._results_reversed = False
        self._reverse_btn.configure(text=gs.BTN_REVERSE)
        self._refresh_display_pane()
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
        members = self._get_family_member_entries(indi_id)
        return (
            [entry['id'] for entry in members['parents']],
            [entry['id'] for entry in members['siblings']],
            [entry['id'] for entry in members['spouses']],
            [entry['id'] for entry in members['children']],
        )

    def _get_family_member_entries(self, indi_id):
        """Return labeled family member entries for profile and graph views."""
        indi = self.individuals[indi_id]
        parents, siblings, spouses, children = [], [], [], []
        seen_parents, seen_siblings, seen_spouses, seen_children = (
            set(), set(), set(), set())
        for fam_id in indi['famc']:
            fam = self.families.get(fam_id)
            if not fam:
                continue
            for pid in (fam['husb'], fam['wife']):
                if pid and pid in self.individuals and pid not in seen_parents:
                    parents.append({
                        'id': pid,
                        'kind': parent_child_relationship(
                            pid, indi_id, self.individuals, self.families),
                        'role': self._parent_role_label(pid, indi_id),
                    })
                    seen_parents.add(pid)
            for sib_id in fam['chil']:
                if (sib_id != indi_id and sib_id in self.individuals
                        and sib_id not in seen_siblings):
                    siblings.append({
                        'id': sib_id,
                        'kind': sibling_relationship(
                            indi_id, sib_id, self.individuals, self.families),
                        'role': self._sibling_role_label(indi_id, sib_id),
                    })
                    seen_siblings.add(sib_id)
        for parent_id in biological_parent_ids(
                indi_id, self.individuals, self.families):
            parent = self.individuals.get(parent_id, {})
            for fam_id in parent.get('fams', ()):
                fam = self.families.get(fam_id)
                if not fam:
                    continue
                for sib_id in fam.get('chil', ()):
                    if (sib_id != indi_id and sib_id in self.individuals
                            and sib_id not in seen_siblings):
                        siblings.append({
                            'id': sib_id,
                            'kind': sibling_relationship(
                                indi_id, sib_id, self.individuals,
                                self.families),
                            'role': self._sibling_role_label(
                                indi_id, sib_id),
                        })
                        seen_siblings.add(sib_id)
        for sib_id in infer_step_sibling_ids(
                indi_id, self.individuals, self.families):
            if sib_id in self.individuals and sib_id not in seen_siblings:
                siblings.append({
                    'id': sib_id,
                    'kind': 'step',
                    'role': self._sibling_role_label(indi_id, sib_id),
                })
                seen_siblings.add(sib_id)
        for fam_id in indi['fams']:
            fam = self.families.get(fam_id)
            if not fam:
                continue
            spouse_id = fam['wife'] if fam['husb'] == indi_id else fam['husb']
            if (spouse_id and spouse_id in self.individuals
                    and spouse_id not in seen_spouses):
                spouses.append({'id': spouse_id, 'kind': 'spouse', 'role': ''})
                seen_spouses.add(spouse_id)
            for child_id in fam['chil']:
                if child_id in self.individuals and child_id not in seen_children:
                    children.append({
                        'id': child_id,
                        'kind': parent_child_relationship(
                            indi_id, child_id, self.individuals, self.families),
                        'role': self._child_role_label(indi_id, child_id),
                    })
                    seen_children.add(child_id)
        return {
            'parents': parents,
            'siblings': siblings,
            'spouses': spouses,
            'children': children,
        }

    def _parent_role_label(self, parent_id, child_id):
        kind = parent_child_relationship(
            parent_id, child_id, self.individuals, self.families)
        sex = self.individuals.get(parent_id, {}).get('sex', '')
        if kind == PARENTAGE_STEP:
            return self._sex_role(
                sex, gs.FAM_ROLE_STEP_FATHER, gs.FAM_ROLE_STEP_MOTHER,
                gs.FAM_ROLE_STEP_PARENT)
        if kind == PARENTAGE_ADOPTED:
            return self._sex_role(
                sex, gs.FAM_ROLE_ADOPTIVE_FATHER,
                gs.FAM_ROLE_ADOPTIVE_MOTHER, gs.FAM_ROLE_ADOPTIVE_PARENT)
        if kind in (PARENTAGE_FOSTER, PARENTAGE_SEALING):
            return self._sex_role(
                sex, gs.FAM_ROLE_FOSTER_FATHER, gs.FAM_ROLE_FOSTER_MOTHER,
                gs.FAM_ROLE_FOSTER_PARENT)
        return self._sex_role(
            sex, gs.FAM_ROLE_FATHER, gs.FAM_ROLE_MOTHER, gs.FAM_ROLE_PARENT)

    def _child_role_label(self, parent_id, child_id):
        kind = parent_child_relationship(
            parent_id, child_id, self.individuals, self.families)
        sex = self.individuals.get(child_id, {}).get('sex', '')
        if kind == PARENTAGE_STEP:
            return self._sex_role(
                sex, gs.FAM_ROLE_STEP_SON, gs.FAM_ROLE_STEP_DAUGHTER,
                gs.FAM_ROLE_STEP_CHILD)
        if kind == PARENTAGE_ADOPTED:
            return self._sex_role(
                sex, gs.FAM_ROLE_ADOPTED_SON, gs.FAM_ROLE_ADOPTED_DAUGHTER,
                gs.FAM_ROLE_ADOPTED_CHILD)
        if kind in (PARENTAGE_FOSTER, PARENTAGE_SEALING):
            return self._sex_role(
                sex, gs.FAM_ROLE_FOSTER_SON, gs.FAM_ROLE_FOSTER_DAUGHTER,
                gs.FAM_ROLE_FOSTER_CHILD)
        return self._sex_role(
            sex, gs.FAM_ROLE_SON, gs.FAM_ROLE_DAUGHTER, gs.FAM_ROLE_CHILD)

    def _sibling_role_label(self, left_id, right_id):
        relation = sibling_relationship(
            left_id, right_id, self.individuals, self.families)
        sex = self.individuals.get(right_id, {}).get('sex', '')
        if relation == 'half':
            return self._sex_role(
                sex, gs.FAM_ROLE_HALF_BROTHER, gs.FAM_ROLE_HALF_SISTER,
                gs.FAM_ROLE_HALF_SIBLING)
        if relation == 'step':
            return self._sex_role(
                sex, gs.FAM_ROLE_STEP_BROTHER, gs.FAM_ROLE_STEP_SISTER,
                gs.FAM_ROLE_STEP_SIBLING)
        if relation == PARENTAGE_ADOPTED:
            return gs.FAM_ROLE_ADOPTIVE_SIBLING
        if relation in (PARENTAGE_FOSTER, PARENTAGE_SEALING):
            return gs.FAM_ROLE_FOSTER_SIBLING
        return self._sex_role(
            sex, gs.FAM_ROLE_BROTHER, gs.FAM_ROLE_SISTER, gs.FAM_ROLE_SIBLING)

    @staticmethod
    def _sex_role(sex, male, female, neutral):
        if sex == 'M':
            return male
        if sex == 'F':
            return female
        return neutral

    def _edge_relationship_kind(self, source_id, target_id, category):
        """Return ordinary/step/half/adopted/foster style kind for a graph edge."""
        if category == 'parents':
            return parent_child_relationship(
                target_id, source_id, self.individuals, self.families)
        if category == 'children':
            return parent_child_relationship(
                source_id, target_id, self.individuals, self.families)
        if category == 'siblings':
            return sibling_relationship(
                source_id, target_id, self.individuals, self.families)
        return category

    def _combined_parent_child_kind(self, parent_ids, child_id):
        """Return the strongest visible parent-child style for a child connector."""
        priority = {
            PARENTAGE_STEP: 1,
            PARENTAGE_ADOPTED: 2,
            PARENTAGE_FOSTER: 3,
            PARENTAGE_SEALING: 4,
            'guardian': 5,
            'other': 6,
            'birth': 99,
            None: 99,
        }
        best = 'birth'
        best_score = priority[best]
        for parent_id in parent_ids:
            kind = self._edge_relationship_kind(parent_id, child_id, 'children')
            score = priority.get(kind, 90)
            if score < best_score:
                best = kind
                best_score = score
        return best
