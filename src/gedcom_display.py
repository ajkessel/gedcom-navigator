#!/usr/bin/env python3
"""
gedcom_display.py

Formatting helpers for GEDCOM individuals.
"""

def format_year(year):
    """Format a signed year for display.

    Negative years are rendered as BCE (e.g. -44 -> '44 BC'); None -> ''.
    """
    if year is None:
        return ''
    if year < 0:
        return f'{-year} BC'
    return str(year)


def lifespan(indi):
    """Return a string representing the individual's lifespan."""
    b, d = indi.get('birth_year'), indi.get('death_year')
    if b and d:
        return f'{format_year(b)}-{format_year(d)}'
    if b:
        return f'b. {format_year(b)}'
    if d:
        return f'd. {format_year(d)}'
    return ''


def describe(indi, show_id=True):
    """Return a string describing the individual, including their name, lifespan, and ID."""
    name = indi['name'] or '(unknown)'
    span = lifespan(indi)
    if show_id:
        return f'{name} ({span}) [{indi["id"]}]' if span else f'{name} [{indi["id"]}]'
    return f'{name} ({span})' if span else name
