"""Tests for tagged text PDF rendering."""

import shutil
import subprocess
from io import BytesIO

import pytest
from PIL import Image
from gedcom_pdf import (
    PDF_BODY_FONT_SIZE,
    TextStyle,
    _supported_char,
    render_text_widget_pdf,
    styled_text_runs,
)


class FakeText:
    def dump(self, *_args, **_kwargs):
        return [
            ("text", "Heading Иван שלום", "1.0"),
            ("tagon", "bold", "1.7"),
            ("text", "\nBold", "1.7"),
            ("tagoff", "bold", "2.4"),
            ("tagon", "link", "2.4"),
            ("text", " link", "2.4"),
            ("tagoff", "link", "2.9"),
            ("text", "\n──father──▶ Alex", "3.0"),
        ]

    def tag_cget(self, tag, option):
        options = {
            ("link", "foreground"): "#0066cc",
            ("link", "underline"): "1",
        }
        return options.get((tag, option), "")


class LongFakeText(FakeText):
    def dump(self, *_args, **_kwargs):
        return [("text", "\n".join(f"Line {i}" for i in range(150)), "1.0")]


class KeepTogetherFakeText(FakeText):
    def dump(self, *_args, **_kwargs):
        filler = "\n".join(f"Filler {i}" for i in range(45))
        long_line = (
            "KEEP-TOGETHER-START "
            + "wrapped-content " * 10
            + "KEEP-TOGETHER-END"
        )
        return [("text", filler + "\n" + long_line, "1.0")]


class PedigreeOrphanFakeText(FakeText):
    def dump(self, *_args, **_kwargs):
        events = [
            ("text", "\n".join(f"Filler {i}" for i in range(46)) + "\n", "1.0"),
            ("tagon", "bold", "47.0"),
            ("text", "Generation 5", "47.0"),
            ("tagoff", "bold", "47.12"),
            ("text", "\n  16. Alex Example (father)", "48.0"),
        ]
        return events


def test_pdf_body_font_size_is_fixed_at_ten_points():
    assert PDF_BODY_FONT_SIZE == 10


def test_styled_text_runs_preserve_header_and_tags():
    runs = styled_text_runs(FakeText())

    assert runs == [
        ("Heading Иван שלום", TextStyle()),
        ("\nBold", TextStyle(bold=True)),
        (" link", TextStyle(color="#0066cc", underline=True)),
        ("\n──father──▶ Alex", TextStyle()),
    ]


def test_pdf_connector_glyphs_have_ascii_fallbacks(monkeypatch):
    monkeypatch.setattr(
        "gedcom_pdf._font_supports", lambda _font_name, _char: False)

    assert _supported_char("MissingFont", "─") == "-"
    assert _supported_char("MissingFont", "▶") == ">"
    assert _supported_char("MissingFont", "A") == "A"


def test_render_text_widget_pdf_writes_pdf(tmp_path):
    path = tmp_path / "profile.pdf"

    render_text_widget_pdf(
        path,
        FakeText(),
        report_title="Profile",
        subject="Person (1900–1980)",
    )

    assert path.read_bytes().startswith(b"%PDF")
    pdftotext = shutil.which("pdftotext")
    if pdftotext is None:
        pytest.skip("pdftotext is required to verify the searchable text layer")
    extracted = subprocess.run(
        [pdftotext, str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "Profile" in extracted
    assert "Person" in extracted
    assert "1900" in extracted
    assert "GEDCOM-Navigator" in extracted
    assert "Page 1" in extracted
    assert "Heading" in extracted
    assert "Иван" in extracted
    assert "Bold link" in extracted
    assert "father" in extracted
    assert "Alex" in extracted


def test_pdf_repeats_report_header_and_numbered_footer_on_each_page(tmp_path):
    path = tmp_path / "multipage.pdf"
    render_text_widget_pdf(
        path,
        LongFakeText(),
        report_title="Matches",
        subject="Alex Example (1900–1980)",
    )

    pdftotext = shutil.which("pdftotext")
    if pdftotext is None:
        pytest.skip("pdftotext is required to verify PDF page chrome")
    extracted = subprocess.run(
        [pdftotext, "-layout", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pages = [page for page in extracted.split("\f") if page.strip()]

    assert len(pages) >= 2
    for page_number, page in enumerate(pages, start=1):
        assert "Matches" in page
        assert "Alex Example" in page
        assert "GEDCOM-Navigator" in page
        assert f"Page {page_number}" in page


def test_wrapped_logical_line_moves_whole_to_next_page(tmp_path):
    path = tmp_path / "keep-together.pdf"
    render_text_widget_pdf(
        path,
        KeepTogetherFakeText(),
        report_title="Paths",
        subject="Alex Example",
    )

    pdftotext = shutil.which("pdftotext")
    if pdftotext is None:
        pytest.skip("pdftotext is required to verify PDF pagination")
    extracted = subprocess.run(
        [pdftotext, "-layout", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pages = [page for page in extracted.split("\f") if page.strip()]

    assert len(pages) == 2
    assert "KEEP-TOGETHER-START" not in pages[0]
    assert "KEEP-TOGETHER-END" not in pages[0]
    assert "KEEP-TOGETHER-START" in pages[1]
    assert "KEEP-TOGETHER-END" in pages[1]


def test_pedigree_generation_heading_stays_with_first_entry(tmp_path):
    path = tmp_path / "pedigree-heading.pdf"
    render_text_widget_pdf(
        path,
        PedigreeOrphanFakeText(),
        report_title="Pedigree",
        subject="Alex Example",
        keep_bold_with_next=True,
    )

    pdftotext = shutil.which("pdftotext")
    if pdftotext is None:
        pytest.skip("pdftotext is required to verify PDF pagination")
    extracted = subprocess.run(
        [pdftotext, "-layout", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pages = [page for page in extracted.split("\f") if page.strip()]

    assert len(pages) == 2
    assert "Generation 5" not in pages[0]
    assert "Generation 5" in pages[1]
    assert "Alex Example (father)" in pages[1]


def test_profile_photo_is_embedded_only_on_first_page(tmp_path):
    pdfimages = shutil.which("pdfimages")
    if pdfimages is None:
        pytest.skip("pdfimages is required to inspect embedded PDF images")
    photo = BytesIO()
    Image.new("RGB", (60, 90), "navy").save(photo, format="PNG")
    path = tmp_path / "photo.pdf"

    render_text_widget_pdf(
        path,
        LongFakeText(),
        report_title="Profile",
        subject="Alex Example",
        photo_bytes=photo.getvalue(),
    )

    output = subprocess.run(
        [pdfimages, "-list", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    image_rows = [
        line.split()
        for line in output.splitlines()
        if line.strip() and line.lstrip()[0].isdigit()
    ]

    assert image_rows
    assert {row[0] for row in image_rows} == {"1"}
