#!/usr/bin/env python3
"""Render tagged Tk text widgets as searchable, paginated PDF files."""

import os
import sys
import tkinter.font as tkfont
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import reportlab
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

_GLYPH_FALLBACKS = {
    "─": "-",
    "▶": ">",
}
PDF_BODY_FONT_SIZE = 10


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


def styled_text_runs(widget):
    """Return ``(text, TextStyle)`` runs from a Tk Text widget dump."""
    runs = []
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


def _font_supports(font_name, char):
    if ord(char) < 128:
        return True
    font = pdfmetrics.getFont(font_name)
    char_widths = getattr(getattr(font, "face", None), "charWidths", None)
    return char_widths is not None and ord(char) in char_widths


def _supported_char(font_name, char):
    """Return a visible fallback when a PDF font lacks a connector glyph."""
    if _font_supports(font_name, char):
        return char
    return _GLYPH_FALLBACKS.get(char, char)


def _wrapped_line_groups(runs, font_names, font_size, max_width):
    """Return wrapped visual rows grouped by their original logical line."""
    line_groups = [[[]]]
    line_width = 0.0
    for text, style in runs:
        font_name = font_names[style.bold]
        for char in text:
            if char == "\n":
                line_groups.append([[]])
                line_width = 0.0
                continue
            char = _supported_char(font_name, char)
            char_width = pdfmetrics.stringWidth(char, font_name, font_size)
            if line_width and line_width + char_width > max_width:
                line_groups[-1].append([])
                line_width = 0.0
            _append_line_run(line_groups[-1][-1], char, style)
            line_width += char_width
    return line_groups


def render_text_widget_pdf(
        path, widget, report_title="", subject="", photo_bytes=None,
        keep_bold_with_next=False):
    """Write a letter-size PDF with selectable text and tagged styling."""
    page_width, page_height = letter
    margin = 0.65 * 72
    font_size = PDF_BODY_FONT_SIZE
    line_height = font_size * 1.35
    title_size = 17
    subject_size = 11
    footer_size = 8
    compact_header_rule_y = page_height - margin - 46
    footer_rule_y = margin - 6
    body_bottom = footer_rule_y + 18
    font_names = _register_pdf_fonts()
    line_groups = _wrapped_line_groups(
        styled_text_runs(widget),
        font_names,
        font_size,
        page_width - 2 * margin,
    )
    pdf = canvas.Canvas(str(path), pagesize=letter, pageCompression=1)
    page_number = 1
    photo = None
    photo_width = photo_height = 0
    if photo_bytes:
        try:
            photo = ImageReader(BytesIO(photo_bytes))
            source_width, source_height = photo.getSize()
            scale = min(72 / source_width, 72 / source_height, 1)
            photo_width = source_width * scale
            photo_height = source_height * scale
        except Exception:  # Invalid or unsupported images are simply omitted.
            photo = None

    def draw_page_header():
        has_photo = page_number == 1 and photo is not None
        header_rule_y = (
            compact_header_rule_y - photo_height - 14
            if has_photo else compact_header_rule_y
        )
        pdf.setFillColor(HexColor("#245b87"))
        pdf.setFont(font_names[True], title_size)
        pdf.drawCentredString(
            page_width / 2,
            page_height - margin - title_size,
            report_title,
        )
        if subject:
            pdf.setFillColor(HexColor("#333333"))
            pdf.setFont(font_names[False], subject_size)
            pdf.drawCentredString(
                page_width / 2,
                page_height - margin - title_size - 18,
                subject,
            )
        if has_photo:
            pdf.drawImage(
                photo,
                (page_width - photo_width) / 2,
                header_rule_y + 8,
                width=photo_width,
                height=photo_height,
                preserveAspectRatio=True,
                mask='auto',
            )
        pdf.setStrokeColor(HexColor("#8aa9bf"))
        pdf.setLineWidth(0.8)
        pdf.line(margin, header_rule_y, page_width - margin, header_rule_y)
        return header_rule_y - 20

    def draw_page_footer():
        pdf.setStrokeColor(HexColor("#c5cdd3"))
        pdf.setLineWidth(0.5)
        pdf.line(margin, footer_rule_y, page_width - margin, footer_rule_y)
        pdf.setFillColor(HexColor("#68747d"))
        pdf.setFont(font_names[False], footer_size)
        pdf.drawCentredString(
            page_width / 2,
            margin - 18,
            f"GEDCOM-Navigator  |  Page {page_number}",
        )

    body_top = draw_page_header()
    y = body_top

    def start_new_page():
        nonlocal body_top, page_number, y
        draw_page_footer()
        pdf.showPage()
        page_number += 1
        body_top = draw_page_header()
        y = body_top

    for group_index, line_group in enumerate(line_groups):
        remaining_lines = (
            int((y - body_bottom) // line_height) + 1
            if y >= body_bottom else 0
        )
        page_line_capacity = int(
            (body_top - body_bottom) // line_height) + 1
        required_lines = len(line_group)
        has_text = any(text for line in line_group for text, _style in line)
        is_bold_heading = (
            has_text
            and all(
                style.bold
                for line in line_group
                for text, style in line
                if text
            )
        )
        if (keep_bold_with_next
                and is_bold_heading
                and group_index + 1 < len(line_groups)):
            required_lines += len(line_groups[group_index + 1])
        if (required_lines > remaining_lines
                and required_lines <= page_line_capacity
                and y < body_top):
            start_new_page()

        for line in line_group:
            if y < body_bottom:
                start_new_page()
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
    draw_page_footer()
    pdf.save()
