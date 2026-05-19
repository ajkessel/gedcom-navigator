#!/usr/bin/env python3
"""
gedcom_gui_help_dialogs.py

Help, documentation, and update-check dialogs for GedcomNavigatorApp.
"""

import os
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import messagebox, ttk

import customtkinter as ctk

from gedcom_markdown import render_markdown
from gedcom_strings import *  # pylint: disable=unused-wildcard-import
from gedcom_update import check_for_updates
from gedcom_zoom import TextZoomController, bind_zoom_shortcuts


class HelpDialogsMixin:
    """Documentation and update-check dialog helpers."""

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
