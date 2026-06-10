#!/usr/bin/env python3
"""
gedcom_walkthrough.py

Interactive first-run walkthrough.  Highlights each area/widget of the main
window in sequence with Back / Next / Skip navigation and, using a temporarily
loaded sample tree (or whatever file is already open), demonstrates the
clickable names and relationship links in the results pane and the graph view's
node context menu.

The highlight is an "outline ring": a bright rectangle drawn just outside the
target from four thin borderless Toplevel strips, so it never covers the target
and needs no transparency/compositor support.  A small companion coach-mark
window shows the explanation and navigation buttons.
"""

import tkinter as tk

import customtkinter as ctk

import gedcom_strings as gs
from gedcom_tooltip import Tooltip

RING_COLOR = '#FF8C00'        # amber, legible on light and dark themes
RING_THICKNESS = 3
RING_PAD = 3

SAMPLE_RESOURCE = 'samples/fictional_genealogy.ged'


class _WalkthroughRing:
    """Bright rectangle around a widget or inline text range, made of four
    borderless edge strips so the target stays fully visible."""

    def __init__(self, root):
        self._root = root
        self._strips = []
        for _ in range(4):
            strip = tk.Toplevel(root)
            strip.withdraw()
            strip.overrideredirect(True)
            try:
                strip.attributes('-topmost', True)
            except tk.TclError:
                pass
            strip.configure(bg=RING_COLOR)
            self._strips.append(strip)

    def _place_rect(self, x, y, w, h):
        """Position the four strips around the inner rectangle (screen coords)."""
        t = RING_THICKNESS
        px = x - RING_PAD
        py = y - RING_PAD
        pw = w + 2 * RING_PAD
        ph = h + 2 * RING_PAD
        # (width, height, x, y) for top, bottom, left, right edges.
        geoms = [
            (pw + 2 * t, t, px - t, py - t),
            (pw + 2 * t, t, px - t, py + ph),
            (t, ph, px - t, py),
            (t, ph, px + pw, py),
        ]
        for strip, (gw, gh, gx, gy) in zip(self._strips, geoms):
            strip.geometry(
                f'{max(int(gw), 1)}x{max(int(gh), 1)}+{int(gx)}+{int(gy)}')
            strip.deiconify()
            strip.lift()

    def move_to_widget(self, widget):
        """Ring a whole widget; return its (x, y, w, h) screen rect or None."""
        try:
            widget.update_idletasks()
            if not widget.winfo_ismapped():
                self.hide()
                return None
            x, y = widget.winfo_rootx(), widget.winfo_rooty()
            w, h = widget.winfo_width(), widget.winfo_height()
        except tk.TclError:
            self.hide()
            return None
        if w <= 1 or h <= 1:
            self.hide()
            return None
        self._place_rect(x, y, w, h)
        return (x, y, w, h)

    def move_to_text_tag(self, text_widget, tag):
        """Ring the first range of a Text tag; return its screen rect or None."""
        try:
            ranges = text_widget.tag_ranges(tag)
            if not ranges:
                self.hide()
                return None
            start, end = ranges[0], ranges[1]
            text_widget.see(start)
            text_widget.update_idletasks()
            b1 = text_widget.bbox(start)
            b2 = text_widget.bbox(end)
        except tk.TclError:
            self.hide()
            return None
        if not b1:
            self.hide()
            return None
        x1, y1, _w1, h1 = b1
        if b2 and b2[1] == y1:
            width = max(b2[0] - x1, 8)
        else:
            # link wraps lines: highlight to the right edge of its first line
            width = max(text_widget.winfo_width() - x1 - 4, 8)
        rx = text_widget.winfo_rootx() + x1
        ry = text_widget.winfo_rooty() + y1
        self._place_rect(rx, ry, width, h1)
        return (rx, ry, width, h1)

    def hide(self):
        for strip in self._strips:
            try:
                strip.withdraw()
            except tk.TclError:
                pass

    def destroy(self):
        for strip in self._strips:
            try:
                strip.destroy()
            except tk.TclError:
                pass
        self._strips = []


