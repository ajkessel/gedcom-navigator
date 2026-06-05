#!/usr/bin/env python3
"""Render tagged Tk text widgets as searchable, paginated PDF files."""

import os
import sys
import tkinter.font as tkfont
from dataclasses import dataclass
from pathlib import Path

import reportlab
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


@dataclass(frozen=True)
class TextStyle:
    """Visual properties used for one PDF text run."""

    color: str = "#1a1a1a"
    bold: bool = False
    underline: bool = False


def _is_true(value):
    return str(value).lower() not in ("", "0", "false", "normal", "none")


def _tag_option(widget, tag, option):
    try:
        return widget.tag_cget(tag, option)
    except Exception:  # Tk raises TclError for unsupported/missing options.
        return ""


def _tag_is_bold(widget, tag):
    font_name = _tag_option(widget, tag, "font")
    if not font_name:
        return tag == "bold"
    try:
        return tkfont.Font(font=font_name).actual("weight") == "bold"
    except Exception:
        return tag == "bold"


def styled_text_runs(widget, header=""):
    """Return ``(text, TextStyle)`` runs from a Tk Text widget dump."""
    runs = []
    if header:
        runs.append((header + "\n\n", TextStyle(bold=True)))

    active_tags = []
    for event, value, _index in widget.dump(
            "1.0", "end-1c", text=True, tag=True):
        if event == "tagon":
            active_tags.append(value)
            continue
        if event == "tagoff":
            if value in active_tags:
                active_tags.remove(value)
            continue
        if event != "text" or not value:
            continue

        color = "#1a1a1a"
        bold = False
        underline = False
        for tag in active_tags:
            foreground = _tag_option(widget, tag, "foreground")
            if foreground:
                color = foreground
            bold = bold or _tag_is_bold(widget, tag)
            underline = underline or _is_true(
                _tag_option(widget, tag, "underline"))
        style = TextStyle(color=color, bold=bold, underline=underline)
        if runs and runs[-1][1] == style:
            runs[-1] = (runs[-1][0] + value, style)
        else:
            runs.append((value, style))
    return runs


def _font_candidates(bold):
    if sys.platform == "win32":
        name = "consolab.ttf" if bold else "consola.ttf"
        candidates = [
            os.path.join(
                os.environ.get("WINDIR", "C:\\Windows"), "Fonts", name),
        ]
    elif sys.platform == "darwin":
        name = "Courier New Bold.ttf" if bold else "Courier New.ttf"
        candidates = [
            os.path.join("/System/Library/Fonts/Supplemental", name),
            os.path.join("/Library/Fonts", name),
        ]
    else:
        filename = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
        candidates = [
            os.path.join("/usr/share/fonts/truetype/dejavu", filename),
            os.path.join("/usr/share/dejavu", filename),
        ]
    fallback = "VeraMoBd.ttf" if bold else "VeraMono.ttf"
    candidates.append(
        str(Path(reportlab.__file__).resolve().parent / "fonts" / fallback))
    return candidates


def _register_pdf_fonts():
    font_names = {False: "GedcomMono", True: "GedcomMonoBold"}
    registered = set(pdfmetrics.getRegisteredFontNames())
    for bold, name in font_names.items():
        if name in registered:
            continue
        for candidate in _font_candidates(bold):
            if not os.path.isfile(candidate):
                continue
            try:
                pdfmetrics.registerFont(TTFont(name, candidate))
                break
            except (OSError, ValueError):
                continue
        else:
            font_names[bold] = "Courier-Bold" if bold else "Courier"
    return font_names


def _append_line_run(line, text, style):
    if line and line[-1][1] == style:
        line[-1] = (line[-1][0] + text, style)
    else:
        line.append((text, style))


def _wrapped_lines(runs, font_names, font_size, max_width):
    lines = [[]]
    line_width = 0.0
    for text, style in runs:
        font_name = font_names[style.bold]
        for char in text:
            if char == "\n":
                lines.append([])
                line_width = 0.0
                continue
            char_width = pdfmetrics.stringWidth(char, font_name, font_size)
            if line_width and line_width + char_width > max_width:
                lines.append([])
                line_width = 0.0
            _append_line_run(lines[-1], char, style)
            line_width += char_width
    return lines


def render_text_widget_pdf(path, widget, header="", font_size=12):
    """Write a letter-size PDF with selectable text and tagged styling."""
    page_width, page_height = letter
    margin = 0.65 * 72
    font_size = max(8, font_size)
    line_height = font_size * 1.35
    font_names = _register_pdf_fonts()
    lines = _wrapped_lines(
        styled_text_runs(widget, header),
        font_names,
        font_size,
        page_width - 2 * margin,
    )
    pdf = canvas.Canvas(str(path), pagesize=letter, pageCompression=1)
    y = page_height - margin - font_size

    for line in lines:
        if y < margin:
            pdf.showPage()
            y = page_height - margin - font_size
        x = margin
        for text, style in line:
            font_name = font_names[style.bold]
            try:
                color = HexColor(style.color)
            except (TypeError, ValueError):
                color = HexColor("#1a1a1a")
            pdf.setFont(font_name, font_size)
            pdf.setFillColor(color)
            pdf.drawString(x, y, text)
            width = pdfmetrics.stringWidth(text, font_name, font_size)
            if style.underline and text.strip():
                pdf.setStrokeColor(color)
                pdf.setLineWidth(0.6)
                pdf.line(x, y - 1.5, x + width, y - 1.5)
            x += width
        y -= line_height
    pdf.save()
