"""
gedcom_markdown.py

Standalone markdown-to-tkinter-Text renderer.  No dependency on the app
class; callers pass link_color explicitly.  Supports both tk.Text widgets
and customtkinter CTkTextbox (resolved via the _textbox attribute).
"""

import re
import sys
import webbrowser
import tkinter as tk
import tkinter.font as tkfont

from gedcom_debug import log_exception, log_exception_once


# Inline markdown: image (skip), link, bold, italic, code
_INLINE_RE = re.compile(
    r'!\[[^\]]*\]\([^)]*\)'      # image – discard, no capture groups
    r'|\[([^\]]+)\]\(([^)]+)\)'  # link: g1 = display text, g2 = URL
    r'|\*\*(.+?)\*\*'            # bold: g3
    r'|\*(.+?)\*'                # italic: g4
    r'|`(.+?)`'                  # inline code: g5
)


def _raw(widget):
    """Return the underlying tk.Text for a CTkTextbox, or the widget itself."""
    return getattr(widget, '_textbox', widget)


def _visual_len(text):
    """Return rendered length of markdown text after stripping markup markers."""
    t = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    t = re.sub(r'\*(.+?)\*', r'\1', t)
    t = re.sub(r'`(.+?)`', r'\1', t)
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', t)
    return len(t)


def _insert_hr(widget):
    """Embed a canvas horizontal rule that fills and resizes with the widget."""
    tw = _raw(widget)

    try:
        padx = int(tw.cget('padx'))
    except Exception:  # pylint: disable=broad-exception-caught
        log_exception("reading markdown horizontal-rule padding")
        padx = 0
    bg = tw.cget('background') or 'white'
    fg = tw.cget('foreground') or 'gray60'

    canvas = tk.Canvas(tw, height=10, bd=0, highlightthickness=0, bg=bg)
    line_id = canvas.create_line(0, 5, 10, 5, fill=fg)

    if not hasattr(tw, '_hr_canvases'):
        tw._hr_canvases = []

        def _on_resize(e):
            usable = max(10, e.width - 2 * int(tw.cget('padx') or 0))
            for c, lid in tw._hr_canvases:
                try:
                    c.configure(width=usable)
                    c.coords(lid, 0, 5, usable, 5)
                except Exception:  # pylint: disable=broad-exception-caught
                    log_exception_once(
                        'markdown-horizontal-rule-resize',
                        "resizing markdown horizontal rule",
                    )
                    pass

        tw.bind('<Configure>', _on_resize)

    tw._hr_canvases.append((canvas, line_id))
    tw.window_create('end', window=canvas)
    tw.insert('end', '\n')

    def _init_size():
        w = tw.winfo_width()
        if w > 1:
            usable = max(10, w - 2 * padx)
            canvas.configure(width=usable)
            canvas.coords(line_id, 0, 5, usable, 5)

    widget.after(1, _init_size)