class WalkthroughMixin:
    """Interactive guided tour of the main window and graph view."""

    # -------------------------------------------------------------- entry point
    def _show_walkthrough(self, on_end=None):
        """Start the walkthrough, or no-op if one is already running."""
        if getattr(self, '_wt_active', False):
            return
        self._wt_active = True
        self._wt_on_end = on_end
        self._wt_index = 0
        self._wt_data_ready = False
        self._wt_used_sample = False
        self._wt_opened_graph = False
        self._wt_orig_mode = self.display_mode.get()
        self._wt_orig_home = getattr(self, '_home_person_id', None)
        self._wt_prev_path = self.gedcom_path.get().strip()
        self._wt_ring = _WalkthroughRing(self.root)
        self._wt_steps = self._walkthrough_steps()
        self._wt_build_coach()
        self._wt_goto(0)

    # ------------------------------------------------------------------ steps
    def _walkthrough_steps(self):
        """Return the ordered list of walkthrough steps.

        Each step is a dict with a ``title``/``body`` and one target spec:
        ``widget`` (attribute name), ``text`` (results-pane tag), or
        ``window`` (the graph window).  Optional ``mode`` reveals mode-specific
        controls; ``needs_data`` marks steps that require a loaded tree.
        """
        def tip(widget_attr, fallback=''):
            widget = getattr(self, widget_attr, None)
            text = Tooltip.text_for(widget) if widget is not None else None
            return text or fallback

        node_items = ', '.join([
            gs.TREE_MENU_RECENTER, gs.GRAPH_MENU_HIGHLIGHT, gs.BTN_SHOW_PERSON,
            gs.BTN_FIND_MATCHES, gs.TREE_MENU_PATHS, gs.TREE_MENU_EXPAND_ALL,
        ])

        steps = [
            {'widget': 'search_entry', 'body': tip('search_entry')},
            {'widget': '_fuzzy_chk', 'body': tip('_fuzzy_chk')},
            {'widget': '_married_chk', 'body': tip('_married_chk')},
            {'widget': 'filter_entry', 'body': tip('filter_entry')},
            {'widget': '_flagged_chk', 'body': tip('_flagged_chk')},
            {'widget': 'tree', 'title': gs.WT_LIST_TITLE, 'body': gs.WT_LIST_BODY},
            {'widget': 'top_n_spin', 'body': tip('top_n_spin')},
            {'widget': 'max_depth_spin', 'body': tip('max_depth_spin')},
            {'widget': 'set_home_btn', 'body': tip('set_home_btn')},
            {'widget': '_display_mode_selector', 'title': gs.WT_MODES_TITLE,
             'body': gs.WT_MODES_BODY},
            {'widget': '_profile_sub_mode_selector', 'mode': 'profile',
             'title': gs.WT_PROFILE_SUBMODES_TITLE,
             'body': gs.WT_PROFILE_SUBMODES_BODY},
            {'widget': 'show_tree_btn', 'body': tip('show_tree_btn')},
            {'widget': 'results', 'title': gs.WT_RESULTS_TITLE,
             'body': gs.WT_RESULTS_BODY},
            {'widget': '_matches_settings_frame', 'mode': 'matches',
             'title': gs.WT_MATCHES_SETTINGS_TITLE,
             'body': gs.WT_MATCHES_SETTINGS_BODY},
            {'widget': '_reverse_btn', 'mode': 'paths',
             'body': tip('_reverse_btn')},
            {'widget': '_save_btn', 'body': tip('_save_btn')},
            {'widget': '_copy_btn', 'body': tip('_copy_btn')},
            {'text': 'person_link', 'needs_data': True,
             'title': gs.WT_PERSON_LINK_TITLE, 'body': gs.WT_PERSON_LINK_BODY},
            {'text': 'relationship_link', 'needs_data': True,
             'title': gs.WT_REL_LINK_TITLE, 'body': gs.WT_REL_LINK_BODY},
            {'window': True, 'needs_data': True,
             'title': gs.WT_NODE_MENU_TITLE,
             'body': gs.WT_NODE_MENU_BODY.format(items=node_items)},
        ]
        return steps

    # ----------------------------------------------------------- coach-mark UI
    def _wt_build_coach(self):
        """Create the persistent companion window with text and nav buttons."""
        coach = ctk.CTkToplevel(self.root)
        coach.withdraw()
        coach.title(gs.BTN_WALKTHROUGH)
        coach.resizable(False, False)
        try:
            coach.attributes('-topmost', True)
        except tk.TclError:
            pass
        coach.protocol('WM_DELETE_WINDOW', self._wt_end)
        coach.bind('<Escape>', lambda *_: self._wt_end())
        coach.bind('<Right>', lambda *_: self._wt_next())
        coach.bind('<Return>', lambda *_: self._wt_next())
        coach.bind('<Left>', lambda *_: self._wt_back())

        outer = ctk.CTkFrame(coach, fg_color='transparent')
        outer.pack(fill='both', expand=True, padx=16, pady=(14, 8))
        self._wt_title = ctk.CTkLabel(
            outer, text='', font=ctk.CTkFont(weight='bold'),
            anchor='w', justify='left', wraplength=320)
        self._wt_title.pack(fill='x')
        self._wt_body = ctk.CTkLabel(
            outer, text='', anchor='w', justify='left', wraplength=320)
        self._wt_body.pack(fill='x', pady=(6, 0))
        self._wt_progress = ctk.CTkLabel(
            outer, text='', anchor='w', justify='left',
            text_color=('gray45', 'gray60'))
        self._wt_progress.pack(fill='x', pady=(8, 0))

        ctk.CTkFrame(coach, height=1, fg_color=('gray70', 'gray30')).pack(
            fill='x')
        btns = ctk.CTkFrame(coach, fg_color='transparent')
        btns.pack(fill='x', padx=16, pady=8)
        ctk.CTkButton(btns, text=gs.BTN_WT_SKIP, width=70,
                      fg_color=('gray75', 'gray30'),
                      hover_color=('gray65', 'gray40'),
                      text_color=('gray10', 'gray90'),
                      command=self._wt_end).pack(side='left')
        self._wt_next_btn = ctk.CTkButton(
            btns, text=gs.BTN_WT_NEXT, width=80, command=self._wt_next)
        self._wt_next_btn.pack(side='right')
        self._wt_back_btn = ctk.CTkButton(
            btns, text=gs.BTN_WT_BACK, width=70, command=self._wt_back)
        self._wt_back_btn.pack(side='right', padx=(0, 6))
        self._wt_coach = coach

    def _wt_update_coach(self, step, busy=False):
        """Refresh the coach-mark text and button state for the current step."""
        # Tooltip text uses the first line as a bold heading; split it out so we
        # never repeat a single-line body as both title and body.
        if step.get('title'):
            title, body = step['title'], step.get('body', '')
        else:
            body = step.get('body', '')
            if '\n' in body:
                title, body = body.split('\n', 1)
            else:
                title, body = body, ''
        self._wt_title.configure(text=title)
        self._wt_body.configure(text=body)
        total = len(self._wt_steps)
        self._wt_progress.configure(
            text=gs.WT_SAMPLE_NOTICE if (busy or self._wt_used_sample)
            else f'{self._wt_index + 1} / {total}')
        last = self._wt_index >= total - 1
        self._wt_next_btn.configure(
            text=gs.BTN_WT_FINISH if last else gs.BTN_WT_NEXT)
        self._wt_back_btn.configure(
            state='disabled' if self._wt_index == 0 else 'normal')

    def _wt_position_coach(self, rect):
        """Place the coach-mark near the highlighted rect, clamped on-screen."""
        coach = self._wt_coach
        coach.update_idletasks()
        cw = max(coach.winfo_width(), coach.winfo_reqwidth())
        ch = max(coach.winfo_height(), coach.winfo_reqheight())
        sw = coach.winfo_screenwidth()
        sh = coach.winfo_screenheight()
        if rect:
            x, y, _w, h = rect
            cx, cy = x, y + h + 16
            if cy + ch > sh - 20:
                cy = y - ch - 16
        else:
            cx = self.root.winfo_rootx() + (self.root.winfo_width() - cw) // 2
            cy = self.root.winfo_rooty() + (self.root.winfo_height() - ch) // 2
        cx = max(20, min(int(cx), sw - cw - 20))
        cy = max(20, min(int(cy), sh - ch - 20))
        coach.geometry(f'+{cx}+{cy}')
        coach.deiconify()
        coach.lift()
        self._wt_focus_coach()

    def _wt_focus_coach(self):
        """Give the coach-mark keyboard focus so Enter/arrows drive the tour."""
        if not getattr(self, '_wt_active', False):
            return
        coach = getattr(self, '_wt_coach', None)
        if coach is None:
            return
        try:
            coach.lift()
            coach.focus_force()
        except tk.TclError:
            pass

    # --------------------------------------------------------------- navigation
    def _wt_next(self):
        if not getattr(self, '_wt_active', False):
            return
        if self._wt_index >= len(self._wt_steps) - 1:
            self._wt_end()
        else:
            self._wt_goto(self._wt_index + 1)

    def _wt_back(self):
        if getattr(self, '_wt_active', False) and self._wt_index > 0:
            self._wt_goto(self._wt_index - 1)

    def _wt_goto(self, index):
        """Show the step at ``index``, preparing data and revealing widgets."""
        if not getattr(self, '_wt_active', False):
            return
        index = max(0, min(index, len(self._wt_steps) - 1))
        self._wt_index = index
        step = self._wt_steps[index]

        if step.get('needs_data') and not self._wt_data_ready:
            self._wt_show_loading(step)
            self._wt_prepare_data(lambda: self._wt_goto(index))
            return

        mode = step.get('mode')
        if mode:
            self._set_display_mode(mode, refresh=False, prompt_for_path=False)
        if step.get('window'):
            self._wt_open_graph_window()

        rect = self._wt_highlight(step)
        self._wt_update_coach(step)
        self._wt_position_coach(rect)

    def _wt_open_graph_window(self):
        """Open the family-tree graph window on the demo person, if not already."""
        win = getattr(self, '_secondary_win', None)
        if win is not None and win.winfo_exists():
            return
        center = getattr(self, '_wt_center_id', None)
        if center and center in self.individuals:
            self._show_person_for(center, initial_view='tree')
            self._wt_opened_graph = True
            win = getattr(self, '_secondary_win', None)
            if win is not None and win.winfo_exists():
                try:
                    win.lift()
                    # The graph window focuses its own canvas as it renders, so
                    # bind Enter there too: advancing the tour works no matter
                    # which window currently holds keyboard focus.
                    win.bind('<Return>', lambda *_: self._wt_next())
                    win.bind('<KP_Enter>', lambda *_: self._wt_next())
                except tk.TclError:
                    pass
            for delay in (150, 450, 800):
                self.root.after(delay, self._wt_focus_coach)

    def _wt_highlight(self, step):
        """Drive the ring for the current step; return the highlighted rect."""
        ring = self._wt_ring
        if 'widget' in step:
            widget = getattr(self, step['widget'], None)
            if widget is None:
                ring.hide()
                return None
            return ring.move_to_widget(widget)
        if 'text' in step:
            return ring.move_to_text_tag(self.results._textbox, step['text'])
        if step.get('window'):
            win = getattr(self, '_secondary_win', None)
            if win is not None and win.winfo_exists():
                return ring.move_to_widget(win)
        ring.hide()
        return None

    def _wt_show_loading(self, step):
        """Show a transient 'loading sample' coach-mark while data prepares."""
        self._wt_ring.hide()
        self._wt_title.configure(text=step.get('title', ''))
        self._wt_body.configure(text=gs.WT_SAMPLE_NOTICE)
        self._wt_position_coach(None)

    # ---------------------------------------------------------- data preparation
    def _wt_prepare_data(self, then):
        """Ensure a tree is loaded, then render a demo profile and continue."""
        if self.individuals:
            self._wt_after_data(then)
            return
        # Nothing loaded: temporarily load the bundled sample tree.
        if self._busy:
            self.root.after(150, lambda: self._wt_prepare_data(then))
            return
        sample = self._resource_path(SAMPLE_RESOURCE)
        self.gedcom_path.set(sample)
        self._wt_used_sample = True
        self._load_file(
            add_to_history=True,
            on_loaded=lambda: self._wt_after_data(then))

    def _wt_after_data(self, then):
        """Pick a person, set a home person, and render their profile."""
        if not getattr(self, '_wt_active', False):
            return
        ids = self.sorted_ids
        if not ids:
            self._wt_data_ready = True
            then()
            return
        center = self._wt_orig_home if self._wt_orig_home in self.individuals \
            else ids[0]
        home = next((i for i in ids if i != center), center)
        self._home_person_id = home
        self._clear_home_path_cache()
        self._set_display_mode('profile', refresh=False, prompt_for_path=False)
        self._select_person_in_main_tree(center)
        self._refresh_display_pane(prompt_for_path=False)
        self._wt_center_id = center
        self._wt_data_ready = True
        # Give the async home-path render a moment to produce the relationship
        # link before we try to highlight it.
        self.root.after(500, then)

    # ---------------------------------------------------------------- teardown
    def _wt_end(self):
        """Close the walkthrough, restore prior state, and run the callback."""
        if not getattr(self, '_wt_active', False):
            return
        self._wt_active = False
        try:
            self._wt_ring.destroy()
        except tk.TclError:
            pass
        try:
            self._wt_coach.destroy()
        except tk.TclError:
            pass
        # Close the graph window if the walkthrough opened one.
        win = getattr(self, '_secondary_win', None)
        if self._wt_opened_graph and win is not None:
            try:
                if win.winfo_exists():
                    win.destroy()
                self._secondary_win = None
            except tk.TclError:
                pass
        # Restore the home person and display mode.
        self._home_person_id = self._wt_orig_home
        self._update_home_button()
        on_end = self._wt_on_end

        if self._wt_used_sample:
            self._clear_loaded_data()
            if self._wt_prev_path:
                # Reload the user's previous file (async); the open-file prompt
                # is unnecessary here, so don't run the onboarding continuation.
                self.gedcom_path.set(self._wt_prev_path)
                self._load_file(add_to_history=False)
                return
            # No prior file: fall through so the continuation opens the dialog.
        else:
            try:
                self._set_display_mode(
                    self._wt_orig_mode, refresh=bool(self.individuals),
                    prompt_for_path=False)
            except tk.TclError:
                pass
        if on_end is not None:
            on_end()
