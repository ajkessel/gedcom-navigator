#!/usr/bin/env python3
"""
gedcom_display.py

Formatting helpers for GEDCOM individuals.
"""

def lifespan(indi):
    """Return a string representing the individual's lifespan."""
    b, d = indi.get('birth_year'), indi.get('death_year')
    if b and d:
        return f'{b}-{d}'
    if b:
        return f'b. {b}'
    if d:
        return f'd. {d}'
    return ''


def describe(indi, show_id=True):
    """Return a string describing the individual, including their name, lifespan, and ID."""
    name = indi['name'] or '(unknown)'
    span = lifespan(indi)
    if show_id:
        return f'{name} ({span}) [{indi["id"]}]' if span else f'{name} [{indi["id"]}]'
    return f'{name} ({span})' if span else name
