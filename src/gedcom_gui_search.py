#!/usr/bin/env python3
"""
gedcom_gui_search.py

GEDCOM loading, person-list filtering, and DNA-match search handlers.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from gedcom_name_search import individual_matches_query
from gedcom_parser import extract_ged_from_zip
import gedcom_strings as gs


class SearchMixin:
    """Provide load, filtering, and DNA-match search behavior for the GUI."""

    def _suppress_path_prompt_after_cancel(self):
        """Temporarily ignore immediate follow-on path prompts after Cancel."""
        self._path_prompt_cancelled = True

        root = getattr(self, "root", None)
        if root is None or not hasattr(root, "after"):
            return

        after_id = getattr(self, "_path_prompt_cancel_after_id", None)
        if after_id:
            try:
                root.after_cancel(after_id)
            except tk.TclError:
                pass

        def clear_suppression():
            self._path_prompt_cancelled = False
            self._path_prompt_cancel_after_id = None

        try:
            self._path_prompt_cancel_after_id = root.after(
                150, clear_suppression)
        except tk.TclError:
            self._path_prompt_cancel_after_id = None

    def _path_prompt_cancelled_recently(self):
        """Return True while an immediate post-cancel re-prompt should be ignored."""
        return bool(getattr(self, "_path_prompt_cancelled", False))

    def _set_reverse_button_visible(self, visible):
        """Show the Reverse button only when it applies to the active mode."""
        button = getattr(self, "_reverse_btn", None)
        if button is None:
            return
        try:
            if visible:
                button.grid()
            else:
                button.configure(state="disabled", text=gs.BTN_REVERSE)
                button.grid_remove()
        except tk.TclError:
            pass

    def _set_matches_settings_visible(self, visible):
        """Show DNA marker controls only when Matches mode is active."""
        frame = getattr(self, "_matches_settings_frame", None)
        if frame is None:
            return
        try:
            if visible:
                frame.grid()
            else:
                frame.grid_remove()
        except tk.TclError:
            pass

    def _browse(self):
        """Prompt for a GEDCOM or ZIP file and load it when selected."""
        current = self.gedcom_path.get().strip()
        initialdir = os.path.dirname(current) if current else None
        path = filedialog.askopenfilename(
            title=gs.DLG_SELECT_GEDCOM,
            filetypes=[("GEDCOM files", "*.ged *.gedcom *.zip"),
                       ("All files", "*.*")],
            initialdir=initialdir,
        )
        if path:
            self.gedcom_path.set(path)
            self._load_file()

    def _load_file(self):
        """Load the selected GEDCOM file into the model and refresh the UI."""
        if self._busy:
            return
        path = self.gedcom_path.get().strip()
        if not path:
            messagebox.showerror(gs.ERR_NO_FILE_TITLE, gs.ERR_NO_FILE_MSG)
            return
        if not os.path.isfile(path):
            messagebox.showerror(gs.ERR_NOT_FOUND_TITLE,
                                 gs.ERR_NOT_FOUND_MSG.format(path=path))
            return

        self._show_progress(gs.STATUS_LOADING)
        self._set_busy(True)

        dna_keyword = self.tag_keyword.get()
        page_marker = self.page_marker.get()
        cache_dir = self._cache_dir()

        def _do_load():
            tmp_path = None
            ged_name = None
            try:
                gedcom_path = path
                if path.lower().endswith('.zip'):
                    tmp_path, ged_name = extract_ged_from_zip(path)
                    gedcom_path = tmp_path
                result = self._model.load(
                    gedcom_path,
                    dna_keyword=dna_keyword,
                    page_marker=page_marker,
                    cache_dir=cache_dir,
                )
                self.root.after(
                    0, lambda: _on_done(result, None, tmp_path, ged_name))
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.root.after(
                    0, lambda e=e, tmp_path=tmp_path: _on_done(
                        None, e, tmp_path, ged_name))

        def _on_done(result, error, tmp_path=None, ged_name=None):
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            self._hide_progress()
            self._set_busy(False)
            if error:
                self.status_text.set(gs.STATUS_LOAD_FAILED)
                if path.lower().endswith('.zip') and ged_name is None:
                    messagebox.showerror(
                        gs.ERR_ZIP_TITLE, gs.ERR_ZIP_MSG.format(error=error))
                else:
                    messagebox.showerror(
                        gs.ERR_PARSE_TITLE, gs.ERR_PARSE_MSG.format(error=error))
                return
            from_cache, encoding_warning, model_error = result
            if model_error:
                self.status_text.set(gs.STATUS_LOAD_FAILED)
                messagebox.showerror(
                    gs.ERR_PARSE_TITLE, gs.ERR_PARSE_MSG.format(error=model_error))
                return
            self.individuals = self._model.individuals
            self.families = self._model.families
            self.tag_records = self._model.tag_records
            self._display_path_target_id = None
            self._last_result = None
            if encoding_warning:
                messagebox.showwarning(gs.ERR_ENCODING_TITLE, encoding_warning)
            self.sorted_ids = sorted(
                self.individuals.keys(),
                key=lambda iid: (self.individuals[iid]['name'].lower(), iid),
            )
            self._add_to_history(path)
            self._home_person_id = self._load_home_person(path)
            self._populate_tree()
            status = (gs.STATUS_LOADED_CACHED.format(count=len(self.individuals))
                      if from_cache
                      else gs.STATUS_LOADED.format(count=len(self.individuals)))
            self.status_text.set(status)

        self.root.after(10, lambda: threading.Thread(
            target=_do_load, daemon=True).start())

    def _on_settings_change(self, *_):
        """Debounce search depth and result count changes before rerendering."""
        if self._settings_after_id is not None:
            self.root.after_cancel(self._settings_after_id)
        self._settings_after_id = self.root.after(400, self._refresh_result)

    def _on_dna_settings_change(self, *_):
        """Debounce DNA marker setting changes before reloading data."""
        if self._dna_settings_after_id is not None:
            self.root.after_cancel(self._dna_settings_after_id)
        self._dna_settings_after_id = self.root.after(
            800, self._reload_if_loaded)

    def _reload_if_loaded(self):
        """Re-flag DNA matches in-place when marker settings change."""
        self._dna_settings_after_id = None
        if not self.individuals or self._busy:
            return
        dna_keyword = self.tag_keyword.get()
        page_marker = self.page_marker.get()
        self._model.reflag(dna_keyword, page_marker)
        self._populate_tree()

    def _find_home_path_data(self, start_id, max_depth, cancel_event=None):
        """Return path data from start_id to the configured home person."""
        home_id = self._home_person_id
        if not home_id or home_id not in self.individuals:
            return None
        if home_id == start_id:
            return {'home_id': home_id, 'paths': [[(start_id, None)]]}
        home_paths, _ = self._model.find_all_paths(
            start_id, home_id, top_n=1, max_depth=max_depth,
            cancel_event=cancel_event)
        return {'home_id': home_id, 'paths': home_paths}

    def _find_dna_result_data(self, start_id, top_n, max_depth, cancel_event=None):
        """Return DNA search results plus the optional path to the home person."""
        results = self._model.find_dna_matches(
            start_id, top_n, max_depth, cancel_event=cancel_event)
        return (
            results,
            self._find_home_path_data(
                start_id, max_depth, cancel_event=cancel_event),
        )

    def _on_display_mode_selected(self, label):
        """Handle a click on the Display Pane mode selector."""
        mode = self._display_mode_by_label.get(label, 'profile')
        if mode == 'paths':
            self._find_path()
            # Revert button visual if picker was cancelled (mode unchanged).
            self._sync_display_mode_selector()
        else:
            self._set_display_mode(mode)

    def _sync_display_mode_selector(self):
        """Keep the mode selector widget in sync with display_mode."""
        selector = getattr(self, '_display_mode_selector', None)
        labels = getattr(self, '_display_mode_labels', {})
        label = labels.get(self.display_mode.get())
        if selector is None or label is None:
            return
        if hasattr(selector, 'set'):
            selector.set(label)
        else:
            radio_var = getattr(self, '_display_mode_radio_var', None)
            if radio_var is not None:
                radio_var.set(label)

    def _set_display_mode(self, mode, refresh=True, prompt_for_path=True):
        """Select the active Display Pane mode."""
        if mode not in ('profile', 'matches', 'paths'):
            mode = 'profile'
        self.display_mode.set(mode)
        self._set_reverse_button_visible(mode == 'paths')
        self._set_matches_settings_visible(mode == 'matches')
        self._sync_display_mode_selector()
        if refresh:
            self._refresh_display_pane(prompt_for_path=prompt_for_path)

    def _selected_or_active_id(self):
        """Return the selected person, falling back to the active person."""
        sel = self.tree.selection()
        return sel[0] if sel else self._active_id

    def _on_tree_selection_change(self, *_):
        """Refresh the Display Pane after the selected person changes."""
        if getattr(self, '_suppress_display_refresh', False):
            return
        self._refresh_display_pane()

    def _refresh_display_pane(self, prompt_for_path=True):
        """Refresh the active Display Pane mode for the selected person."""
        if self._busy or not self.individuals:
            return
        start_id = self._selected_or_active_id()
        if not start_id:
            return
        mode = self.display_mode.get()
        self._set_reverse_button_visible(mode == 'paths')
        self._set_matches_settings_visible(mode == 'matches')
        if mode == 'profile':
            self._results_reversed = False
            self._reverse_btn.configure(state='disabled', text=gs.BTN_REVERSE)
            self._last_result = {'type': 'profile', 'start_id': start_id}
            self._render_profile_result(start_id)
        elif mode == 'matches':
            self._find_matches()
        elif mode == 'paths':
            target_id = getattr(self, '_display_path_target_id', None)
            if (not target_id or target_id not in self.individuals
                    or target_id == start_id):
                if self._path_prompt_cancelled_recently():
                    return
                if not prompt_for_path:
                    return
                target_id = self._pick_person(gs.WIN_SELECT_TARGET)
                if not target_id:
                    self._suppress_path_prompt_after_cancel()
                    return
                self._display_path_target_id = target_id
            self._run_path_search(start_id, target_id)

    def _refresh_result(self):
        """Recompute and redraw the active Display Pane view."""
        self._settings_after_id = None
        if self._busy or not self._last_result or not self.individuals:
            return
        try:
            top_n = int(self.top_n.get())
            max_depth = int(self.max_depth.get())
        except (tk.TclError, ValueError):
            return
        kind = self._last_result['type']
        start_id = self._last_result['start_id']
        if kind == 'profile':
            self._render_profile_result(
                start_id, self._find_home_path_data(start_id, max_depth))
            return
        self._show_progress()
        self._set_busy(True)
        if kind == 'dna_matches':
            def _do_refresh(cancel_event):
                return self._find_dna_result_data(
                    start_id, top_n, max_depth, cancel_event=cancel_event)

            def _on_done(result, error):
                self._hide_search_popup()
                self._hide_progress()
                self._set_busy(False)
                if error:
                    messagebox.showerror(gs.ERR_PARSE_TITLE, str(error))
                    return
                results, home_paths = result
                self._render_results(start_id, results, home_paths=home_paths)

            self._run_background_task(
                _do_refresh,
                _on_done,
                popup_message=(
                    gs.PROGRESS_SEARCHING
                    if self._is_slow_search(max_depth, len(self.individuals))
                    else None
                ),
                cancelable=True,
                on_cancel=lambda: (self._hide_progress(), self._set_busy(False)),
            )
        elif kind == 'path':
            end_id = self._last_result['end_id']

            def _do_refresh(cancel_event):
                paths, truncated = self._model.find_all_paths(
                    start_id, end_id, top_n, max_depth,
                    cancel_event=cancel_event)
                home_path_data = self._find_home_path_data(
                    start_id, max_depth, cancel_event=cancel_event)
                return paths, truncated, home_path_data

            def _on_done(result, error):
                self._hide_search_popup()
                self._hide_progress()
                self._set_busy(False)
                if error:
                    messagebox.showerror(gs.ERR_PARSE_TITLE, str(error))
                    return
                paths, truncated, home_path_data = result
                self._render_path_results(
                    start_id, end_id, paths, truncated, home_path_data)

            self._run_background_task(
                _do_refresh,
                _on_done,
                popup_message=gs.PROGRESS_FINDING_PATH,
                cancelable=True,
                on_cancel=lambda: (self._hide_progress(), self._set_busy(False)),
            )
        else:
            self._hide_progress()
            self._set_busy(False)

    def _on_search_change(self, *_):
        """Debounce person-list filtering while the user types."""
        if self._search_after_id is not None:
            self.root.after_cancel(self._search_after_id)
        self._search_after_id = self.root.after(150, self._populate_tree)

    def _search_flush_and_jump(self):
        """Apply pending search filters immediately and select the first row."""
        if self._search_after_id is not None:
            self.root.after_cancel(self._search_after_id)
            self._search_after_id = None
            self._populate_tree()
        self._tree_jump('first')

    def _populate_tree(self):
        """Populate the people list using current search, filter, and sort settings."""
        self._search_after_id = None
        prev_sel = self.tree.selection()
        prev_id = prev_sel[0] if prev_sel else None
        old_suppress = getattr(self, '_suppress_display_refresh', False)
        self._suppress_display_refresh = True

        try:
            self.tree.delete(*self.tree.get_children())

            if not self.individuals:
                return

            query = self.search_text.get().strip()
            filter_query = self.filter_text.get().strip().lower()
            flagged_only = self.show_flagged_only.get()
            extra_names_by_id = (
                self._model.married_name_index
                if self.married_name_search.get()
                else {}
            )
            flagged_count = sum(
                1 for i in self.individuals.values() if i['dna_markers'])

            _col_labels = {'name': gs.COL_NAME, 'birth': gs.COL_BIRTH,
                           'death': gs.COL_DEATH, 'flagged': gs.COL_DNA}
            for _col, _label in _col_labels.items():
                suffix = (
                    ' ▼' if self._sort_rev else ' ▲') if _col == self._sort_col else ''
                self.tree.heading(_col, text=_label + suffix)

            def _sort_key(indi_id):
                indi = self.individuals[indi_id]
                name = self._display_name(indi).lower()
                if self._sort_col == 'birth':
                    by = indi['birth_year']
                    return (by is None, by or 0, name)
                if self._sort_col == 'death':
                    dy = indi['death_year']
                    return (dy is None, dy or 0, name)
                if self._sort_col == 'flagged':
                    return (not bool(indi['dna_markers']), name)
                return (name, indi_id)

            # Re-sort only when sort settings or underlying data change.
            # id(self.sorted_ids) changes whenever a new file is loaded.
            cache_key = (
                self._sort_col, self._sort_rev, id(self.sorted_ids),
                self._name_order,
            )
            if getattr(self, '_pop_sort_key', None) != cache_key:
                self._pop_sorted = sorted(self.sorted_ids, key=_sort_key,
                                          reverse=self._sort_rev)
                self._pop_sort_key = cache_key
            display_ids = self._pop_sorted

            shown = 0
            total_matches = 0
            truncated = False
            for indi_id in display_ids:
                indi = self.individuals[indi_id]
                if flagged_only and not indi['dna_markers']:
                    continue
                if query:
                    match, _score = individual_matches_query(
                        indi_id, indi, query,
                        fuzzy=self.fuzzy_search.get(),
                        fuzzy_threshold=self._fuzzy_threshold_value(),
                        extra_names=extra_names_by_id.get(indi_id),
                    )
                    if not match:
                        continue
                if filter_query:
                    raw_text = ' '.join(v.lower() for _, _, _, v in indi['_raw'])
                    if filter_query not in raw_text:
                        continue
                total_matches += 1
                if shown >= self.max_display.get():
                    truncated = True
                    continue
                tags = ('flagged_row',) if indi['dna_markers'] else ()
                flagged_mark = '✓' if indi['dna_markers'] else ''
                self.tree.insert(
                    '', 'end', iid=indi_id,
                    values=(self._display_name(indi),
                            indi['birth_year'] or '',
                            indi['death_year'] or '',
                            flagged_mark),
                    tags=tags,
                )
                shown += 1

            if prev_id and self.tree.exists(prev_id):
                self.tree.selection_set(prev_id)
                self.tree.see(prev_id)
            elif shown == 1 and (query or flagged_only):
                only = self.tree.get_children()[0]
                self.tree.selection_set(only)
                self.tree.see(only)

            total = len(self.individuals)
            if truncated and (query or flagged_only):
                self.status_text.set(gs.STATUS_SHOWING_FIRST.format(
                    max_display=self.max_display.get(), total_matches=total_matches,
                    total=total, flagged=flagged_count))
            elif query or flagged_only:
                self.status_text.set(gs.STATUS_MATCHES.format(
                    shown=shown, plural='es' if shown != 1 else '',
                    total=total, flagged=flagged_count))
            else:
                self.status_text.set(gs.STATUS_OVERVIEW.format(
                    total=total, families=len(self.families), flagged=flagged_count))
        finally:
            self._suppress_display_refresh = old_suppress

    def _fuzzy_threshold_value(self):
        """Return the configured fuzzy threshold, falling back to the default."""
        try:
            return float(self.fuzzy_threshold.get())
        except (tk.TclError, ValueError):
            return self.FUZZY_THRESHOLD

    def _sort_by(self, col):
        """Toggle sorting for the people list by the requested column."""
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False
        self._populate_tree()

    def _find_matches(self):
        """Find and display nearest DNA-flagged matches for the selected person."""
        if self._busy:
            return
        if getattr(self, 'display_mode', None) is not None:
            self._set_display_mode('matches', refresh=False)
        if not self.individuals:
            messagebox.showwarning(gs.ERR_NO_DATA_TITLE, gs.ERR_NO_DATA_MSG)
            return
        sel = self.tree.selection()
        start_id = sel[0] if sel else self._active_id
        if not start_id:
            messagebox.showwarning(gs.ERR_NO_SEL_TITLE, gs.ERR_NO_SEL_MSG)
            return
        try:
            top_n = int(self.top_n.get())
            max_depth = int(self.max_depth.get())
        except (tk.TclError, ValueError):
            messagebox.showerror(gs.ERR_BAD_VAL_TITLE, gs.ERR_BAD_VAL_TOP_N)
            return

        _slow = self._is_slow_search(max_depth, len(self.individuals))
        self._show_progress()
        self._set_busy(True)

        def _do_search(cancel_event):
            return self._find_dna_result_data(
                start_id, top_n, max_depth, cancel_event=cancel_event)

        def _on_cancel():
            self._hide_progress()
            self._set_busy(False)

        def _on_done(result, error):
            self._hide_search_popup()
            self._hide_progress()
            self._set_busy(False)
            if error:
                messagebox.showerror(gs.ERR_PARSE_TITLE, str(error))
                return
            results, home_paths = result
            self._results_reversed = False
            self._reverse_btn.configure(text=gs.BTN_REVERSE)
            self._last_result = {'type': 'dna_matches', 'start_id': start_id}
            self._render_results(start_id, results, home_paths=home_paths)

        self._run_background_task(
            _do_search,
            _on_done,
            popup_message=gs.PROGRESS_SEARCHING if _slow else None,
            cancelable=True,
            on_cancel=_on_cancel,
        )
