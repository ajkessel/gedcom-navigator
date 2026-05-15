#!/usr/bin/env python3
"""
gedcom_gui_search.py

GEDCOM loading, person-list filtering, and DNA-match search handlers.
"""

import difflib
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from gedcom_parser import extract_ged_from_zip
from gedcom_search import bfs_find_all_paths
from gedcom_strings import *  # pylint: disable=unused-wildcard-import,wildcard-import


class SearchMixin:
    """Provide load, filtering, and DNA-match search behavior for the GUI."""

    def _browse(self):
        """Prompt for a GEDCOM or ZIP file and load it when selected."""
        current = self.gedcom_path.get().strip()
        initialdir = os.path.dirname(current) if current else None
        path = filedialog.askopenfilename(
            title=DLG_SELECT_GEDCOM,
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
            messagebox.showerror(ERR_NO_FILE_TITLE, ERR_NO_FILE_MSG)
            return
        if not os.path.isfile(path):
            messagebox.showerror(ERR_NOT_FOUND_TITLE,
                                 ERR_NOT_FOUND_MSG.format(path=path))
            return

        gedcom_path = path
        tmp_path = None
        if path.lower().endswith('.zip'):
            try:
                tmp_path, ged_name = extract_ged_from_zip(path)
                gedcom_path = tmp_path
                self.status_text.set(
                    STATUS_EXTRACTED_ZIP.format(name=ged_name))
            except Exception as e:  # pylint: disable=broad-exception-caught
                messagebox.showerror(
                    ERR_ZIP_TITLE, ERR_ZIP_MSG.format(error=e))
                return

        self._show_progress(STATUS_LOADING)
        self._set_busy(True)

        dna_keyword = self.tag_keyword.get()
        page_marker = self.page_marker.get()
        cache_dir = self._cache_dir()

        def _do_load():
            try:
                result = self._model.load(
                    gedcom_path,
                    dna_keyword=dna_keyword,
                    page_marker=page_marker,
                    cache_dir=cache_dir,
                )
                self.root.after(0, lambda: _on_done(result, None))
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.root.after(0, lambda: _on_done(None, e))

        def _on_done(result, error):
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            self._hide_progress()
            self._set_busy(False)
            if error:
                self.status_text.set(STATUS_LOAD_FAILED)
                messagebox.showerror(
                    ERR_PARSE_TITLE, ERR_PARSE_MSG.format(error=error))
                return
            from_cache, encoding_warning, model_error = result
            if model_error:
                self.status_text.set(STATUS_LOAD_FAILED)
                messagebox.showerror(
                    ERR_PARSE_TITLE, ERR_PARSE_MSG.format(error=model_error))
                return
            self.individuals = self._model.individuals
            self.families = self._model.families
            self.tag_records = self._model.tag_records
            if encoding_warning:
                messagebox.showwarning(ERR_ENCODING_TITLE, encoding_warning)
            self.sorted_ids = sorted(
                self.individuals.keys(),
                key=lambda iid: (self.individuals[iid]['name'].lower(), iid),
            )
            self._add_to_history(path)
            self._home_person_id = self._load_home_person(path)
            self._populate_tree()
            status = (STATUS_LOADED_CACHED.format(count=len(self.individuals))
                      if from_cache
                      else STATUS_LOADED.format(count=len(self.individuals)))
            self.status_text.set(status)

        threading.Thread(target=_do_load, daemon=True).start()

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
        """Reload the active GEDCOM when DNA marker settings change."""
        self._dna_settings_after_id = None
        if self.individuals:
            self._load_file()

    def _refresh_result(self):
        """Recompute and redraw the most recent result view."""
        self._settings_after_id = None
        if not self._last_result or not self.individuals:
            return
        try:
            top_n = int(self.top_n.get())
            max_depth = int(self.max_depth.get())
        except (tk.TclError, ValueError):
            return
        kind = self._last_result['type']
        start_id = self._last_result['start_id']
        if kind == 'dna_matches':
            def _do_refresh():
                try:
                    results = self._model.find_dna_matches(
                        start_id, top_n, max_depth)
                    home_paths = None
                    home_id = self._home_person_id
                    if home_id and home_id != start_id and home_id in self.individuals:
                        home_paths, _ = bfs_find_all_paths(
                            start_id, home_id, self.individuals, self.families,
                            top_n=1, max_depth=max_depth,
                        )
                    self.root.after(0, lambda: self._render_results(
                        start_id, results, home_paths=home_paths))
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
            threading.Thread(target=_do_refresh, daemon=True).start()
        elif kind == 'path':
            end_id = self._last_result['end_id']
            paths, truncated = self._model.find_all_paths(
                start_id, end_id, top_n, max_depth)
            self._render_path_results(start_id, end_id, paths, truncated)

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

        self.tree.delete(*self.tree.get_children())

        if not self.individuals:
            return

        query = self.search_text.get().strip().lower()
        query_tokens = query.split()
        filter_query = self.filter_text.get().strip().lower()
        flagged_only = self.show_flagged_only.get()
        flagged_count = sum(
            1 for i in self.individuals.values() if i['dna_markers'])

        _col_labels = {'name': COL_NAME, 'birth': COL_BIRTH,
                       'death': COL_DEATH, 'flagged': COL_DNA}
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
        cache_key = (self._sort_col, self._sort_rev, id(self.sorted_ids))
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
            if query_tokens:
                all_names = indi['alt_names'] or [indi['name']]
                id_lower = indi_id.lower()
                if self.fuzzy_search.get():
                    match = (
                        any(
                            all(self._fuzzy_token_matches(tok, name.lower().split())
                                for tok in query_tokens)
                            for name in all_names
                        )
                        or query in id_lower
                    )
                else:
                    match = (
                        any(
                            all(tok in name.lower() for tok in query_tokens)
                            for name in all_names
                        )
                        or query in id_lower
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
            self.status_text.set(STATUS_SHOWING_FIRST.format(
                max_display=self.max_display.get(), total_matches=total_matches,
                total=total, flagged=flagged_count))
        elif query or flagged_only:
            self.status_text.set(STATUS_MATCHES.format(
                shown=shown, plural='es' if shown != 1 else '',
                total=total, flagged=flagged_count))
        else:
            self.status_text.set(STATUS_OVERVIEW.format(
                total=total, families=len(self.families), flagged=flagged_count))

    def _fuzzy_token_matches(self, token, name_words):
        """Return whether token fuzzily matches any word in a name."""
        try:
            threshold = float(self.fuzzy_threshold.get())
        except (tk.TclError, ValueError):
            threshold = self.FUZZY_THRESHOLD
        return any(
            difflib.SequenceMatcher(
                None, token, word).ratio() >= threshold
            for word in name_words
        )

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
        if not self.individuals:
            messagebox.showwarning(ERR_NO_DATA_TITLE, ERR_NO_DATA_MSG)
            return
        sel = self.tree.selection()
        start_id = sel[0] if sel else self._active_id
        if not start_id:
            messagebox.showwarning(ERR_NO_SEL_TITLE, ERR_NO_SEL_MSG)
            return
        try:
            top_n = int(self.top_n.get())
            max_depth = int(self.max_depth.get())
        except (tk.TclError, ValueError):
            messagebox.showerror(ERR_BAD_VAL_TITLE, ERR_BAD_VAL_TOP_N)
            return

        _slow = self._is_slow_search(max_depth, len(self.individuals))
        self._show_progress()
        self._set_busy(True)

        def _do_search(cancel_event):
            results = self._model.find_dna_matches(
                start_id, top_n, max_depth, cancel_event=cancel_event)
            home_paths = None
            home_id = self._home_person_id
            if home_id and home_id != start_id and home_id in self.individuals:
                home_paths, _ = bfs_find_all_paths(
                    start_id, home_id, self.individuals, self.families,
                    top_n=1, max_depth=max_depth, cancel_event=cancel_event,
                )
            return results, home_paths

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
            self._results_reversed = False
            self._reverse_btn.configure(text=BTN_REVERSE)
            self._last_result = {'type': 'dna_matches', 'start_id': start_id}
            self._render_results(start_id, results, home_paths=home_paths)

        self._run_background_task(
            _do_search,
            _on_done,
            popup_message=PROGRESS_SEARCHING if _slow else None,
            cancelable=True,
            on_cancel=_on_cancel,
        )
