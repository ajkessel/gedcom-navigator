#!/usr/bin/env python3
"""
gedcom_gui_background.py

Background worker, busy-state, and progress-dialog helpers for the GUI.
"""

import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from gedcom_debug import log_exception
from gedcom_strings import *  # pylint: disable=unused-wildcard-import,wildcard-import
from gedcom_theme import ttk_colors


class BackgroundTaskMixin:
    """Provide background task and progress helpers for the main GUI class."""

    def _show_progress(self, msg=None):
        """Reveal the animated progress bar and optionally set status text."""
        if msg:
            self.status_text.set(msg)
        self._save_btn.grid_remove()
        self._copy_btn.grid_remove()
        self._progress_bar.grid()
        self._progress_anim_val = 0.0
        if self._progress_anim_id is None:
            self._tick_progress()
        self.root.update_idletasks()

    def _tick_progress(self):
        """Advance the progress bar animation one step."""
        self._progress_anim_val = (self._progress_anim_val + 0.03) % 1.0
        self._progress_bar.set(self._progress_anim_val)
        self._progress_anim_id = self.root.after(50, self._tick_progress)

    def _hide_progress(self):
        """Stop and hide the progress bar."""
        if self._progress_anim_id is not None:
            self.root.after_cancel(self._progress_anim_id)
            self._progress_anim_id = None
        self._progress_bar.grid_remove()
        self._save_btn.grid()
        self._copy_btn.grid()

    def _run_background_task(self, work, done, *, popup_message=None,
                             cancelable=False, on_cancel=None,
                             popup_delay_ms=0, popup_owner=None):
        """Run CPU-heavy work in a thread and deliver its result on the Tk thread."""
        result_queue = queue.Queue(maxsize=1)
        cancel_event = threading.Event() if cancelable else None
        cancelled = {'value': False}
        finished = {'value': False}
        popup_after_id = {'value': None}
        switch_interval = sys.getswitchinterval()
        using_fast_switch = switch_interval > 0.001

        def _worker():
            try:
                if cancel_event is None:
                    result_queue.put((work(), None))
                else:
                    result_queue.put((work(cancel_event), None))
            except Exception as e:  # pylint: disable=broad-exception-caught
                log_exception("running background task")
                result_queue.put((None, e))

        def _cancel_task():
            if cancel_event is None or cancelled['value']:
                return
            cancelled['value'] = True
            cancel_event.set()
            self._background_cancel_event = None
            after_id = popup_after_id.get('value')
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
                popup_after_id['value'] = None
            self._hide_search_popup()
            if on_cancel:
                on_cancel()

        def _poll_result():
            try:
                result, error = result_queue.get_nowait()
            except queue.Empty:
                self.root.after(50, _poll_result)
                return
            finished['value'] = True
            after_id = popup_after_id.get('value')
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
                popup_after_id['value'] = None
            if using_fast_switch:
                sys.setswitchinterval(switch_interval)
            if cancel_event is not None and self._background_cancel_event is cancel_event:
                self._background_cancel_event = None
            if cancelled['value']:
                return
            done(result, error)

        def _start_worker():
            if cancelled['value']:
                return
            if using_fast_switch:
                sys.setswitchinterval(0.0005)
            threading.Thread(target=_worker, daemon=True).start()
            _poll_result()

        if cancel_event is not None:
            self._background_cancel_event = cancel_event
        if popup_message:
            def _show_delayed_popup():
                popup_after_id['value'] = None
                if finished['value'] or cancelled['value']:
                    return
                self._show_search_popup(
                    popup_message,
                    on_cancel=_cancel_task if cancelable else None,
                    owner=popup_owner,
                )

            if popup_delay_ms:
                popup_after_id['value'] = self.root.after(
                    popup_delay_ms, _show_delayed_popup)
                _start_worker()
            else:
                _show_delayed_popup()
                # Let Tk process the popup's map/expose events before starting a
                # CPU-heavy Python thread that will compete with the GUI for the GIL.
                self.root.after(100, _start_worker)
        else:
            _start_worker()

    def _set_busy(self, busy):
        """Disable or re-enable the controls that trigger long operations."""
        self._busy = busy
        state = 'disabled' if busy else 'normal'
        selector = getattr(self, '_display_mode_selector', None)
        if selector is not None:
            try:
                selector.configure(state=state)
            except (tk.TclError, ValueError):
                pass
        show_tree_btn = getattr(self, 'show_tree_btn', None)
        if show_tree_btn is not None:
            show_tree_btn.configure(state=state)
        self._file_menu.entryconfigure(MENU_OPEN_GEDCOM, state=state)

    # ---------------------------------------------------------- Search popup
    _SLOW_SEARCH_THRESHOLD = 50_000

    @staticmethod
    def _is_slow_search(max_depth, n_individuals):
        """Predict whether a BFS DNA-match search will be noticeably slow."""
        return max_depth * n_individuals > BackgroundTaskMixin._SLOW_SEARCH_THRESHOLD

    def _show_search_popup(self, message=PROGRESS_SEARCHING, on_cancel=None,
                           owner=None):
        """Show a centered progress dialog for slow searches."""
        if self._search_popup is not None:
            return
        owner = self._valid_popup_owner(owner)
        # Use tk.Toplevel rather than ctk.CTkToplevel to avoid the Windows-only
        # deferred deiconify callback in CTkToplevel that races with destroy()
        # when the search finishes before the ~10 ms title bar-color timer fires.
        popup = tk.Toplevel(owner)
        popup.withdraw()  # hide until positioned to avoid flash at 0,0
        popup.title(PROGRESS_SEARCHING_TITLE)
        popup.resizable(False, False)
        try:
            popup.transient(owner)
        except tk.TclError:
            popup.transient(self.root)
        popup.protocol("WM_DELETE_WINDOW", lambda: None)

        # Use plain ttk widgets — CTk widgets defer rendering via after() timers
        # that update_idletasks() does not flush, leaving the window blank.
        frame = ttk.Frame(popup, padding=(20, 14))
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=message).pack(pady=(0, 10))
        bar = ttk.Progressbar(frame, mode='indeterminate', length=260)
        bar.pack(pady=(0, 10 if on_cancel else 4))
        if on_cancel:
            if sys.platform == 'darwin':
                is_dark = ctk.get_appearance_mode() == 'Dark'
                colors = ttk_colors(is_dark, self._theme_pref)
                cancel_btn = tk.Label(
                    frame,
                    text=BTN_CANCEL,
                    bg=colors['select_bg'],
                    fg=colors['select_fg'],
                    activebackground=colors['select_bg'],
                    activeforeground=colors['select_fg'],
                    padx=18,
                    pady=5,
                    relief='raised',
                    bd=1,
                    cursor='hand2',
                    takefocus=True,
                )
                cancel_btn.bind('<Button-1>', lambda *_: on_cancel())
                cancel_btn.bind('<Return>', lambda *_: on_cancel())
                cancel_btn.bind('<space>', lambda *_: on_cancel())
                cancel_btn.pack()
            else:
                ttk.Button(frame, text=BTN_CANCEL, command=on_cancel).pack()

        self._fit_window_to_content(popup, min_w=300, min_h=80)
        if owner is not self.root:
            self._center_popup_on_owner(popup, owner)
        popup.deiconify()
        try:
            popup.lift(owner)
        except tk.TclError:
            popup.lift()
        self._search_popup = popup
        self._search_popup_bar = bar
        self._tick_search_popup_progress()

    def _valid_popup_owner(self, owner):
        """Return a live window suitable as a transient owner."""
        if owner is None:
            return self.root
        try:
            if owner.winfo_exists():
                return owner
        except tk.TclError:
            pass
        return self.root

    def _center_popup_on_owner(self, popup, owner):
        """Center popup over owner instead of over the main app window."""
        try:
            popup.update_idletasks()
            owner.update_idletasks()
            w = popup.winfo_width()
            h = popup.winfo_height()
            owner_x = owner.winfo_x()
            owner_y = owner.winfo_y()
            owner_w = owner.winfo_width()
            owner_h = owner.winfo_height()
            screen_w = popup.winfo_screenwidth()
            screen_h = popup.winfo_screenheight()
            x = owner_x + (owner_w - w) // 2
            y = owner_y + (owner_h - h) // 2
            x = max(0, min(x, screen_w - w))
            y = max(0, min(y, screen_h - h))
            popup.geometry(f"{w}x{h}+{x}+{y}")
        except tk.TclError:
            pass

    def _tick_search_popup_progress(self):
        """Advance the search popup's progress bar one step."""
        if self._search_popup is None or self._search_popup_bar is None:
            self._search_popup_anim_id = None
            return
        try:
            self._search_popup_bar.step(6)
        except tk.TclError:
            self._search_popup_anim_id = None
            return
        self._search_popup_anim_id = self.root.after(
            50, self._tick_search_popup_progress)

    def _pulse_search_popup_progress(self):
        """Advance the search popup immediately during synchronous GUI work."""
        if self._search_popup is None or self._search_popup_bar is None:
            return
        try:
            self._search_popup_bar.step(6)
            self._search_popup.update_idletasks()
        except tk.TclError:
            pass

    def _hide_search_popup(self):
        """Destroy the search progress dialog."""
        if self._search_popup_anim_id is not None:
            try:
                self.root.after_cancel(self._search_popup_anim_id)
            except tk.TclError:
                pass
            self._search_popup_anim_id = None
        if self._search_popup is not None:
            try:
                self._search_popup.destroy()
            except tk.TclError:
                pass
            self._search_popup = None
        self._search_popup_bar = None
