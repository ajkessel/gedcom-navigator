#!/usr/bin/env python3
"""
gedcom_gui_person_dialog.py

Person profile and family-tree detail windows for GedcomNavigatorApp.
"""

import sys
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from gedcom_debug import debug_enabled
from gedcom_display import describe
from gedcom_family_tree import INITIAL_TREE_CATEGORIES
from gedcom_relationship import _extract_event
from gedcom_strings import *  # pylint: disable=unused-wildcard-import
from gedcom_tooltip import Tooltip
from gedcom_zoom import TextZoomController, bind_zoom_shortcuts


class PersonDialogMixin:
    """Person detail window helpers."""

    def _show_profile_from_tree_context(self, indi_id, close_tree_window):
        """Close Tree View and show indi_id in the main Display Pane profile."""
        self._select_person_in_main_tree(indi_id)
        close_tree_window()
        self.root.after_idle(lambda: self._set_display_mode("profile"))

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

    def _insert_person_profile(
        self, text, current_id, navigate_callback, tag_callback=None, home_paths=None
    ):
        """Insert the textual profile for current_id into a textbox."""
        text._textbox.tag_configure(
            "bold", font=(self._mono_family, self._mono_size, "bold")
        )
        text._textbox.tag_configure("person_link")
        text._textbox.tag_bind(
            "person_link", "<Enter>", lambda *_: text._textbox.config(cursor="hand2")
        )
        text._textbox.tag_bind(
            "person_link", "<Leave>", lambda *_: text._textbox.config(cursor="")
        )
        text._textbox.tag_configure("tag_link")
        text._textbox.tag_bind(
            "tag_link", "<Enter>", lambda *_: text._textbox.config(cursor="hand2")
        )
        text._textbox.tag_bind(
            "tag_link", "<Leave>", lambda *_: text._textbox.config(cursor="")
        )
        text._textbox.tag_configure(
            "relationship_link", foreground=self._link_color, underline=1
        )
        text._textbox.tag_bind(
            "relationship_link",
            "<Enter>",
            lambda *_: text._textbox.config(cursor="hand2"),
        )
        text._textbox.tag_bind(
            "relationship_link", "<Leave>", lambda *_: text._textbox.config(cursor="")
        )
        self._clear_person_tags(text)

        indi = self.individuals[current_id]

        def add(line="", bold=False):
            text.insert("end", line + "\n", ("bold",) if bold else ())

        def person(pid, prefix=""):
            if prefix:
                text.insert("end", prefix)
            tag = f'pers_{pid.strip("@")}'
            text.insert(
                "end",
                describe(self.individuals[pid], show_id=self.show_ids.get()),
                ("person_link", tag),
            )
            text._textbox.tag_configure(tag, foreground=self._link_color)
            text._textbox.tag_bind(
                tag, "<Button-1>", lambda _, p=pid: navigate_callback(p)
            )
            text.insert("end", "\n")

        def person_inline(pid, prefix="", suffix=""):
            if prefix:
                text.insert("end", prefix)
            tag = f'pers_{pid.strip("@")}'
            text.insert(
                "end",
                describe(self.individuals[pid], show_id=self.show_ids.get()),
                ("person_link", tag),
            )
            text._textbox.tag_configure(tag, foreground=self._link_color)
            text._textbox.tag_bind(
                tag, "<Button-1>", lambda _, p=pid: navigate_callback(p)
            )
            if suffix:
                text.insert("end", suffix)

        relationship_link_count = 0

        def relationship_line(rel, path, prefix=""):
            nonlocal relationship_link_count
            tag = f"path_graph_{relationship_link_count}"
            relationship_link_count += 1
            if prefix:
                text.insert("end", prefix)
            text.insert(
                "end", RESULT_RELATIONSHIP.format(rel=rel), ("relationship_link", tag)
            )
            text._textbox.tag_bind(
                tag,
                "<Button-1>",
                lambda _, p=tuple(path), r=rel: self._show_path_graph(p, r),
            )
            text.insert("end", "\n")

        def common_ancestor_line(ancestor_ids, prefix="", item_prefix="    "):
            if prefix:
                text.insert("end", prefix)
            if not ancestor_ids:
                text.insert("end", RESULT_COMMON_ANCESTOR)
                text.insert("end", RESULT_COMMON_ANCESTOR_NONE)
                text.insert("end", "\n")
                return
            if len(ancestor_ids) == 1:
                text.insert("end", RESULT_COMMON_ANCESTOR)
                person_inline(ancestor_ids[0])
                text.insert("end", "\n")
                return
            text.insert("end", RESULT_COMMON_ANCESTORS + "\n")
            for ancestor_id in ancestor_ids:
                person_inline(ancestor_id, prefix=item_prefix)
                text.insert("end", "\n")

        add(BIO_SECTION, bold=True)
        bio_found = False

        def fmt_event(date, place):
            parts = [p for p in (date, place) if p]
            return ", ".join(parts)

        b_date, b_place = _extract_event(indi["_raw"], "BIRT")
        if b_date or b_place:
            bio_found = True
            add(BIO_BORN.format(event=fmt_event(b_date, b_place)))

        for fam_id in indi["fams"]:
            fam = self.families.get(fam_id)
            if not fam:
                continue
            m_date = fam.get("marr_date", "")
            m_place = fam.get("marr_place", "")
            spouse_id = fam["wife"] if fam["husb"] == current_id else fam["husb"]
            spouse_name = (
                self._display_name(self.individuals[spouse_id])
                if spouse_id and spouse_id in self.individuals
                else ""
            )
            if spouse_name or m_date or m_place:
                bio_found = True
                parts = [p for p in (spouse_name, m_date, m_place) if p]
                add(BIO_MARRIED.format(spouses=", ".join(parts)))

        d_date, d_place = _extract_event(indi["_raw"], "DEAT")
        if d_date or d_place:
            bio_found = True
            add(BIO_DIED.format(event=fmt_event(d_date, d_place)))

        bu_date, bu_place = _extract_event(indi["_raw"], "BURI")
        if bu_date or bu_place:
            bio_found = True
            add(BIO_BURIED.format(event=fmt_event(bu_date, bu_place)))

        if not bio_found:
            add(BIO_NO_INFO)
        add("")

        add(FAM_SECTION, bold=True)
        family_found = False
        parents, siblings, spouses, children = self._get_family_members(current_id)

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

        self._render_home_path_section(
            current_id,
            home_paths,
            nl=add,
            person=person,
            relationship_line=relationship_line,
            common_ancestor_line=common_ancestor_line,
        )

        indi_tags = indi.get("tags", [])
        if indi_tags:
            add(TAGS_SECTION, bold=True)
            for i, tag_name in enumerate(indi_tags):
                tlink = f"taglink_{i}"
                text.insert("end", "  ")
                text.insert("end", tag_name, ("tag_link", tlink))
                text.insert("end", "\n")
                text._textbox.tag_configure(tlink, foreground=self._link_color)
                if tag_callback is not None:
                    text._textbox.tag_bind(
                        tlink, "<Button-1>", lambda _, n=tag_name: tag_callback(n)
                    )
            add("")

        if self.show_full_gedcom.get():
            add(GEDCOM_SECTION, bold=True)

            for level, xref, tag, value in indi.get("_raw", []):
                parts = [str(level)]
                if xref and self.show_ids.get():
                    parts.append(xref)
                parts.append(tag)
                if value:
                    parts.append(value)
                add(" ".join(parts))

    def _show_person_for(self, indi_id, initial_view=None, existing_window=None):
        """Open a detail window for a specific individual ID."""
        if indi_id not in self.individuals:
            messagebox.showwarning(ERR_NO_SEL_TITLE, ERR_NO_SEL_MSG)
            return
        if existing_window is None:
            existing = getattr(self, "_secondary_win", None)
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
            if getattr(self, "_path_graph_win", None) is win:
                self._path_graph_win = None
                self._path_graph_replace_fn = None
            for sequence in self._reused_person_window_bindings():
                try:
                    win.unbind(sequence)
                except tk.TclError:
                    pass
            try:
                win.unbind("<Configure>")
            except tk.TclError:
                pass
            for child in win.winfo_children():
                child.destroy()
        else:
            win = ctk.CTkToplevel(self.root)
            self._secondary_win = win
            win.withdraw()
        win.resizable(True, True)
        if sys.platform != "win32":
            win.transient(self.root)

        _geo_after = [None]

        def _on_win_configure(event):
            if event.widget is not win:
                return
            if _geo_after[0]:
                win.after_cancel(_geo_after[0])
            _geo_after[0] = win.after(
                400, lambda: self._persist_show_person_geometry(win)
            )

        def _on_destroy_person_win(*_):
            if getattr(self, "_secondary_win", None) is win:
                self._secondary_win = None
            if getattr(self, "_path_graph_win", None) is win:
                self._path_graph_win = None
                self._path_graph_replace_fn = None
            win.destroy()

        win.bind("<Escape>", _on_destroy_person_win)
        win.protocol("WM_DELETE_WINDOW", _on_destroy_person_win)

        content_frame = ctk.CTkFrame(win, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)
        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(4, 8))

        copy_shortcut = "<Command-c>" if sys.platform == "darwin" else "<Control-c>"
        save_shortcut = "<Command-s>" if sys.platform == "darwin" else "<Control-s>"
        toggle_shortcut = "<Command-t>" if sys.platform == "darwin" else "<Control-t>"
        state = {
            "person_id": indi_id,
            "mode": "person",
            "tree_expanded": [(indi_id, cat) for cat in INITIAL_TREE_CATEGORIES],
            "tree_zoom": 1.0,
            "zoom_controller": None,
            "history": [],
            "forward": [],
        }

        def _clear_content():
            for child in content_frame.winfo_children():
                child.destroy()

        def _clear_buttons():
            for child in btn_frame.winfo_children():
                child.destroy()

        def _bind_text_navigation(text_widget):
            win.bind(
                "<Up>", lambda *_: text_widget.yview_scroll(-1, "units") or "break"
            )
            win.bind(
                "<Down>", lambda *_: text_widget.yview_scroll(1, "units") or "break"
            )
            win.bind(
                "<Prior>", lambda *_: text_widget.yview_scroll(-1, "pages") or "break"
            )
            win.bind(
                "<Next>", lambda *_: text_widget.yview_scroll(1, "pages") or "break"
            )
            win.bind("<Home>", lambda *_: text_widget.yview_moveto(0) or "break")
            win.bind("<End>", lambda *_: text_widget.yview_moveto(1) or "break")

        def _bind_canvas_navigation(canvas):
            win.bind("<Up>", lambda *_: canvas.yview_scroll(-1, "units") or "break")
            win.bind("<Down>", lambda *_: canvas.yview_scroll(1, "units") or "break")
            win.bind("<Prior>", lambda *_: canvas.yview_scroll(-1, "pages") or "break")
            win.bind("<Next>", lambda *_: canvas.yview_scroll(1, "pages") or "break")
            win.bind(
                "<Home>",
                lambda *_: (canvas.xview_moveto(0), canvas.yview_moveto(0), "break")[
                    -1
                ],
            )
            win.bind(
                "<End>",
                lambda *_: (canvas.xview_moveto(1), canvas.yview_moveto(1), "break")[
                    -1
                ],
            )

        def _bind_tree_mouse_navigation(canvas):
            drag_state = {"x": 0, "y": 0}
            canvas._family_tree_dragged = False

            def _scroll_units(event):
                delta = getattr(event, "delta", 0)
                if not delta:
                    return 0
                if abs(delta) >= 120:
                    return int(-delta / 120)
                return -1 if delta > 0 else 1

            def _on_mouse_wheel(event):
                if getattr(event, "state", 0):
                    return None
                units = _scroll_units(event)
                if units:
                    canvas.yview_scroll(units, "units")
                return "break"

            def _on_linux_wheel_up(event):
                if getattr(event, "state", 0):
                    return None
                canvas.yview_scroll(-1, "units")
                return "break"

            def _on_linux_wheel_down(event):
                if getattr(event, "state", 0):
                    return None
                canvas.yview_scroll(1, "units")
                return "break"

            def _on_drag_start(event):
                canvas.focus_set()
                drag_state["x"] = event.x
                drag_state["y"] = event.y
                canvas._family_tree_dragged = False
                canvas.scan_mark(event.x, event.y)

            def _on_drag_motion(event):
                if (
                    abs(event.x - drag_state["x"]) > 3
                    or abs(event.y - drag_state["y"]) > 3
                ):
                    canvas._family_tree_dragged = True
                canvas.scan_dragto(event.x, event.y, gain=1)
                return "break"

            def _on_drag_release(_event):
                canvas.after_idle(
                    lambda: setattr(canvas, "_family_tree_dragged", False)
                )

            canvas.bind("<MouseWheel>", _on_mouse_wheel, add="+")
            canvas.bind("<Button-4>", _on_linux_wheel_up, add="+")
            canvas.bind("<Button-5>", _on_linux_wheel_down, add="+")
            canvas.bind("<ButtonPress-1>", _on_drag_start, add="+")
            canvas.bind("<B1-Motion>", _on_drag_motion, add="+")
            canvas.bind("<ButtonRelease-1>", _on_drag_release, add="+")

        def _render_person_buttons(show_tree_view, copy_profile, save_profile):
            _clear_buttons()
            ctk.CTkButton(
                btn_frame, text=BTN_CLOSE, width=80, command=win.destroy
            ).pack(side="right", padx=8)
            tree_btn = ctk.CTkButton(
                btn_frame, text=BTN_TREE_VIEW, width=90, command=show_tree_view
            )
            tree_btn.pack(side="right", padx=(0, 8))
            Tooltip(tree_btn, get_tip_tree_view_btn())
            copy_btn = ctk.CTkButton(
                btn_frame, text=BTN_COPY_GRAPH, width=80, command=copy_profile
            )
            copy_btn.pack(side="right", padx=(0, 8))
            Tooltip(copy_btn, get_tip_copy_profile())
            save_btn = ctk.CTkButton(
                btn_frame, text=BTN_SAVE_GRAPH, width=80, command=save_profile
            )
            save_btn.pack(side="right", padx=(0, 8))
            Tooltip(save_btn, get_tip_save_profile())

        def _render_tree_buttons(
            show_person_view, copy_graph, save_graph, save_debug=None
        ):
            _clear_buttons()
            ctk.CTkButton(
                btn_frame, text=BTN_CLOSE, width=80, command=win.destroy
            ).pack(side="right", padx=8)
            copy_btn = ctk.CTkButton(
                btn_frame, text=BTN_COPY_GRAPH, width=80, command=copy_graph
            )
            copy_btn.pack(side="right", padx=(0, 8))
            Tooltip(copy_btn, get_tip_copy_graph())
            save_btn = ctk.CTkButton(
                btn_frame, text=BTN_SAVE_GRAPH, width=80, command=save_graph
            )
            save_btn.pack(side="right", padx=(0, 8))
            Tooltip(save_btn, get_tip_save_graph())
            if save_debug:
                debug_btn = ctk.CTkButton(
                    btn_frame, text=BTN_DEBUG_GRAPH, width=100, command=save_debug
                )
                debug_btn.pack(side="right", padx=(0, 8))
                Tooltip(debug_btn, TIP_DEBUG_GRAPH)

        back_seq = "<Command-Left>" if sys.platform == "darwin" else "<Alt-Left>"
        fwd_seq = "<Command-Right>" if sys.platform == "darwin" else "<Alt-Right>"

        def _go_back():
            if state["history"]:
                state["forward"].append(state["person_id"])
                state["person_id"] = state["history"].pop()
                _show_person_view()

        def _go_forward():
            if state["forward"]:
                state["history"].append(state["person_id"])
                state["person_id"] = state["forward"].pop()
                _show_person_view()

        def _show_person_view(iid=None):
            if iid is not None:
                state["history"].append(state["person_id"])
                state["forward"].clear()
                state["person_id"] = iid
            current_id = state["person_id"]
            state["mode"] = "person"
            _clear_content()
            text = ctk.CTkTextbox(
                content_frame, font=(self._mono_family, self._mono_size), wrap="none"
            )
            text._textbox.configure(padx=8, pady=8)
            text.pack(fill="both", expand=True)

            def _apply_person_zoom(size):
                text.configure(font=(self._mono_family, size))
                text._textbox.tag_configure(
                    "bold", font=(self._mono_family, size, "bold")
                )

            state["zoom_controller"] = TextZoomController(
                text, self._mono_size, _apply_person_zoom, targets=(text._textbox,)
            )
            _bind_text_navigation(text)
            win.bind(back_seq, lambda *_: _go_back() or "break")
            win.bind(fwd_seq, lambda *_: _go_forward() or "break")

            indi = self.individuals[current_id]
            win.title(WIN_GEDCOM_RECORD.format(name=indi["name"] or current_id))
            text.configure(state="normal")
            text.delete("1.0", "end")

            def _on_tag_click(tag_name):
                self.tag_keyword.set(tag_name)
                self.page_marker.set("")
                self.search_text.set("")
                self.filter_text.set("")
                self.show_flagged_only.set(True)
                win.destroy()

            self._insert_person_profile(
                text, current_id, _show_person_view, tag_callback=_on_tag_click
            )

            text.configure(state="disabled")

            def _profile_content():
                body = text.get("1.0", "end").rstrip()
                title = win.title().strip()
                return (title + "\n\n" + body) if title else body

            def _copy_profile(*_):
                content = _profile_content()
                if not content:
                    return "break"
                win.clipboard_clear()
                win.clipboard_append(content)
                return "break"

            def _save_profile(*_):
                content = _profile_content()
                if not content:
                    return "break"
                path = filedialog.asksaveasfilename(
                    parent=win,
                    title=DLG_SAVE_PROFILE,
                    defaultextension=".txt",
                    filetypes=[
                        ("Text files", "*.txt"),
                        ("All files", "*.*"),
                    ],
                )
                if not path:
                    return "break"
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                        f.write("\n")
                except OSError as exc:
                    messagebox.showerror(
                        ERR_SAVE_GRAPH_TITLE,
                        ERR_SAVE_PROFILE_MSG.format(error=exc),
                        parent=win,
                    )
                return "break"

            win.bind(copy_shortcut, _copy_profile)
            win.bind(save_shortcut, _save_profile)
            _render_person_buttons(
                lambda: _show_tree_view(state["person_id"]),
                _copy_profile,
                _save_profile,
            )
            text.focus_set()

        def _show_tree_view(iid=None):
            if iid is not None:
                state["person_id"] = iid
            state["mode"] = "tree"
            state["tree_expanded"] = [
                (state["person_id"], cat) for cat in INITIAL_TREE_CATEGORIES
            ]
            _clear_content()
            indi = self.individuals[state["person_id"]]
            win.title(WIN_FAMILY_TREE.format(name=indi["name"] or state["person_id"]))

            is_dark = ctk.get_appearance_mode() == "Dark"
            colors = self._path_graph_colors(
                is_dark, getattr(self, "_theme_pref", None)
            )

            canvas_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
            canvas_frame.pack(fill="both", expand=True, padx=12, pady=(12, 0))
            canvas_frame.rowconfigure(0, weight=1)
            canvas_frame.columnconfigure(0, weight=1)

            canvas = tk.Canvas(canvas_frame, bg=colors["bg"], highlightthickness=0)
            ybar = tk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
            xbar = tk.Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
            canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            canvas.grid(row=0, column=0, sticky="nsew")
            ybar.grid(row=0, column=1, sticky="ns")
            xbar.grid(row=1, column=0, sticky="ew")

            graph_state = {
                "zoom": state["tree_zoom"],
                "canvas_w": 0,
                "canvas_h": 0,
                "debug_payload": None,
            }
            canvas.bind(
                "<Configure>",
                lambda *_: self._center_graph_canvas(
                    canvas, graph_state["canvas_w"], graph_state["canvas_h"]
                ),
                add="+",
            )

            def _redraw_tree():
                canvas.delete("all")
                graph_state["canvas_w"], graph_state["canvas_h"] = (
                    self._render_family_tree_canvas(
                        canvas,
                        state["person_id"],
                        state["tree_expanded"],
                        colors,
                        win,
                        graph_state["zoom"],
                        _expand_tree,
                        _recenter_tree,
                        _show_profile_from_tree,
                        _find_matches_from_tree,
                        _find_paths_from_tree,
                        _expand_all_tree,
                    )
                )
                graph_state["debug_payload"] = getattr(
                    canvas, "_family_tree_debug_payload", None
                )

            def _center_tree_on_current():
                canvas.update_idletasks()
                center_x, center_y = getattr(
                    canvas,
                    "_family_tree_center",
                    (graph_state["canvas_w"] / 2, graph_state["canvas_h"] / 2),
                )
                view_w = max(canvas.winfo_width(), 1)
                view_h = max(canvas.winfo_height(), 1)
                canvas_w = max(graph_state["canvas_w"], 1)
                canvas_h = max(graph_state["canvas_h"], 1)
                max_x = max(0, 1 - (view_w / canvas_w))
                max_y = max(0, 1 - (view_h / canvas_h))
                x_pos = max(0, min(max_x, (center_x - view_w / 2) / canvas_w))
                y_pos = max(0, min(max_y, (center_y - view_h / 2) / canvas_h))
                canvas.xview_moveto(x_pos)
                canvas.yview_moveto(y_pos)

            def _set_tree_zoom(zoom):
                zoom = max(0.5, min(2.5, zoom))
                if abs(zoom - graph_state["zoom"]) < 0.001:
                    return
                x0, x1 = canvas.xview()
                y0, y1 = canvas.yview()
                center_x = (x0 + x1) / 2
                center_y = (y0 + y1) / 2
                span_x = x1 - x0
                span_y = y1 - y0
                graph_state["zoom"] = zoom
                state["tree_zoom"] = zoom
                _redraw_tree()
                canvas.update_idletasks()
                canvas.xview_moveto(max(0, min(1, center_x - span_x / 2)))
                canvas.yview_moveto(max(0, min(1, center_y - span_y / 2)))

            def _zoom_tree_in():
                _set_tree_zoom(graph_state["zoom"] * 1.1)

            def _zoom_tree_out():
                _set_tree_zoom(graph_state["zoom"] / 1.1)

            def _zoom_tree_reset():
                _set_tree_zoom(1.0)

            def _maybe_grow_tree_win():
                """Grow window to fit expanded content; skip if already maximized."""
                # Detect maximized state separately so a TclError from an
                # unsupported attribute (e.g. -zoomed on macOS Aqua) is treated
                # as "not maximized" rather than aborting the whole function.
                try:
                    is_max = (
                        win.state() == "zoomed"
                        if sys.platform == "win32"
                        else bool(win.attributes("-zoomed"))
                    )
                except tk.TclError:
                    is_max = False
                if is_max:
                    return
                try:
                    win.update_idletasks()
                    tsw = self.root.winfo_screenwidth()
                    tsh = self.root.winfo_screenheight()
                    tnw = int(graph_state["canvas_w"]) + 65
                    tnh = int(graph_state["canvas_h"]) + 105
                    if tnw > int(tsw * 0.9) or tnh > int(tsh * 0.9):
                        win.state("zoomed")
                    else:
                        cur_w = win.winfo_width()
                        cur_h = win.winfo_height()
                        new_w = max(cur_w, tnw)
                        new_h = max(cur_h, tnh)
                        if new_w > cur_w or new_h > cur_h:
                            cx, cy = win.winfo_x(), win.winfo_y()
                            win.geometry(
                                f"{int(new_w)}x{int(new_h)}"
                                f"+{max(0, min(cx, tsw - new_w))}"
                                f"+{max(0, min(cy, tsh - new_h))}"
                            )
                except tk.TclError:
                    pass

            def _expand_tree(expand_id, category):
                request = (expand_id, category)
                self._toggle_expansion_request(state["tree_expanded"], request)
                _redraw_tree()
                _maybe_grow_tree_win()

            def _recenter_tree(new_center_id):
                state["person_id"] = new_center_id
                state["tree_expanded"] = [
                    (new_center_id, cat) for cat in INITIAL_TREE_CATEGORIES
                ]
                center = self.individuals[new_center_id]
                win.title(WIN_FAMILY_TREE.format(name=center["name"] or new_center_id))
                _redraw_tree()
                canvas.after_idle(_center_tree_on_current)

            def _show_profile_from_tree(indi_id):
                self._show_profile_from_tree_context(
                    indi_id, _on_destroy_person_win)

            def _find_matches_from_tree(indi_id):
                self._select_person_in_main_tree(indi_id)
                _on_destroy_person_win()
                self.root.after_idle(self._find_matches)

            def _find_paths_from_tree(indi_id):
                center_id = state["person_id"]
                self._select_person_in_main_tree(center_id)
                _on_destroy_person_win()
                self.root.after_idle(
                    lambda: self._run_path_search(center_id, indi_id))

            def _expand_all_tree(indi_id, categories):
                if self._expand_all_requests(
                    state["tree_expanded"], indi_id, categories
                ):
                    _redraw_tree()
                    _maybe_grow_tree_win()

            def _save_tree(*_):
                win.update_idletasks()
                try:
                    return self._save_graph_canvas(
                        win, canvas, graph_state, DLG_SAVE_FAMILY_TREE
                    )
                finally:
                    btn_frame.pack(fill="x", pady=(4, 8))

            def _copy_tree(*_):
                win.update_idletasks()
                try:
                    return self._copy_graph_canvas(win, canvas, graph_state)
                finally:
                    btn_frame.pack(fill="x", pady=(4, 8))

            def _save_tree_debug(*_):
                win.update_idletasks()
                try:
                    return self._save_graph_debug_payload(win, graph_state)
                finally:
                    btn_frame.pack(fill="x", pady=(4, 8))

            _redraw_tree()
            _bind_canvas_navigation(canvas)
            _bind_tree_mouse_navigation(canvas)
            bind_zoom_shortcuts(canvas, _zoom_tree_in, _zoom_tree_out, _zoom_tree_reset)
            win.bind(copy_shortcut, _copy_tree)
            win.bind(save_shortcut, _save_tree)
            graph_debug_enabled = debug_enabled()
            if graph_debug_enabled:
                win.bind("<Control-Shift-D>", _save_tree_debug)
                canvas.bind("<Control-Shift-D>", _save_tree_debug)
            _render_tree_buttons(
                lambda: _show_person_view(state["person_id"]),
                _copy_tree,
                _save_tree,
                _save_tree_debug if graph_debug_enabled else None,
            )
            canvas.focus_set()
            canvas.after_idle(_center_tree_on_current)

            # Compute needed window size from tree content plus fixed UI overhead.
            # Measured chrome at scale=1.0: padx×2 (24) + ybar (17) = 41 wide;
            # pady-top (12) + xbar (17) + btn-bar+pady (~40) = 69 tall.
            # Add a 24px horizontal and 36px vertical buffer above the measured
            # chrome so that minor geometry rounding never triggers scrollbars.
            # Use self.root (always mapped) for reliable screen dimensions.
            _tsw = self.root.winfo_screenwidth()
            _tsh = self.root.winfo_screenheight()
            _tmax_w = int(_tsw * 0.9)
            _tmax_h = int(_tsh * 0.9)
            _tnw = int(graph_state["canvas_w"]) + 65
            _tnh = int(graph_state["canvas_h"]) + 105
            _twants_max = _tnw > _tmax_w or _tnh > _tmax_h
            state["_tree_wants_max"] = _twants_max
            state["_tree_needed_w"] = min(_tnw, _tmax_w)
            state["_tree_needed_h"] = min(_tnh, _tmax_h)

            if win.winfo_viewable():
                if _twants_max:
                    if sys.platform == "win32":
                        win.state("zoomed")
                    else:
                        win.attributes("-zoomed", True)
                else:
                    _tcur_w = win.winfo_width()
                    _tcur_h = win.winfo_height()
                    _tnew_w = max(_tcur_w, state["_tree_needed_w"])
                    _tnew_h = max(_tcur_h, state["_tree_needed_h"])
                    if _tnew_w > _tcur_w or _tnew_h > _tcur_h:
                        _tcx = win.winfo_x()
                        _tcy = win.winfo_y()
                        win.geometry(
                            f"{int(_tnew_w)}x{int(_tnew_h)}"
                            f"+{max(0, min(_tcx, _tsw - _tnew_w))}"
                            f"+{max(0, min(_tcy, _tsh - _tnew_h))}"
                        )

        def _toggle_view(*_):
            if state["mode"] == "person":
                _show_tree_view(state["person_id"])
            else:
                _show_person_view(state["person_id"])

        win.bind(toggle_shortcut, _toggle_view)

        initial_view = initial_view or "profile"
        if initial_view == "tree":
            _show_tree_view(indi_id)
        else:
            _show_person_view(indi_id)

        # Use self.root for screen info — win is still withdrawn so
        # win.winfo_screenwidth() returns 0 on Windows before first show.
        _sw = self.root.winfo_screenwidth()
        _sh = self.root.winfo_screenheight()
        _mw = max(400, int(_sw * 0.9) - 32)
        _mh = max(300, int(_sh * 0.9) - 32)
        _tnw = state.get("_tree_needed_w", 0)
        _tnh = state.get("_tree_needed_h", 0)
        _twm = state.get("_tree_wants_max", False)

        if self._show_person_geometry and self._show_person_opened_this_session:
            # Subsequent open: parse saved geometry and expand for tree if needed.
            try:
                _wh = self._show_person_geometry.split("+")[0].split("-")[0]
                _sgw, _sgh = (int(p) for p in _wh.split("x"))
                _rest = self._show_person_geometry[len(_wh) :]
                _pnums = [
                    int(n)
                    for n in _rest.replace("+", " +").replace("-", " -").split()
                    if n
                ]
                _sgx, _sgy = _pnums[0], _pnums[1]
            except (ValueError, IndexError, AttributeError):
                _sgw, _sgh = 700, 520
                _sgx, _sgy = (_sw - _sgw) // 2, (_sh - _sgh) // 2
            if _tnw and not _twm:
                # Size to tree content, not to saved size.  The saved geometry
                # may have been set when a large tree caused the window to grow
                # to near-maximum; reusing that size would make every subsequent
                # small tree open at full maximum width.  Use the saved position
                # so the window re-opens near where the user left it.
                _w = min(_tnw, _mw)
                _h = min(_tnh, _mh)
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
        win.bind("<Configure>", _on_win_configure)
        win.minsize(400, 300)
        if reuse_window:
            win.update_idletasks()
            self._raise_window(win)
            return

        win.update_idletasks()
        win.geometry(f"{int(_w)}x{int(_h)}+{int(_x)}+{int(_y)}")
        self._raise_window(win)
        if _twm:
            win.state("zoomed")

    @staticmethod
    def _reused_person_window_bindings():
        """Return Toplevel bindings that should not survive a view swap."""
        mod_key = "Command" if sys.platform == "darwin" else "Control"
        return (
            "<Escape>",
            "<Up>",
            "<Down>",
            "<Prior>",
            "<Next>",
            "<Home>",
            "<End>",
            f"<{mod_key}-c>",
            f"<{mod_key}-s>",
            f"<{mod_key}-t>",
            f"<{mod_key}-plus>",
            f"<{mod_key}-equal>",
            f"<{mod_key}-KP_Add>",
            f"<{mod_key}-minus>",
            f"<{mod_key}-KP_Subtract>",
            f"<{mod_key}-0>",
            f"<{mod_key}-KP_0>",
            f"<{mod_key}-MouseWheel>",
            f"<{mod_key}-Button-4>",
            f"<{mod_key}-Button-5>",
        )
