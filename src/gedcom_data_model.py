#!/usr/bin/env python3
"""
gedcom_data_model.py

Data layer: GEDCOM loading, JSON caching, and BFS search.
Isolated from all GUI concerns — no tkinter imports.
"""

import hashlib
import json
import os
from pathlib import Path

from gedcom_core import (
    build_model,
    bfs_find_dna_matches,
    bfs_find_all_paths
)


class GedcomDataModel:
    """Owns the parsed GEDCOM state and all I/O against it."""

    # Bump this whenever the cached individual/family schema changes so that
    # stale cache files are automatically discarded and reparsed.
    _CACHE_VERSION = 3

    def __init__(self):
        self.individuals = {}
        self.families = {}
        self.tag_records = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, gedcom_path, dna_keyword, page_marker, cache_dir):
        """Parse (or restore from cache) a GEDCOM file.

        Returns (from_cache, encoding_warning).
        encoding_warning is a string or None; always None when loaded from cache.
        """
        cached = self._load_from_cache(
            gedcom_path, dna_keyword, page_marker, cache_dir)
        if cached is not None:
            self.individuals, self.families, self.tag_records = cached
            return True, None

        self.individuals, self.families, self.tag_records, warning = build_model(
            gedcom_path,
            dna_keyword=dna_keyword,
            page_marker=page_marker,
        )
        self._save_to_cache(gedcom_path, dna_keyword, page_marker, cache_dir)
        return False, warning

    def find_dna_matches(self, start_id, top_n, max_depth):
        """Find the nearest DNA-flagged people to a given individual."""
        return bfs_find_dna_matches(
            start_id, self.individuals, self.families,
            top_n=top_n, max_depth=max_depth,
        )

    def find_all_paths(self, start_id, end_id, top_n, max_depth):
        """Find up to top_n relationship paths between two individuals."""
        return bfs_find_all_paths(
            start_id, end_id, self.individuals, self.families,
            top_n=top_n, max_depth=max_depth,
        )

    def clear_cache(self, cache_dir):
        """Delete all .json cache files under cache_dir. Returns count deleted."""
        deleted = 0
        try:
            for f in Path(cache_dir).glob('*.json'):
                try:
                    f.unlink()
                    deleted += 1
                except OSError:
                    pass
        except Exception: # pylint: disable=broad-exception-caught
            pass
        return deleted

    # ------------------------------------------------------------------
    # Cache internals
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_path(gedcom_path, cache_dir):
        key = os.path.normcase(os.path.abspath(gedcom_path)).encode()
        return Path(cache_dir) / (hashlib.md5(key).hexdigest() + '.json')

    def _load_from_cache(self, gedcom_path, dna_keyword, page_marker, cache_dir):
        try:
            cache_file = self._cache_path(gedcom_path, cache_dir)
            if not cache_file.exists():
                return None
            file_mtime = os.path.getmtime(gedcom_path)
            with cache_file.open('r', encoding='utf-8') as f:
                data = json.load(f)
            if (data.get('cache_version') != self._CACHE_VERSION
                    or data.get('mtime') != file_mtime
                    or data.get('dna_keyword') != dna_keyword
                    or data.get('page_marker') != page_marker):
                return None
            return data['individuals'], data['families'], data['tag_records']
        except Exception: # pylint: disable=broad-exception-caught
            return None

    def _save_to_cache(self, gedcom_path, dna_keyword, page_marker, cache_dir):
        try:
            cache_dir_path = Path(cache_dir)
            cache_dir_path.mkdir(parents=True, exist_ok=True)
            cache_file = self._cache_path(gedcom_path, cache_dir_path)
            payload = {
                'cache_version': self._CACHE_VERSION,
                'mtime': os.path.getmtime(gedcom_path),
                'dna_keyword': dna_keyword,
                'page_marker': page_marker,
                'individuals': self.individuals,
                'families': self.families,
                'tag_records': self.tag_records,
            }
            tmp = cache_file.with_suffix('.tmp')
            with tmp.open('w', encoding='utf-8') as f:
                json.dump(payload, f)
            tmp.replace(cache_file)
        except Exception: # pylint: disable=broad-exception-caught
            pass
