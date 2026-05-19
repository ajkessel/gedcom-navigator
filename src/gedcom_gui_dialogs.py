"""
gedcom_gui_dialogs.py

DialogsMixin — person detail, tag picker, person picker, path finder,
preferences, and documentation windows for DNAMatchFinderApp.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog
import os
import sys
import threading
import webbrowser
import customtkinter as ctk

from gedcom_display import describe
from gedcom_family_tree import INITIAL_TREE_CATEGORIES
from gedcom_name_search import individual_matches_query
from gedcom_relationship import (
    _extract_event, get_ancestor_depths, get_descendant_depths,
    describe_relationship,
)
from gedcom_markdown import render_markdown
from gedcom_strings import *  # noqa: F401,F403
from gedcom_theme import get_flag_bg
from gedcom_tooltip import Tooltip
from gedcom_update import check_for_updates
from gedcom_zoom import TextZoomController, bind_zoom_shortcuts


class DialogsMixin:
    """Mixin providing dialog and documentation window methods."""

    def _show_person(self, initial_view=None):
        """Open the GEDCOM record viewer for the selected person."""
        if not self.individuals:
            messagebox.showwarning(ERR_NO_DATA_TITLE, ERR_NO_DATA_MSG)
            return
        sel = self.tree.selection()
        indi_id = sel[0] if sel else self._active_id
        if not indi_id:
            messagebox.showwarning(ERR_NO_SEL_TITLE, ERR_NO_SEL_MSG)
            return
        self._show_person_for(indi_id, initial_view=initial_view)

    def _update_show_person_btn_for_shift(self, shift_held):
        """Temporarily flip show_person_btn label/command while Shift is held."""
        if self._default_profile_view == 'tree':
            if shift_held:
                self.show_person_btn.configure(
                    text=BTN_SHOW_PERSON,
                    command=lambda: self._show_person(initial_view='profile'))
                self._show_person_tooltip.update_text(TIP_SHOW_PERSON)
            else:
                self.show_person_btn.configure(
                    text=BTN_SHOW_PERSON_TREE, command=self._show_person)
                self._show_person_tooltip.update_text(TIP_SHOW_PERSON_TREE)
        else:
            if shift_held:
                self.show_person_btn.configure(
                    text=BTN_SHOW_PERSON_TREE,
                    command=lambda: self._show_person(initial_view='tree'))
                self._show_person_tooltip.update_text(TIP_SHOW_PERSON_TREE)
            else:
                self.show_person_btn.configure(
                    text=BTN_SHOW_PERSON, command=self._show_person)
                self._show_person_tooltip.update_text(TIP_SHOW_PERSON)

    def _show_person_for(self, indi_id, initial_view=None,
                         existing_window=None):
        """Open a detail window for a specific individual ID."""
        if existing_window is None:
            existing = getattr(self, '_secondary_win', None)
            if existing is not None:
                try:
                    if existing.winfo_exists():
                        existing_window = existing
                    else:
                        self._secondary_win = None
                        self._path_graph_win = None
                        self._path_graph_replace_fn = None
                except tk.TclError:
                    self._secondary_win = None
                    self._path_graph_win = None
                    self._path_graph_replace_fn = None
        reuse_window = existing_window is not None
        if reuse_window:
            win = existing_window
            if getattr(self, '_path_graph_win', None) is win:
                self._path_graph_win = None
                self._path_graph_replace_fn = None
            for sequence in self._reused_person_window_bindings():
                try:
                    win.unbind(sequence)
                except tk.TclError:
                    pass
            try:
                win.unbind('<Configure>')
            except tk.TclError:
                pass
            for child in win.winfo_children():
                child.destroy()
        else:
            win = ctk.CTkToplevel(self.root)
            self._secondary_win = win
            win.withdraw()
        win.resizable(True, True)
        if sys.platform != 'win32':
            win.transient(self.root)

        _geo_after = [None]

        def _on_win_configure(event):
            if event.widget is not win:
                return
            if _geo_after[0]:
                win.after_cancel(_geo_after[0])
            _geo_after[0] = win.after(
                400, lambda: self._persist_show_person_geometry(win))

        def _on_destroy_person_win(*_):
            if getattr(self, '_secondary_win', None) is win:
                self._secondary_win = None
            if getattr(self, '_path_graph_win', None) is win:
                self._path_graph_win = None
                self._path_graph_replace_fn = None
            win.destroy()

        win.bind('<Escape>', _on_destroy_person_win)
        win.protocol('WM_DELETE_WINDOW', _on_destroy_person_win)

        content_frame = ctk.CTkFrame(win, fg_color='transparent')
        content_frame.pack(fill='both', expand=True)
        btn_frame = ctk.CTkFrame(win, fg_color='transparent')
        btn_frame.pack(fill='x', pady=(4, 8))

        copy_shortcut = '<Command-c>' if sys.platform == 'darwin' else '<Control-c>'
        save_shortcut = '<Command-s>' if sys.platform == 'darwin' else '<Control-s>'
        toggle_shortcut = '<Command-t>' if sys.platform == 'darwin' else '<Control-t>'
        state = {
            'person_id': indi_id,
            'mode': 'person',
            'tree_expanded': [(indi_id, cat) for cat in INITIAL_TREE_CATEGORIES],
            'tree_zoom': 1.0,
            'zoom_controller': None,
            'history': [],
            'forward': [],
        }

        def _clear_content():
            for child in content_frame.winfo_children():
                child.destroy()

        def _clear_buttons():
            for child in btn_frame.winfo_children():
                child.destroy()

        def _bind_text_navigation(text_widget):
            win.bind(
                '<Up>',
                lambda *_: text_widget.yview_scroll(-1, 'units') or 'break')
            win.bind(
                '<Down>',
                lambda *_: text_widget.yview_scroll(1, 'units') or 'break')
            win.bind(
                '<Prior>',
                lambda *_: text_widget.yview_scroll(-1, 'pages') or 'break')
            win.bind(
                '<Next>',
                lambda *_: text_widget.yview_scroll(1, 'pages') or 'break')
            win.bind(
                '<Home>', lambda *_: text_widget.yview_moveto(0) or 'break')
            win.bind(
                '<End>', lambda *_: text_widget.yview_moveto(1) or 'break')

        def _bind_canvas_navigation(canvas):
            win.bind(
                '<Up>', lambda *_: canvas.yview_scroll(-1, 'units') or 'break')
            win.bind(
                '<Down>',
                lambda *_: canvas.yview_scroll(1, 'units') or 'break')
            win.bind(
                '<Prior>',
                lambda *_: canvas.yview_scroll(-1, 'pages') or 'break')
            win.bind(
                '<Next>',
                lambda *_: canvas.yview_scroll(1, 'pages') or 'break')
            win.bind(
                '<Home>',
                lambda *_: (
                    canvas.xview_moveto(0), canvas.yview_moveto(0), 'break'
                )[-1])
            win.bind(
                '<End>',
                lambda *_: (
                    canvas.xview_moveto(1), canvas.yview_moveto(1), 'break'
                )[-1])

        def _bind_tree_mouse_navigation(canvas):
            drag_state = {'x': 0, 'y': 0}
            canvas._family_tree_dragged = False

            def _scroll_units(event):
                delta = getattr(event, 'delta', 0)
                if not delta:
                    return 0
                if abs(delta) >= 120:
                    return int(-delta / 120)
                return -1 if delta > 0 else 1

            def _on_mouse_wheel(event):
                if getattr(event, 'state', 0):
                    return None
                units = _scroll_units(event)
                if units:
                    canvas.yview_scroll(units, 'units')
                return 'break'

            def _on_linux_wheel_up(event):
                if getattr(event, 'state', 0):
                    return None
                canvas.yview_scroll(-1, 'units')
                return 'break'

            def _on_linux_wheel_down(event):
                if getattr(event, 'state', 0):
                    return None
                canvas.yview_scroll(1, 'units')
                return 'break'

            def _on_drag_start(event):
                canvas.focus_set()
                drag_state['x'] = event.x
                drag_state['y'] = event.y
                canvas._family_tree_dragged = False
                canvas.scan_mark(event.x, event.y)

            def _on_drag_motion(event):
                if (abs(event.x - drag_state['x']) > 3 or
                        abs(event.y - drag_state['y']) > 3):
                    canvas._family_tree_dragged = True
                canvas.scan_dragto(event.x, event.y, gain=1)
                return 'break'

            def _on_drag_release(_event):
                canvas.after_idle(
                    lambda: setattr(canvas, '_family_tree_dragged', False))

            canvas.bind('<MouseWheel>', _on_mouse_wheel, add='+')
            canvas.bind('<Button-4>', _on_linux_wheel_up, add='+')
            canvas.bind('<Button-5>', _on_linux_wheel_down, add='+')
            canvas.bind('<ButtonPress-1>', _on_drag_start, add='+')
            canvas.bind('<B1-Motion>', _on_drag_motion, add='+')
            canvas.bind('<ButtonRelease-1>', _on_drag_release, add='+')

        def _render_person_buttons(show_tree_view, copy_profile, save_profile):
            _clear_buttons()
            ctk.CTkButton(
                btn_frame, text=BTN_CLOSE, width=80,
                command=win.destroy).pack(side='right', padx=8)
            tree_btn = ctk.CTkButton(
                btn_frame, text=BTN_TREE_VIEW, width=90,
                command=show_tree_view)
            tree_btn.pack(side='right', padx=(0, 8))
            Tooltip(tree_btn, TIP_TREE_VIEW_BTN)
            copy_btn = ctk.CTkButton(
                btn_frame, text=BTN_COPY_GRAPH, width=80, command=copy_profile)
            copy_btn.pack(side='right', padx=(0, 8))
            Tooltip(copy_btn, TIP_COPY_PROFILE)
            save_btn = ctk.CTkButton(
                btn_frame, text=BTN_SAVE_GRAPH, width=80, command=save_profile)
            save_btn.pack(side='right', padx=(0, 8))
            Tooltip(save_btn, TIP_SAVE_PROFILE)

        def _render_tree_buttons(show_person_view, copy_graph, save_graph,
                                 save_debug=None):
            _clear_buttons()
            ctk.CTkButton(
                btn_frame, text=BTN_CLOSE, width=80,
                command=win.destroy).pack(side='right', padx=8)
            person_btn = ctk.CTkButton(
                btn_frame, text=BTN_PERSON_VIEW, width=100,
                command=show_person_view)
            person_btn.pack(side='right', padx=(0, 8))
            Tooltip(person_btn, TIP_PERSON_VIEW_BTN)
            copy_btn = ctk.CTkButton(
                btn_frame, text=BTN_COPY_GRAPH, width=80, command=copy_graph)
            copy_btn.pack(side='right', padx=(0, 8))
            Tooltip(copy_btn, TIP_COPY_GRAPH)
            save_btn = ctk.CTkButton(
                btn_frame, text=BTN_SAVE_GRAPH, width=80, command=save_graph)
            save_btn.pack(side='right', padx=(0, 8))
            Tooltip(save_btn, TIP_SAVE_GRAPH)
            if save_debug:
                debug_btn = ctk.CTkButton(
                    btn_frame, text=BTN_DEBUG_GRAPH, width=100,
                    command=save_debug)
                debug_btn.pack(side='right', padx=(0, 8))
                Tooltip(debug_btn, TIP_DEBUG_GRAPH)

        back_seq = '<Command-Left>' if sys.platform == 'darwin' else '<Alt-Left>'
        fwd_seq = '<Command-Right>' if sys.platform == 'darwin' else '<Alt-Right>'

        def _go_back():
            if state['history']:
                state['forward'].append(state['person_id'])
                state['person_id'] = state['history'].pop()
                _show_person_view()

        def _go_forward():
            if state['forward']:
                state['history'].append(state['person_id'])
                state['person_id'] = state['forward'].pop()
                _show_person_view()

        def _show_person_view(iid=None):
            if iid is not None:
                state['history'].append(state['person_id'])
                state['forward'].clear()
                state['person_id'] = iid
            current_id = state['person_id']
            state['mode'] = 'person'
            _clear_content()
            text = ctk.CTkTextbox(
                content_frame, font=(self._mono_family, self._mono_size),
                wrap='none')
            text._textbox.configure(padx=8, pady=8)
            text.pack(fill='both', expand=True)
            text._textbox.tag_configure(
                'bold', font=(self._mono_family, self._mono_size, 'bold'))
            text._textbox.tag_configure('person_link')
            text._textbox.tag_bind(
                'person_link', '<Enter>',
                lambda *_: text._textbox.config(cursor='hand2'))
            text._textbox.tag_bind(
                'person_link', '<Leave>',
                lambda *_: text._textbox.config(cursor=''))
            text._textbox.tag_configure('tag_link')
            text._textbox.tag_bind(
                'tag_link', '<Enter>',
                lambda *_: text._textbox.config(cursor='hand2'))
            text._textbox.tag_bind(
                'tag_link', '<Leave>',
                lambda *_: text._textbox.config(cursor=''))

            def _apply_person_zoom(size):
                text.configure(font=(self._mono_family, size))
                text._textbox.tag_configure(
                    'bold', font=(self._mono_family, size, 'bold'))

            state['zoom_controller'] = TextZoomController(
                text, self._mono_size, _apply_person_zoom,
                targets=(text._textbox,))
            _bind_text_navigation(text)
            win.bind(back_seq, lambda *_: _go_back() or 'break')
            win.bind(fwd_seq, lambda *_: _go_forward() or 'break')

            indi = self.individuals[current_id]
            win.title(WIN_GEDCOM_RECORD.format(
                name=indi['name'] or current_id))
            text.configure(state='normal')
            text.delete('1.0', 'end')
            self._clear_person_tags(text)

            def add(line, bold=False):
                text.insert('end', line + '\n', ('bold',) if bold else ())

            def person(pid, prefix=''):
                if prefix:
                    text.insert('end', prefix)
                tag = f'pers_{pid.strip("@")}'
                text.insert('end', describe(self.individuals[pid],
                                            show_id=self.show_ids.get()),
                            ('person_link', tag))
                text._textbox.tag_configure(tag, foreground=self._link_color)
                text._textbox.tag_bind(tag, '<Button-1>',
                                       lambda _, p=pid: _show_person_view(p))
                text.insert('end', '\n')

            add(BIO_SECTION, bold=True)
            bio_found = False

            def fmt_event(date, place):
                parts = [p for p in (date, place) if p]
                return ', '.join(parts)

            b_date, b_place = _extract_event(indi['_raw'], 'BIRT')
            if b_date or b_place:
                bio_found = True
                add(BIO_BORN.format(event=fmt_event(b_date, b_place)))

            for fam_id in indi['fams']:
                fam = self.families.get(fam_id)
                if not fam:
                    continue
                m_date = fam.get('marr_date', '')
                m_place = fam.get('marr_place', '')
                spouse_id = (
                    fam['wife'] if fam['husb'] == current_id else fam['husb'])
                spouse_name = (self._display_name(self.individuals[spouse_id])
                               if spouse_id and spouse_id in self.individuals else '')
                if spouse_name or m_date or m_place:
                    bio_found = True
                    parts = [p for p in (spouse_name, m_date, m_place) if p]
                    add(BIO_MARRIED.format(spouses=', '.join(parts)))

            d_date, d_place = _extract_event(indi['_raw'], 'DEAT')
            if d_date or d_place:
                bio_found = True
                add(BIO_DIED.format(event=fmt_event(d_date, d_place)))

            bu_date, bu_place = _extract_event(indi['_raw'], 'BURI')
            if bu_date or bu_place:
                bio_found = True
                add(BIO_BURIED.format(event=fmt_event(bu_date, bu_place)))

            if not bio_found:
                add(BIO_NO_INFO)
            add("")

            add(FAM_SECTION, bold=True)
            family_found = False
            parents, siblings, spouses, children = self._get_family_members(
                current_id)

            if parents:
                family_found = True
                add(FAM_PARENTS)
                for pid in parents:
                    person(pid, prefix="    ")
            if siblings:
                family_found = True
                add(FAM_SIBLINGS)
                for sib_id in siblings:
                    person(sib_id, prefix="    ")
            if spouses:
                family_found = True
                add(FAM_SPOUSES if len(spouses) > 1 else FAM_SPOUSE)
                for sid in spouses:
                    person(sid, prefix="    ")
            if children:
                family_found = True
                add(FAM_CHILDREN)
                for child_id in children:
                    person(child_id, prefix="    ")
            if not family_found:
                add(FAM_NO_INFO)
            add("")

            indi_tags = indi.get('tags', [])
            if indi_tags:
                add(TAGS_SECTION, bold=True)
                for i, tag_name in enumerate(indi_tags):
                    tlink = f'taglink_{i}'
                    text.insert('end', '  ')
                    text.insert('end', tag_name, ('tag_link', tlink))
                    text.insert('end', '\n')
                    text._textbox.tag_configure(
                        tlink, foreground=self._link_color)

                    def _on_tag_click(_, n=tag_name):
                        self.tag_keyword.set(n)
                        self.page_marker.set('')
                        self.search_text.set('')
                        self.filter_text.set('')
                        self.show_flagged_only.set(True)
                        win.destroy()

                    text._textbox.tag_bind(tlink, '<Button-1>', _on_tag_click)
                add("")

            add(GEDCOM_SECTION, bold=True)

            for level, xref, tag, value in indi.get('_raw', []):
                parts = [str(level)]
                if xref and self.show_ids.get():
                    parts.append(xref)
                parts.append(tag)
                if value:
                    parts.append(value)
                add(' '.join(parts))

            text.configure(state='disabled')

            def _profile_content():
                body = text.get('1.0', 'end').rstrip()
                title = win.title().strip()
                return (title + '\n\n' + body) if title else body

            def _copy_profile(*_):
                content = _profile_content()
                if not content:
                    return 'break'
                win.clipboard_clear()
                win.clipboard_append(content)
                return 'break'

            def _save_profile(*_):
                content = _profile_content()
                if not content:
                    return 'break'
                path = filedialog.asksaveasfilename(
                    parent=win,
                    title=DLG_SAVE_PROFILE,
                    defaultextension='.txt',
                    filetypes=[
                        ("Text files", "*.txt"),
                        ("All files", "*.*"),
                    ],
                )
                if not path:
                    return 'break'
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                        f.write('\n')
                except OSError as exc:
                    messagebox.showerror(
                        ERR_SAVE_GRAPH_TITLE,
                        ERR_SAVE_PROFILE_MSG.format(error=exc),
                        parent=win,
                    )
                return 'break'

            win.bind(copy_shortcut, _copy_profile)
            win.bind(save_shortcut, _save_profile)
            _render_person_buttons(
                lambda: _show_tree_view(state['person_id']),
                _copy_profile,
                _save_profile,
            )
            text.focus_set()

        def _show_tree_view(iid=None):
            if iid is not None:
                state['person_id'] = iid
            state['mode'] = 'tree'
            state['tree_expanded'] = [
                (state['person_id'], cat) for cat in INITIAL_TREE_CATEGORIES]
            _clear_content()
            indi = self.individuals[state['person_id']]
            win.title(WIN_FAMILY_TREE.format(
                name=indi['name'] or state['person_id']))

            is_dark = ctk.get_appearance_mode() == 'Dark'
            colors = self._path_graph_colors(
                is_dark, getattr(self, '_theme_pref', None))

            canvas_frame = ctk.CTkFrame(content_frame, fg_color='transparent')
            canvas_frame.pack(fill='both', expand=True, padx=12, pady=(12, 0))
            canvas_frame.rowconfigure(0, weight=1)
            canvas_frame.columnconfigure(0, weight=1)

            canvas = tk.Canvas(
                canvas_frame, bg=colors['bg'], highlightthickness=0)
            ybar = tk.Scrollbar(
                canvas_frame, orient='vertical', command=canvas.yview)
            xbar = tk.Scrollbar(
                canvas_frame, orient='horizontal', command=canvas.xview)
            canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            canvas.grid(row=0, column=0, sticky='nsew')
            ybar.grid(row=0, column=1, sticky='ns')
            xbar.grid(row=1, column=0, sticky='ew')

            graph_state = {
                'zoom': state['tree_zoom'],
                'canvas_w': 0,
                'canvas_h': 0,
                'debug_payload': None,
            }
            canvas.bind(
                '<Configure>',
                lambda *_: self._center_graph_canvas(
                    canvas, graph_state['canvas_w'], graph_state['canvas_h']),
                add='+')

            def _redraw_tree():
                canvas.delete('all')
                graph_state['canvas_w'], graph_state['canvas_h'] = (
                    self._render_family_tree_canvas(
                        canvas,
                        state['person_id'],
                        state['tree_expanded'],
                        colors,
                        win,
                        graph_state['zoom'],
                        _expand_tree,
                        _recenter_tree,
                        _show_profile_from_tree,
                        _find_matches_from_tree,
                        _expand_all_tree,
                    ))
                graph_state['debug_payload'] = getattr(
                    canvas, '_family_tree_debug_payload', None)

            def _center_tree_on_current():
                canvas.update_idletasks()
                center_x, center_y = getattr(
                    canvas, '_family_tree_center',
                    (graph_state['canvas_w'] / 2,
                     graph_state['canvas_h'] / 2),
                )
                view_w = max(canvas.winfo_width(), 1)
                view_h = max(canvas.winfo_height(), 1)
                canvas_w = max(graph_state['canvas_w'], 1)
                canvas_h = max(graph_state['canvas_h'], 1)
                max_x = max(0, 1 - (view_w / canvas_w))
                max_y = max(0, 1 - (view_h / canvas_h))
                x_pos = max(0, min(max_x, (center_x - view_w / 2) / canvas_w))
                y_pos = max(0, min(max_y, (center_y - view_h / 2) / canvas_h))
                canvas.xview_moveto(x_pos)
                canvas.yview_moveto(y_pos)

            def _set_tree_zoom(zoom):
                zoom = max(0.5, min(2.5, zoom))
                if abs(zoom - graph_state['zoom']) < 0.001:
                    return
                x0, x1 = canvas.xview()
                y0, y1 = canvas.yview()
                center_x = (x0 + x1) / 2
                center_y = (y0 + y1) / 2
                span_x = x1 - x0
                span_y = y1 - y0
                graph_state['zoom'] = zoom
                state['tree_zoom'] = zoom
                _redraw_tree()
                canvas.update_idletasks()
                canvas.xview_moveto(max(0, min(1, center_x - span_x / 2)))
                canvas.yview_moveto(max(0, min(1, center_y - span_y / 2)))

            def _zoom_tree_in():
                _set_tree_zoom(graph_state['zoom'] * 1.1)

            def _zoom_tree_out():
                _set_tree_zoom(graph_state['zoom'] / 1.1)

            def _zoom_tree_reset():
                _set_tree_zoom(1.0)

            def _expand_tree(expand_id, category):
                request = (expand_id, category)
                self._toggle_expansion_request(
                    state['tree_expanded'], request)
                _redraw_tree()

            def _recenter_tree(new_center_id):
                state['person_id'] = new_center_id
                state['tree_expanded'] = [
                    (new_center_id, cat) for cat in INITIAL_TREE_CATEGORIES]
                center = self.individuals[new_center_id]
                win.title(WIN_FAMILY_TREE.format(
                    name=center['name'] or new_center_id))
                _redraw_tree()
                canvas.after_idle(_center_tree_on_current)

            def _show_profile_from_tree(indi_id):
                self._select_person_in_main_tree(indi_id)
                _show_person_view(indi_id)

            def _find_matches_from_tree(indi_id):
                self._select_person_in_main_tree(indi_id)
                _on_destroy_person_win()
                self.root.after_idle(self._find_matches)

            def _expand_all_tree(indi_id, categories):
                if self._expand_all_requests(
                        state['tree_expanded'], indi_id, categories):
                    _redraw_tree()

            def _save_tree(*_):
                win.update_idletasks()
                try:
                    return self._save_graph_canvas(
                        win, canvas, graph_state, DLG_SAVE_FAMILY_TREE)
                finally:
                    btn_frame.pack(fill='x', pady=(4, 8))

            def _copy_tree(*_):
                win.update_idletasks()
                try:
                    return self._copy_graph_canvas(win, canvas, graph_state)
                finally:
                    btn_frame.pack(fill='x', pady=(4, 8))

            def _save_tree_debug(*_):
                win.update_idletasks()
                try:
                    return self._save_graph_debug_payload(win, graph_state)
                finally:
                    btn_frame.pack(fill='x', pady=(4, 8))

            _redraw_tree()
            _bind_canvas_navigation(canvas)
            _bind_tree_mouse_navigation(canvas)
            bind_zoom_shortcuts(
                canvas, _zoom_tree_in, _zoom_tree_out, _zoom_tree_reset)
            win.bind(copy_shortcut, _copy_tree)
            win.bind(save_shortcut, _save_tree)
            graph_debug_enabled = (
                os.environ.get('GEDCOM_DNA_FINDER_GRAPH_DEBUG') == '1')
            if graph_debug_enabled:
                win.bind('<Control-Shift-D>', _save_tree_debug)
                canvas.bind('<Control-Shift-D>', _save_tree_debug)
            _render_tree_buttons(
                lambda: _show_person_view(state['person_id']),
                _copy_tree,
                _save_tree,
                _save_tree_debug if graph_debug_enabled else None,
            )
            canvas.focus_set()
            canvas.after_idle(_center_tree_on_current)

            # Compute needed window size from tree content plus fixed UI overhead.
            # Horizontal: canvas_frame padx×2 (24) + vertical scrollbar (~17) + margin (~4)
            # Vertical: canvas_frame pady-top (12) + horiz scrollbar (~17) + button bar (~48) + margin (~8)
            # Use self.root (always mapped) for reliable screen dimensions.
            _tsw = self.root.winfo_screenwidth()
            _tsh = self.root.winfo_screenheight()
            _tmax_w = int(_tsw * 0.9)
            _tmax_h = int(_tsh * 0.9)
            _tnw = int(graph_state['canvas_w']) + 45
            _tnh = int(graph_state['canvas_h']) + 85
            _twants_max = _tnw > _tmax_w or _tnh > _tmax_h
            state['_tree_wants_max'] = _twants_max
            state['_tree_needed_w'] = min(_tnw, _tmax_w)
            state['_tree_needed_h'] = min(_tnh, _tmax_h)

            if win.winfo_viewable():
                if _twants_max:
                    if sys.platform == 'win32':
                        win.state('zoomed')
                    else:
                        win.attributes('-zoomed', True)
                else:
                    _tcur_w = win.winfo_width()
                    _tcur_h = win.winfo_height()
                    _tnew_w = max(_tcur_w, state['_tree_needed_w'])
                    _tnew_h = max(_tcur_h, state['_tree_needed_h'])
                    if _tnew_w > _tcur_w or _tnew_h > _tcur_h:
                        _tcx = win.winfo_x()
                        _tcy = win.winfo_y()
                        win.geometry(
                            f"{int(_tnew_w)}x{int(_tnew_h)}"
                            f"+{max(0, min(_tcx, _tsw - _tnew_w))}"
                            f"+{max(0, min(_tcy, _tsh - _tnew_h))}"
                        )

        def _toggle_view(*_):
            if state['mode'] == 'person':
                _show_tree_view(state['person_id'])
            else:
                _show_person_view(state['person_id'])

        win.bind(toggle_shortcut, _toggle_view)

        initial_view = (
            initial_view
            or getattr(self, '_default_profile_view', 'profile')
        )
        if initial_view == 'tree':
            _show_tree_view(indi_id)
        else:
            _show_person_view(indi_id)

        # Use self.root for screen info — win is still withdrawn so
        # win.winfo_screenwidth() returns 0 on Windows before first show.
        _sw = self.root.winfo_screenwidth()
        _sh = self.root.winfo_screenheight()
        _mw = max(400, int(_sw * 0.9) - 32)
        _mh = max(300, int(_sh * 0.9) - 32)
        _tnw = state.get('_tree_needed_w', 0)
        _tnh = state.get('_tree_needed_h', 0)
        _twm = state.get('_tree_wants_max', False)

        if self._show_person_geometry and self._show_person_opened_this_session:
            # Subsequent open: parse saved geometry and expand for tree if needed.
            try:
                _wh = self._show_person_geometry.split('+')[0].split('-')[0]
                _sgw, _sgh = (int(p) for p in _wh.split('x'))
                _rest = self._show_person_geometry[len(_wh):]
                _pnums = [int(n) for n in
                          _rest.replace('+', ' +').replace('-', ' -').split() if n]
                _sgx, _sgy = _pnums[0], _pnums[1]
            except (ValueError, IndexError, AttributeError):
                _sgw, _sgh = 700, 520
                _sgx, _sgy = (_sw - _sgw) // 2, (_sh - _sgh) // 2
            if _tnw and not _twm:
                _w = min(max(_tnw, _sgw), _mw)
                _h = min(max(_tnh, _sgh), _mh)
            else:
                _w, _h = min(_sgw, _mw), min(_sgh, _mh)
            _x = max(0, min(_sgx, _sw - _w))
            _y = max(0, min(_sgy, _sh - _h))
        else:
            # First open this session: size for content and center on display.
            if _twm:
                _w, _h = 700, 520  # will be maximized after deiconify
            elif _tnw:
                _w, _h = min(_tnw, _mw), min(_tnh, _mh)
            else:
                _w, _h = 700, 520
            _w, _h = max(400, _w), max(300, _h)
            _x = max(0, (_sw - _w) // 2)
            _y = max(0, (_sh - _h) // 2)

        self._show_person_opened_this_session = True
        win.bind('<Configure>', _on_win_configure)
        win.minsize(400, 300)
        if reuse_window:
            win.update_idletasks()
            self._raise_window(win)
            return

        win.geometry(f"{int(_w)}x{int(_h)}+{int(_x)}+{int(_y)}")
        self._raise_window(win)
        if _twm:
            if sys.platform == 'win32':
                win.state('zoomed')
            else:
                win.attributes('-zoomed', True)

    @staticmethod
    def _reused_person_window_bindings():
        """Return Toplevel bindings that should not survive a view swap."""
        mod_key = 'Command' if sys.platform == 'darwin' else 'Control'
        return (
            '<Escape>',
            '<Up>',
            '<Down>',
            '<Prior>',
            '<Next>',
            '<Home>',
            '<End>',
            f'<{mod_key}-c>',
            f'<{mod_key}-s>',
            f'<{mod_key}-t>',
            f'<{mod_key}-plus>',
            f'<{mod_key}-equal>',
            f'<{mod_key}-KP_Add>',
            f'<{mod_key}-minus>',
            f'<{mod_key}-KP_Subtract>',
            f'<{mod_key}-0>',
            f'<{mod_key}-KP_0>',
            f'<{mod_key}-MouseWheel>',
            f'<{mod_key}-Button-4>',
            f'<{mod_key}-Button-5>',
        )

    def _view_tags(self):
        """Show tag-record definitions and allow choosing the DNA tag keyword."""
        if not self.tag_records:
            messagebox.showinfo(WIN_TAG_DEFINITIONS, MSG_NO_TAGS)
            return

        win = ctk.CTkToplevel(self.root)
        win.withdraw()
        win.title(WIN_TAG_DEFINITIONS)
        win.transient(self.root)
        win.resizable(True, True)

        show_ids = self.show_ids.get()
        rows = sorted(self.tag_records.items())

        list_frame = ctk.CTkFrame(win, fg_color='transparent')
        list_frame.pack(fill='both', expand=True, padx=8, pady=(8, 0))

        if show_ids:
            tag_tree = ttk.Treeview(list_frame, columns=('id', 'name'),
                                    show='headings', selectmode='browse',
                                    height=min(len(rows), 20))
            tag_tree.heading('id', text=COL_TAG_ID)
            tag_tree.heading('name', text=COL_TAG_NAME)
            tag_tree.column('id', width=90, anchor='w', stretch=False)
            tag_tree.column('name', width=300, anchor='w', stretch=True)
        else:
            tag_tree = ttk.Treeview(list_frame, columns=('name',),
                                    show='headings', selectmode='browse',
                                    height=min(len(rows), 20))
            tag_tree.heading('name', text=COL_TAG_NAME)
            tag_tree.column('name', width=390, anchor='w', stretch=True)

        ysb = ctk.CTkScrollbar(list_frame, orientation='vertical',
                               command=tag_tree.yview)
        tag_tree.configure(yscrollcommand=ysb.set)
        tag_tree.pack(side='left', fill='both', expand=True)
        ysb.pack(side='right', fill='y')

        current_kw = self.tag_keyword.get().strip().lower()
        first_match = None
        for ref, name in rows:
            iid = tag_tree.insert('', 'end',
                                  values=(ref, name) if show_ids else (name,))
            if first_match is None and name.strip().lower() == current_kw:
                first_match = iid

        btn_frame = ctk.CTkFrame(win, fg_color='transparent')
        btn_frame.pack(fill='x', padx=8, pady=8)

        def on_ok():
            sel = tag_tree.selection()
            if sel:
                name_val = tag_tree.set(sel[0], 'name')
                self.tag_keyword.set(name_val)
            win.destroy()

        def on_cancel():
            win.destroy()

        ctk.CTkButton(btn_frame, text=BTN_OK, width=80,
                      command=on_ok).pack(side='right', padx=(4, 0))
        ctk.CTkButton(btn_frame, text=BTN_CANCEL, width=80,
                      command=on_cancel).pack(side='right')

        tag_tree.bind('<Return>', lambda *_: on_ok())
        tag_tree.bind('<Home>', lambda *_: self._tree_jump(
            'first', tag_tree) or 'break')
        tag_tree.bind('<End>', lambda *_: self._tree_jump(
            'last',  tag_tree) or 'break')
        win.bind('<Escape>', lambda *_: on_cancel())

        self._fit_window_to_content(win, min_w=350, min_h=220)
        self._apply_theme_to_window(win)

        win.deiconify()
        win.focus_force()
        tag_tree.focus_set()
        target = first_match or (tag_tree.get_children()[
                                 0] if tag_tree.get_children() else None)
        if target:
            tag_tree.focus(target)
            tag_tree.selection_set(target)
            tag_tree.see(target)

    def _pick_person(self, title=WIN_SELECT_PERSON):
        """Modal dialog to pick one person from the loaded GEDCOM. Returns indi_id or None."""
        if not self.individuals:
            messagebox.showwarning(ERR_NO_DATA_TITLE, ERR_NO_DATA_MSG)
            return None

        dialog = ctk.CTkToplevel(self.root)
        dialog.withdraw()
        dialog.title(title)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.focus_force()

        result = [None]

        search_frame = ctk.CTkFrame(dialog, fg_color='transparent')
        search_frame.pack(fill='x', padx=8, pady=8)
        ctk.CTkLabel(search_frame, text=LBL_FIND).pack(side='left', padx=(0, 4))
        search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(search_frame, textvariable=search_var)
        search_entry.pack(side='left', fill='x', expand=True)

        list_frame = ctk.CTkFrame(dialog, fg_color='transparent')
        list_frame.pack(fill='both', expand=True, padx=8)

        picker_tree = ttk.Treeview(
            list_frame,
            columns=('name', 'birth', 'death', 'flagged'),
            show='headings',
            selectmode='browse',
        )
        picker_tree.heading('name', text=COL_NAME)
        picker_tree.heading('birth', text=COL_BIRTH)
        picker_tree.heading('death', text=COL_DEATH)
        picker_tree.heading('flagged', text=COL_DNA)
        picker_tree.column('name', width=240, anchor='w', stretch=True)
        picker_tree.column('birth', width=55, anchor='w', stretch=False)
        picker_tree.column('death', width=55, anchor='w', stretch=False)
        picker_tree.column('flagged', width=50, anchor='center', stretch=False)
        is_dark = ctk.get_appearance_mode() == 'Dark'
        picker_tree.tag_configure('flagged_row', background=get_flag_bg(is_dark))

        ysb = ctk.CTkScrollbar(list_frame, orientation='vertical',
                               command=picker_tree.yview)
        picker_tree.configure(yscrollcommand=ysb.set)
        picker_tree.pack(side='left', fill='both', expand=True)
        ysb.pack(side='right', fill='y')

        after_id = [None]

        def populate(query=''):
            picker_tree.delete(*picker_tree.get_children())
            query = query.strip()
            shown = 0
            for indi_id in self.sorted_ids:
                indi = self.individuals[indi_id]
                if query:
                    match, _score = individual_matches_query(
                        indi_id, indi, query)
                    if not match:
                        continue
                tags = ('flagged_row',) if indi['dna_markers'] else ()
                flagged_mark = '✓' if indi['dna_markers'] else ''
                picker_tree.insert(
                    '', 'end', iid=indi_id,
                    values=(self._display_name(indi),
                            indi['birth_year'] or '',
                            indi['death_year'] or '',
                            flagged_mark),
                    tags=tags,
                )
                shown += 1
                if shown >= self.MAX_LIST_DISPLAY:
                    break

        def on_search_change(*_):
            if after_id[0]:
                dialog.after_cancel(after_id[0])
            after_id[0] = dialog.after(150, lambda: populate(search_var.get()))

        def picker_flush_and_jump():
            if after_id[0]:
                dialog.after_cancel(after_id[0])
                after_id[0] = None
                populate(search_var.get())
            self._tree_jump('first', picker_tree)

        search_var.trace_add('write', on_search_change)
        search_entry.bind('<Return>', lambda *_: picker_flush_and_jump())
        populate()

        def select():
            sel = picker_tree.selection()
            if sel:
                result[0] = sel[0]
            dialog.destroy()

        picker_tree.bind('<Double-1>', lambda *_: select())
        picker_tree.bind('<Return>', lambda *_: select())
        picker_tree.bind(
            '<Key>', lambda e: self._tree_type_ahead(e, picker_tree))
        picker_tree.bind('<Home>', lambda *_: self._tree_jump(
            'first', picker_tree) or 'break')
        picker_tree.bind('<End>', lambda *_: self._tree_jump(
            'last',  picker_tree) or 'break')
        dialog.bind('<Escape>', lambda *_: dialog.destroy())

        btn_frame = ctk.CTkFrame(dialog, fg_color='transparent')
        btn_frame.pack(fill='x', padx=8, pady=8)
        ctk.CTkButton(btn_frame, text=BTN_SELECT, width=80,
                      command=select).pack(side='right', padx=(4, 0))
        ctk.CTkButton(btn_frame, text=BTN_CANCEL, width=80,
                      command=dialog.destroy).pack(side='right')

        self._apply_theme_to_window(dialog)
        self._fit_window_to_content(
            dialog,
            min_w=500,
            min_h=380,
            preferred_w=600,
            preferred_h=500,
        )
        dialog.deiconify()
        search_entry.focus_set()
        dialog.wait_window()
        return result[0]

    def _find_path(self):
        """Prompt for a target person and render paths from the current selection."""
        if self._busy:
            return
        sel = self.tree.selection()
        start_id = sel[0] if sel else self._active_id
        if not start_id:
            messagebox.showwarning(ERR_NO_SEL_TITLE, ERR_NO_PATH_SEL_MSG)
            return

        target_id = self._pick_person(WIN_SELECT_TARGET)
        if not target_id:
            return

        try:
            max_depth = int(self.max_depth.get())
        except (tk.TclError, ValueError):
            messagebox.showerror(ERR_BAD_VAL_TITLE, ERR_BAD_VAL_DEPTH)
            return

        try:
            top_n = int(self.top_n.get())
        except (tk.TclError, ValueError):
            top_n = 5

        self._show_progress()
        self._set_busy(True)

        def _do_search(cancel_event):
            return self._model.find_all_paths(
                start_id, target_id, top_n, max_depth,
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
            self._results_reversed = False
            self._reverse_btn.configure(text=BTN_REVERSE)
            self._last_result = {'type': 'path',
                                 'start_id': start_id, 'end_id': target_id}
            self._render_path_results(start_id, target_id, paths, truncated)

        self._run_background_task(
            _do_search,
            _on_done,
            popup_message=PROGRESS_FINDING_PATH,
            cancelable=True,
            on_cancel=_on_cancel,
        )

    def _render_path_results(self, start_id, end_id, paths, truncated=False):
        """Render relationship paths between two selected individuals."""
        if self._last_result and self._last_result.get('type') == 'path':
            self._last_result['paths'] = paths
            self._last_result['truncated'] = truncated

        w = self.results
        w.configure(state='normal')
        w.delete('1.0', 'end')
        self._clear_person_tags(w)

        w._textbox.tag_configure('person_link')
        w._textbox.tag_bind('person_link', '<Enter>',
                            lambda *_: w._textbox.config(cursor='hand2'))
        w._textbox.tag_bind('person_link', '<Leave>',
                            lambda *_: w._textbox.config(cursor=''))
        w._textbox.tag_configure('relationship_link',
                                 foreground=self._link_color, underline=1)
        w._textbox.tag_bind('relationship_link', '<Enter>',
                            lambda *_: w._textbox.config(cursor='hand2'))
        w._textbox.tag_bind('relationship_link', '<Leave>',
                            lambda *_: w._textbox.config(cursor=''))

        def nl(text='', bold=False):
            w.insert('end', text + '\n', ('bold',) if bold else ())

        def person(indi_id, prefix='', suffix=''):
            if prefix:
                w.insert('end', prefix)
            tag = f'pers_{indi_id.strip("@")}'
            w.insert('end', describe(self.individuals[indi_id],
                                     show_id=self.show_ids.get()),
                     ('person_link', tag))
            w._textbox.tag_configure(tag, foreground=self._link_color)
            w._textbox.tag_bind(tag, '<Button-1>',
                                lambda _, iid=indi_id: self._navigate_to(iid))
            if suffix:
                w.insert('end', suffix)
            w.insert('end', '\n')

        def person_inline(indi_id, prefix='', suffix=''):
            if prefix:
                w.insert('end', prefix)
            tag = f'pers_{indi_id.strip("@")}'
            w.insert('end', describe(self.individuals[indi_id],
                                     show_id=self.show_ids.get()),
                     ('person_link', tag))
            w._textbox.tag_configure(tag, foreground=self._link_color)
            w._textbox.tag_bind(tag, '<Button-1>',
                                lambda _, iid=indi_id: self._navigate_to(iid))
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
            w._textbox.tag_bind(
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

        if self._results_reversed:
            disp_start, disp_end = end_id, start_id
            disp_paths = [self._reverse_path(p, self.individuals) for p in paths]
        else:
            disp_start, disp_end = start_id, end_id
            disp_paths = paths
        common_ancestor_ids = self._model.find_common_ancestors(
            disp_start, disp_end)

        nl(PATH_SECTION, bold=True)
        person(disp_start, prefix=PATH_FROM)
        person(disp_end,   prefix=PATH_TO)
        nl()

        if start_id == end_id:
            nl(PATH_SAME_PERSON)
        elif not disp_paths:
            nl(PATH_NOT_FOUND.format(depth=self.max_depth.get()))
        else:
            ancestors = get_ancestor_depths(
                disp_start, self.individuals, self.families)
            descendants = get_descendant_depths(
                disp_start, self.individuals, self.families)
            for rank, path in enumerate(disp_paths, 1):
                dist = len(path) - 1
                rel = describe_relationship(path, self.individuals,
                                            ancestors=ancestors,
                                            descendants=descendants,
                                            families=self.families)
                nl(PATH_RANK.format(
                    rank=rank, rel=rel, dist=dist,
                    plural='s' if dist != 1 else ''), bold=True)
                relationship_line(rel, path, prefix="  ")
                common_ancestor_line(
                    common_ancestor_ids, prefix="  ", item_prefix="    ")
                for i, (node_id, edge) in enumerate(path):
                    if i == 0:
                        person(node_id, prefix="  ")
                    else:
                        person(node_id, prefix=self._path_edge_prefix(
                            edge, "    "))
                nl()
            if truncated:
                nl(PATH_SEARCH_CAP)
        nl()

        self._reverse_btn.configure(state='normal')
        w.configure(state='disabled')

    def _show_preferences(self):
        """Open the preferences dialog for display, search, and cache settings."""
        win = ctk.CTkToplevel(self.root)
        win.withdraw()
        win.title(WIN_PREFERENCES)
        win.resizable(True, True)
        win.transient(self.root)
        win.grab_set()

        outer = ctk.CTkFrame(win, fg_color='transparent')
        outer.pack(fill='both', expand=True, padx=16, pady=16)

        # Appearance section (font size + theme + tooltips)
        appearance_section = ctk.CTkFrame(outer, border_width=1)
        appearance_section.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(appearance_section, text=FRAME_APPEARANCE, anchor='w',
                     font=ctk.CTkFont(weight='bold')).pack(
            anchor='nw', padx=12, pady=(8, 4))

        # Resolve the CTkFrame background so ttk.Radiobutton blends in.
        # Walk up _fg_color chain past any transparent frames.
        def _section_bg(frame):
            try:
                fg = frame._fg_color
                if fg == 'transparent':
                    return _section_bg(frame.master)
                is_dark = ctk.get_appearance_mode() == 'Dark'
                return (fg[1] if is_dark else fg[0]) if isinstance(fg, (list, tuple)) else fg
            except AttributeError:
                return frame.cget('background')

        # On Windows/Linux, stamp the CTkFrame colour onto a named ttk style so
        # ttk.Radiobutton blends in.  On macOS the Aqua ttk theme ignores the
        # background style option; tk.Radiobutton (same native indicator, but
        # classic widget) does respect it, so we use that instead.
        _rb_style = ttk.Style()

        def _radiobutton(parent, *, text, variable, value):
            if sys.platform == 'darwin':
                bg = _section_bg(parent)
                return tk.Radiobutton(parent, text=text, variable=variable,
                                      value=value, background=bg,
                                      activebackground=bg, highlightthickness=0)
            if sys.platform != 'darwin':
                _rb_style.configure('Pref.TRadiobutton', background=_section_bg(parent))
            return ttk.Radiobutton(parent, text=text, variable=variable,
                                   value=value, style='Pref.TRadiobutton')

        # Font size row
        font_row = ctk.CTkFrame(appearance_section, fg_color='transparent')
        font_row.pack(fill='x', padx=12, pady=(0, 4))
        ctk.CTkLabel(font_row, text=FRAME_FONT_SIZE + ':').pack(side='left', padx=(0, 8))
        size_var = tk.StringVar(value=self._font_size_pref)
        for label, key in ((FONT_SMALL, "small"), (FONT_MEDIUM, "medium"), (FONT_LARGE, "large")):
            _radiobutton(
                font_row, text=label, variable=size_var, value=key,
            ).pack(side='left', padx=8)

        # Theme row
        theme_row = ctk.CTkFrame(appearance_section, fg_color='transparent')
        theme_row.pack(fill='x', padx=12, pady=(0, 4))
        ctk.CTkLabel(theme_row, text=FRAME_THEME + ':').pack(side='left', padx=(0, 8))
        theme_var = tk.StringVar(value=self._theme_pref)
        for name in self._THEME_NAMES:
            _radiobutton(
                theme_row, text=name, variable=theme_var, value=name,
            ).pack(side='left', padx=6)

        # Hide Tooltips checkbox
        tooltip_row = ctk.CTkFrame(appearance_section, fg_color='transparent')
        tooltip_row.pack(fill='x', padx=12, pady=(0, 10))
        hide_tooltips_var = tk.BooleanVar(value=self._hide_tooltips_pref)
        hide_tooltips_chk = ctk.CTkCheckBox(
            tooltip_row, text=CHK_HIDE_TOOLTIPS, variable=hide_tooltips_var)
        hide_tooltips_chk.pack(anchor='w')
        Tooltip(hide_tooltips_chk, TIP_HIDE_TOOLTIPS)

        # Search defaults section
        search_section = ctk.CTkFrame(outer, border_width=1)
        search_section.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(search_section, text=FRAME_SEARCH_DEFAULTS, anchor='w',
                     font=ctk.CTkFont(weight='bold')).pack(
            anchor='nw', padx=12, pady=(8, 4))
        search_frame = ctk.CTkFrame(search_section, fg_color='transparent')
        search_frame.pack(fill='x', padx=12, pady=(0, 10))

        _pref_top_n_label = ctk.CTkLabel(search_frame, text=LBL_TOP_N_RESULTS)
        _pref_top_n_label.grid(row=0, column=0, sticky='w', padx=(0, 8))
        top_n_var = tk.IntVar(value=self.top_n.get())
        _pref_top_n_spin = ttk.Spinbox(
            search_frame, from_=1, to=20, textvariable=top_n_var, width=6)
        _pref_top_n_spin.grid(row=0, column=1, sticky='w', padx=(0, 24))
        Tooltip(_pref_top_n_label, TIP_TOP_N)
        Tooltip(_pref_top_n_spin, TIP_TOP_N)
        _pref_max_depth_label = ctk.CTkLabel(search_frame, text=LBL_MAX_DEPTH_PREF)
        _pref_max_depth_label.grid(row=0, column=2, sticky='w', padx=(0, 8))
        max_depth_var = tk.IntVar(value=self.max_depth.get())
        _pref_max_depth_spin = ttk.Spinbox(
            search_frame, from_=1, to=200, textvariable=max_depth_var, width=6)
        _pref_max_depth_spin.grid(row=0, column=3, sticky='w')
        Tooltip(_pref_max_depth_label, TIP_MAX_DEPTH)
        Tooltip(_pref_max_depth_spin, TIP_MAX_DEPTH)
        _pref_fuzzy_label = ctk.CTkLabel(search_frame, text=LBL_FUZZY_THRESHOLD)
        _pref_fuzzy_label.grid(row=1, column=0, sticky='w', padx=(0, 8), pady=(6, 0))
        fuzzy_threshold_var = tk.DoubleVar(
            value=round(float(self.fuzzy_threshold.get()), 2))
        _pref_fuzzy_spin = ttk.Spinbox(
            search_frame, from_=0.0, to=1.0, increment=0.01,
            textvariable=fuzzy_threshold_var, width=6, format="%.2f")
        _pref_fuzzy_spin.grid(row=1, column=1, sticky='w', pady=(6, 0))
        Tooltip(_pref_fuzzy_label, TIP_FUZZY_THRESHOLD)
        Tooltip(_pref_fuzzy_spin, TIP_FUZZY_THRESHOLD)

        _pref_max_display_label = ctk.CTkLabel(search_frame, text=LBL_MAX_DISPLAY)
        _pref_max_display_label.grid(row=1, column=2, sticky='w', padx=(0, 8), pady=(6, 0))
        max_display_var = tk.IntVar(value=self.max_display.get())
        _pref_max_display_spin = ttk.Spinbox(
            search_frame, from_=100, to=100000, increment=500,
            textvariable=max_display_var, width=8)
        _pref_max_display_spin.grid(row=1, column=3, sticky='w', pady=(6, 0))
        Tooltip(_pref_max_display_label, TIP_MAX_DISPLAY)
        Tooltip(_pref_max_display_spin, TIP_MAX_DISPLAY)

        _pref_tag_keyword_label = ctk.CTkLabel(search_frame, text=LBL_TAG_KEYWORD)
        _pref_tag_keyword_label.grid(row=2, column=0, sticky='w', padx=(0, 8), pady=(6, 0))
        tag_keyword_var = tk.StringVar(value=self.tag_keyword.get())
        _pref_tag_keyword_entry = ctk.CTkEntry(
            search_frame, textvariable=tag_keyword_var, width=180)
        _pref_tag_keyword_entry.grid(row=2, column=1, columnspan=3, sticky='ew', pady=(6, 0))
        Tooltip(_pref_tag_keyword_label, TIP_TAG_KEYWORD)
        Tooltip(_pref_tag_keyword_entry, TIP_TAG_KEYWORD)

        _pref_page_marker_label = ctk.CTkLabel(search_frame, text=LBL_PAGE_MARKER)
        _pref_page_marker_label.grid(row=3, column=0, sticky='w', padx=(0, 8), pady=(6, 0))
        page_marker_var = tk.StringVar(value=self.page_marker.get())
        _pref_page_marker_entry = ctk.CTkEntry(
            search_frame, textvariable=page_marker_var, width=180)
        _pref_page_marker_entry.grid(row=3, column=1, columnspan=3, sticky='ew', pady=(6, 0))
        Tooltip(_pref_page_marker_label, TIP_PAGE_MARKER)
        Tooltip(_pref_page_marker_entry, TIP_PAGE_MARKER)

        # Display section
        display_section = ctk.CTkFrame(outer, border_width=1)
        display_section.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(display_section, text=FRAME_DISPLAY, anchor='w',
                     font=ctk.CTkFont(weight='bold')).pack(
            anchor='nw', padx=12, pady=(8, 4))
        display_frame = ctk.CTkFrame(display_section, fg_color='transparent')
        display_frame.pack(fill='x', padx=12, pady=(0, 10))

        show_ids_var = tk.BooleanVar(value=self.show_ids.get())
        ctk.CTkCheckBox(display_frame, text=CHK_SHOW_IDS,
                        variable=show_ids_var).pack(anchor='w')

        name_order_row = ctk.CTkFrame(display_frame, fg_color='transparent')
        name_order_row.pack(anchor='w', pady=(6, 0))
        ctk.CTkLabel(name_order_row, text=LBL_NAME_FORMAT).pack(
            side='left', padx=(0, 8))
        name_order_var = tk.StringVar(value=self._name_order)
        _radiobutton(name_order_row, text=NAME_FIRST_LAST,
                     variable=name_order_var, value='first_last').pack(side='left', padx=(0, 8))
        _radiobutton(name_order_row, text=NAME_LAST_FIRST,
                     variable=name_order_var, value='last_first').pack(side='left')

        profile_view_row = ctk.CTkFrame(display_frame, fg_color='transparent')
        profile_view_row.pack(anchor='w', pady=(6, 0))
        ctk.CTkLabel(profile_view_row, text=LBL_DEFAULT_PROFILE_VIEW).pack(
            side='left', padx=(0, 8))
        profile_view_var = tk.StringVar(
            value=getattr(self, '_default_profile_view', 'profile'))
        _radiobutton(profile_view_row, text=PROFILE_VIEW_PROFILE,
                     variable=profile_view_var, value='profile').pack(side='left', padx=(0, 8))
        _radiobutton(profile_view_row, text=PROFILE_VIEW_TREE,
                     variable=profile_view_var, value='tree').pack(side='left')

        # Cache section
        cache_section = ctk.CTkFrame(outer, border_width=1)
        cache_section.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(cache_section, text=FRAME_CACHE, anchor='w',
                     font=ctk.CTkFont(weight='bold')).pack(
            anchor='nw', padx=12, pady=(8, 4))
        cache_frame = ctk.CTkFrame(cache_section, fg_color='transparent')
        cache_frame.pack(fill='x', padx=12, pady=(0, 10))
        ctk.CTkButton(cache_frame, text=BTN_CLEAR_CACHE,
                      command=self._clear_cache).pack(side='left')
        ctk.CTkLabel(cache_frame, text=LBL_CACHE_NOTE).pack(
            side='left', padx=(10, 0))

        # Buttons
        btn_frame = ctk.CTkFrame(win, fg_color='transparent')
        btn_frame.pack(fill='x', padx=16, pady=(0, 16))

        def on_ok():
            self._font_size_pref = size_var.get()
            self._apply_font_size(self._font_size_pref)
            self._save_font_preference(self._font_size_pref)
            self._apply_theme(theme_var.get())
            self._save_theme_preference(theme_var.get())
            self._hide_tooltips_pref = hide_tooltips_var.get()
            Tooltip.enabled = not self._hide_tooltips_pref
            self._save_hide_tooltips_preference(self._hide_tooltips_pref)
            try:
                self.top_n.set(max(1, int(top_n_var.get())))
                self._config.set_top_n(self.top_n.get())
            except (tk.TclError, ValueError):
                pass
            try:
                self.max_depth.set(max(1, int(max_depth_var.get())))
                self._config.set_max_depth(self.max_depth.get())
            except (tk.TclError, ValueError):
                pass
            try:
                threshold = min(
                    1.0, max(0.0, float(fuzzy_threshold_var.get())))
                self.fuzzy_threshold.set(threshold)
                self._config.set_fuzzy_threshold(threshold)
            except (tk.TclError, ValueError):
                pass
            try:
                self.max_display.set(max(100, int(max_display_var.get())))
                self._config.set_max_display(self.max_display.get())
            except (tk.TclError, ValueError):
                pass
            self.tag_keyword.set(tag_keyword_var.get())
            self._config.set_tag_keyword(tag_keyword_var.get())
            self.page_marker.set(page_marker_var.get())
            self._config.set_page_marker(page_marker_var.get())
            self.show_ids.set(show_ids_var.get())
            self._config.set_show_ids(show_ids_var.get())
            self._name_order = name_order_var.get()
            self._config.set_name_order(self._name_order)
            self._default_profile_view = profile_view_var.get()
            self._config.set_profile_view_default(self._default_profile_view)
            if self._default_profile_view == 'tree':
                self.show_person_btn.configure(text=BTN_SHOW_PERSON_TREE)
                self._show_person_tooltip.update_text(TIP_SHOW_PERSON_TREE)
            else:
                self.show_person_btn.configure(text=BTN_SHOW_PERSON)
                self._show_person_tooltip.update_text(TIP_SHOW_PERSON)
            self._pop_sort_key = None
            self._populate_tree()
            self._refresh_result()
            win.destroy()

        def on_cancel():
            win.destroy()

        win.bind('<Escape>', lambda *_: on_cancel())
        win.bind('<Return>', lambda *_: on_ok())

        ctk.CTkButton(btn_frame, text=BTN_OK, width=80,
                      command=on_ok).pack(side='right', padx=(4, 0))
        ctk.CTkButton(btn_frame, text=BTN_CANCEL, width=80,
                      command=on_cancel).pack(side='right')

        self._fit_window_to_content(win, min_w=500, min_h=420)
        win.deiconify()
        win.after(50, win.focus_force)

    def _resource_path(self, filename):
        """Locate a bundled resource whether running from source or PyInstaller."""
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, filename)

    def _show_how_to_use(self):
        """Open the help documentation window."""
        self._show_file_window(
            WIN_HOW_TO_USE, self._resource_path('docs/HELP.md'), markdown=True)

    def _show_keyboard_shortcuts(self):
        """Open the keyboard shortcuts reference window."""
        win = ctk.CTkToplevel(self.root)
        win.withdraw()
        win.title(WIN_KEYBOARD_SHORTCUTS)
        win.transient(self.root)
        win.grab_set()
        win.resizable(True, True)
        win.bind('<Escape>', lambda *_: win.destroy())

        outer = ctk.CTkFrame(win, fg_color='transparent')
        outer.pack(fill='both', expand=True, padx=16, pady=(16, 8))

        tree_frame = ctk.CTkFrame(outer, fg_color='transparent')
        tree_frame.pack(fill='both', expand=True)

        tree = ttk.Treeview(tree_frame, columns=('key', 'action'),
                            show='headings', selectmode='browse',
                            height=len(KEYBOARD_SHORTCUT_ROWS))
        tree.heading('key', text=COL_SHORTCUT)
        tree.heading('action', text=COL_ACTION)
        tree.column('key', width=90, minwidth=70, stretch=False, anchor='center')
        tree.column('action', width=420, minwidth=200, stretch=True, anchor='w')

        is_dark = ctk.get_appearance_mode() == 'Dark'
        odd_bg  = '#2f2f2f' if is_dark else '#f5f5f5'
        tree.tag_configure('odd', background=odd_bg)

        for idx, (key, action) in enumerate(KEYBOARD_SHORTCUT_ROWS):
            tree.insert('', 'end', values=(key, action),
                        tags=('odd',) if idx % 2 else ())

        vsb = ctk.CTkScrollbar(tree_frame, orientation='vertical',
                               command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        ctk.CTkFrame(win, height=1,
                     fg_color=('gray70', 'gray30')).pack(fill='x')
        btn_frame = ctk.CTkFrame(win, fg_color='transparent')
        btn_frame.pack(fill='x', padx=16, pady=8)
        ctk.CTkButton(btn_frame, text=BTN_CLOSE, width=80,
                      command=win.destroy).pack(side='right')

        self._fit_window_to_content(win, min_w=540, min_h=420)
        win.deiconify()
        win.after(50, win.focus_force)

    def _show_about(self):
        """Open the about window with version and license information."""
        self._show_file_window(
            WIN_ABOUT,
            self._resource_path('docs/LICENSE.md'), markdown=True,
            preamble=f"# {APP_TITLE}  v{self._version} ({self._release_date})\n\n",
        )

    def _show_privacy_policy(self):
        """Open the privacy policy documentation window."""
        self._show_file_window(
            WIN_PRIVACY_POLICY,
            self._resource_path('docs/PRIVACY_POLICY.md'), markdown=True,
        )

    def _check_for_updates(self):
        """Check GitHub for a newer release and report the result."""
        if getattr(self, '_update_check_in_progress', False):
            return
        self._update_check_in_progress = True
        progress = self._show_update_check_progress()

        def _worker():
            result = check_for_updates(self._version)
            self.root.after(
                0, lambda: self._finish_update_check(result, progress))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_update_check_progress(self):
        """Show a small progress dialog while the GitHub request runs."""
        popup = tk.Toplevel(self.root)
        popup.withdraw()
        popup.title(WIN_CHECKING_FOR_UPDATES)
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = ttk.Frame(popup, padding=(20, 14))
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=UPDATE_CHECKING_MSG).pack(pady=(0, 10))
        bar = ttk.Progressbar(frame, mode='indeterminate', length=260)
        bar.pack(pady=(0, 4))
        bar.start(10)

        self._fit_window_to_content(popup, min_w=320, min_h=90)
        popup.deiconify()
        popup.lift()
        return popup

    def _finish_update_check(self, result, progress):
        """Close progress feedback and show the update-check result."""
        self._update_check_in_progress = False
        try:
            progress.destroy()
        except tk.TclError:
            pass

        if result.error:
            messagebox.showerror(
                UPDATE_CHECK_FAILED_TITLE,
                UPDATE_CHECK_FAILED_MSG.format(error=result.error),
                parent=self.root,
            )
            return

        if result.update_available:
            self._show_update_available(result)
            return

        messagebox.showinfo(
            UPDATE_CURRENT_TITLE,
            UPDATE_CURRENT_MSG.format(current=result.current_version),
            parent=self.root,
        )

    def _show_update_available(self, result):
        """Show a dialog linking to the latest GitHub release."""
        win = ctk.CTkToplevel(self.root)
        win.withdraw()
        win.title(WIN_UPDATE_AVAILABLE)
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        win.bind('<Escape>', lambda *_: win.destroy())

        outer = ctk.CTkFrame(win, fg_color='transparent')
        outer.pack(fill='both', expand=True, padx=18, pady=(16, 10))

        ctk.CTkLabel(
            outer,
            text=UPDATE_AVAILABLE_HEADING,
            font=ctk.CTkFont(weight='bold'),
            anchor='w',
        ).pack(fill='x', pady=(0, 10))
        ctk.CTkLabel(
            outer,
            text=UPDATE_INSTALLED_VERSION.format(
                current=result.current_version),
            anchor='w',
        ).pack(fill='x')
        ctk.CTkLabel(
            outer,
            text=UPDATE_LATEST_VERSION.format(latest=result.latest_version),
            anchor='w',
        ).pack(fill='x', pady=(2, 12))
        ctk.CTkLabel(
            outer,
            text=UPDATE_DOWNLOAD_PROMPT,
            anchor='w',
        ).pack(fill='x')
        release_link = ctk.CTkLabel(
            outer,
            text=result.release_url,
            text_color=self._link_color,
            anchor='w',
        )
        release_link.pack(fill='x', pady=(2, 0))
        release_link.bind(
            '<Button-1>', lambda *_: webbrowser.open(result.release_url))

        ctk.CTkFrame(win, height=1,
                     fg_color=('gray70', 'gray30')).pack(fill='x')
        btn_frame = ctk.CTkFrame(win, fg_color='transparent')
        btn_frame.pack(fill='x', padx=12, pady=8)
        ctk.CTkButton(
            btn_frame,
            text=UPDATE_OPEN_RELEASES,
            command=lambda: webbrowser.open(result.release_url),
        ).pack(side='right', padx=(4, 0))
        ctk.CTkButton(
            btn_frame, text=BTN_CLOSE, width=80,
            command=win.destroy,
        ).pack(side='right')

        self._fit_window_to_content(win, min_w=430, min_h=220)
        win.deiconify()
        win.after(50, win.focus_force)

    def _show_file_window(self, title, filepath, markdown=False, preamble=""):
        """Open a modal text window for a bundled documentation file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = preamble + f.read()
        except OSError as e:
            messagebox.showerror(
                ERR_FILE_NOT_FOUND_TITLE,
                ERR_FILE_NOT_FOUND_MSG.format(path=filepath, error=e))
            return

        win = ctk.CTkToplevel(self.root)
        win.withdraw()
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        win.bind('<Escape>', lambda *_: win.destroy())

        is_dark = ctk.get_appearance_mode() == 'Dark'
        code_bg = '#3a3a3a' if is_dark else '#f0f0f0'

        ui_size = self._FONT_SIZES[self._font_size_pref]['ui']
        ui_family = tkfont.nametofont('TkDefaultFont').actual()['family']
        text = ctk.CTkTextbox(win, wrap='word', activate_scrollbars=True,
                              font=ctk.CTkFont(family=ui_family, size=ui_size))
        text._textbox.configure(padx=12, pady=8)
        text.pack(fill='both', expand=True)

        base_dir = os.path.dirname(os.path.abspath(filepath))
        doc_state = {'content': content, 'base_dir': base_dir}

        def _set_state(enabled):
            if sys.platform == 'darwin':
                if enabled:
                    text._textbox.unbind('<Key>')
                else:
                    text._textbox.bind('<Key>', lambda *_: 'break')
            else:
                text.configure(state='normal' if enabled else 'disabled')

        def _nav_handler(url):
            if not url.startswith(('http://', 'https://')) and url.endswith('.md'):
                target = os.path.normpath(os.path.join(doc_state['base_dir'], url))
                try:
                    with open(target, 'r', encoding='utf-8') as f:
                        new_content = f.read()
                except OSError:
                    webbrowser.open(url)
                    return
                win.title(os.path.splitext(os.path.basename(target))[0]
                          .replace('_', ' ').title())
                doc_state['content'] = new_content
                doc_state['base_dir'] = os.path.dirname(target)
                _render_doc_content()
                text.yview_moveto(0)
            else:
                webbrowser.open(url)

        def _clear_markdown_widgets():
            for tag in list(text._textbox.tag_names()):
                if tag.startswith('_url_'):
                    text._textbox.tag_delete(tag)
            for canvas, _line_id in getattr(text._textbox, '_hr_canvases', []):
                try:
                    canvas.destroy()
                except tk.TclError:
                    pass
            text._textbox._hr_canvases = []
            text._link_count = 0

        def _render_doc_content():
            _set_state(True)
            text.delete('1.0', 'end')
            if markdown:
                _clear_markdown_widgets()
                render_markdown(
                    text, doc_state['content'], self._link_color,
                    url_handler=_nav_handler, code_bg=code_bg)
            else:
                text.insert('1.0', doc_state['content'])
            _set_state(False)

        def _apply_doc_zoom(size):
            top_index = text._textbox.index('@0,0')
            text.configure(font=ctk.CTkFont(family=ui_family, size=size))
            if markdown:
                _render_doc_content()
                try:
                    text._textbox.see(top_index)
                except tk.TclError:
                    pass

        TextZoomController(
            text, ui_size, _apply_doc_zoom, targets=(win, text._textbox))

        _render_doc_content()

        if sys.platform == 'darwin':
            text._textbox.bind('<Key>', lambda *_: 'break')
        else:
            text.configure(state='disabled')

        # Thin separator
        ctk.CTkFrame(win, height=1, fg_color=("gray70", "gray30")).pack(fill='x')

        btn_frame = ctk.CTkFrame(win, fg_color='transparent')
        btn_frame.pack(fill='x', padx=12, pady=8)
        ctk.CTkButton(btn_frame, text=BTN_CLOSE, width=80,
                      command=win.destroy).pack(side='right')

        win.bind('<Up>', lambda *_: text.yview_scroll(-1, 'units') or 'break')
        win.bind('<Down>', lambda *_: text.yview_scroll(1, 'units') or 'break')
        win.bind('<Prior>', lambda *_: text.yview_scroll(-1, 'pages') or 'break')
        win.bind('<Next>', lambda *_: text.yview_scroll(1, 'pages') or 'break')
        win.bind('<Home>', lambda *_: text.yview_moveto(0) or 'break')
        win.bind('<End>', lambda *_: text.yview_moveto(1) or 'break')

        self._fit_window_to_content(
            win,
            min_w=500,
            min_h=300,
            preferred_w=820,
            preferred_h=640,
        )
        win.deiconify()
        win.focus_set()