def render_markdown(widget, content, link_color='#0066cc', url_handler=None,
                    code_bg='#f0f0f0'):
    """Render basic markdown into a tkinter Text widget using tag formatting."""
    tw = _raw(widget)
    try:
        base = tkfont.Font(font=tw.cget('font'))
        info = base.actual()
    except Exception:  # pylint: disable=broad-exception-caught
        log_exception("reading markdown widget font")
        info = {'family': 'TkTextFont', 'size': 10}
    family = info['family']
    size = abs(info['size']) or 10
    if sys.platform == 'darwin':
        mono = 'Menlo'
    elif sys.platform == 'win32':
        mono = 'Consolas'
    else:
        available = set(tkfont.families())
        mono = next(
            (n for n in ('DejaVu Sans Mono', 'Liberation Mono', 'Courier New')
             if n in available),
            'Courier',
        )

    tw.tag_configure('h1', font=(
        family, size + 7, 'bold'), spacing1=10, spacing3=5)
    tw.tag_configure('h2', font=(
        family, size + 4, 'bold'), spacing1=8, spacing3=4)
    tw.tag_configure('h3', font=(
        family, size + 2, 'bold'), spacing1=6, spacing3=3)
    tw.tag_configure('bold', font=(family, size, 'bold'))
    tw.tag_configure('italic', font=(family, size, 'italic'))
    tw.tag_configure('code_inline', font=(mono, size - 1), background=code_bg)
    tw.tag_configure('code_block', font=(mono, size - 1), background=code_bg,
                     lmargin1=16, lmargin2=16, spacing1=1, spacing3=1)
    tw.tag_configure('link', foreground=link_color)
    tw.tag_configure('bullet', lmargin1=16, lmargin2=32)
    tw.tag_configure('normal', font=(family, size))
    tw.tag_configure('table_cell', font=(mono, size - 1))
    tw.tag_configure('table_bold', font=(mono, size - 1, 'bold'))

    lines = content.split('\n')

    # Pre-scan: compute max visual column widths across all table rows
    _col_widths: list = []
    for _ln in lines:
        _s = _ln.strip()
        if (_s.startswith('|') and _s.endswith('|')
                and not re.match(r'^\|[\s\-:|]+\|$', _s)):
            _cells = [c.strip() for c in _s[1:-1].split('|')]
            for _j, _cell in enumerate(_cells):
                _vl = _visual_len(_cell)
                if _j >= len(_col_widths):
                    _col_widths.append(_vl)
                else:
                    _col_widths[_j] = max(_col_widths[_j], _vl)
    _divider_width = (sum(_col_widths) + 3 * len(_col_widths) + 1
                      if _col_widths else 64)

    i = 0
    in_code = False
    code_acc = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code block toggle
        if stripped.startswith('```'):
            if in_code:
                widget.insert('end', '\n'.join(code_acc) + '\n', 'code_block')
                code_acc = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue

        if in_code:
            code_acc.append(line)
            i += 1
            continue

        # ASCII-art table border row (+---+---+ or +===+===+)
        if re.match(r'^\+[-=+]+\+$', stripped):
            widget.insert('end', '─' * _divider_width + '\n', 'table_cell')
            i += 1
            continue

        # GFM table separator row – skip
        if re.match(r'^\|[\s\-:|]+\|$', stripped):
            i += 1
            continue

        # ATX headers (up to ###)
        hm = re.match(r'^(#{1,3})\s+(.*)', stripped)
        if hm:
            insert_inline(widget, hm.group(2), 'h' + str(len(hm.group(1))),
                          link_color, url_handler=url_handler)
            widget.insert('end', '\n')
            i += 1
            continue

        # Horizontal rule
        if re.match(r'^[-*_]{3,}\s*$', stripped):
            _insert_hr(widget)
            i += 1
            continue

        # Table row
        if stripped.startswith('|') and stripped.endswith('|'):
            cells = [c.strip() for c in stripped[1:-1].split('|')]
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
            is_header = bool(
                re.match(r'^\|[\s\-:|]+\|$', next_line) or
                re.match(r'^\+[=+]+\+$', next_line)
            )
            base_tag = 'table_bold' if is_header else 'table_cell'
            widget.insert('end', '│ ', base_tag)
            for j, cell in enumerate(cells):
                insert_inline(widget, cell, base_tag, link_color,
                              bold_tag='table_bold', url_handler=url_handler)
                pad = (_col_widths[j] - _visual_len(cell)
                       if j < len(_col_widths) else 0)
                suffix = ' ' * max(0, pad) + ' │'
                if j < len(cells) - 1:
                    suffix += ' '
                widget.insert('end', suffix, base_tag)
            widget.insert('end', '\n')
            i += 1
            continue

        # Bullet list
        bm = re.match(r'^[-*+]\s+(.*)', stripped)
        if bm:
            insert_inline(widget, '• ' + bm.group(1), 'bullet', link_color,
                          url_handler=url_handler)
            widget.insert('end', '\n')
            i += 1
            continue

        # Numbered list
        nm = re.match(r'^(\d+\.)\s+(.*)', stripped)
        if nm:
            insert_inline(widget, nm.group(1) + ' ' + nm.group(2), 'bullet',
                          link_color, url_handler=url_handler)
            widget.insert('end', '\n')
            i += 1
            continue

        # Empty line
        if not stripped:
            widget.insert('end', '\n')
            i += 1
            continue

        # Normal paragraph line
        insert_inline(widget, line, 'normal', link_color,
                      url_handler=url_handler)
        widget.insert('end', '\n')
        i += 1

    if code_acc:
        widget.insert('end', '\n'.join(code_acc) + '\n', 'code_block')


def insert_inline(widget, text, base_tag, link_color='#0066cc',
                  bold_tag='bold', url_handler=None):
    """Insert text with inline markdown (bold, italic, code, links) into widget."""
    tw = _raw(widget)
    pos = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            widget.insert('end', text[pos:m.start()], base_tag)
        g1, g2, g3, g4, g5 = m.group(1), m.group(
            2), m.group(3), m.group(4), m.group(5)
        if g1 is not None:
            url = g2
            lc = getattr(widget, '_link_count', 0)
            widget._link_count = lc + 1
            tag = f'_url_{lc}'
            _open = url_handler if url_handler is not None else webbrowser.open
            tw.tag_configure(tag, foreground=link_color)
            tw.tag_bind(tag, '<Button-1>', lambda _, u=url, h=_open: h(u))
            tw.tag_bind(tag, '<Enter>', lambda _: tw.config(cursor='hand2'))
            tw.tag_bind(tag, '<Leave>', lambda _: tw.config(cursor=''))
            if not hasattr(widget, '_url_tags'):
                widget._url_tags = {}
            widget._url_tags[tag] = url
            widget.insert('end', g1, (base_tag, tag))
        elif g3 is not None:
            widget.insert('end', g3, (base_tag, bold_tag))
        elif g4 is not None:
            widget.insert('end', g4, (base_tag, 'italic'))
        elif g5 is not None:
            widget.insert('end', g5, 'code_inline')
        # else: image – discard silently
        pos = m.end()
    if pos < len(text):
        widget.insert('end', text[pos:], base_tag)
