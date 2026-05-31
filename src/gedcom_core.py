#!/usr/bin/env python3
"""
gedcom_core.py

Compatibility facade for the GEDCOM parser, display formatting, and graph search
modules used by the CLI and GUI.
"""

from gedcom_display import describe, format_year, lifespan
from gedcom_parser import (
    LINE_RE,
    ZIP_MAX_BYTES,
    apply_dna_flags,
    build_model,
    extract_ged_from_zip,
    extract_year,
    iter_records,
    iter_records_checked,
)
from gedcom_search import (
    SearchCancelled,
    bfs_find_all_paths,
    bfs_find_dna_matches,
    neighbors,
)

__all__ = [
    'LINE_RE',
    'SearchCancelled',
    'ZIP_MAX_BYTES',
    'apply_dna_flags',
    'bfs_find_all_paths',
    'bfs_find_dna_matches',
    'build_model',
    'describe',
    'extract_ged_from_zip',
    'extract_year',
    'format_year',
    'iter_records',
    'iter_records_checked',
    'lifespan',
    'neighbors',
]
