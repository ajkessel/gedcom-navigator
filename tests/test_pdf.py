"""Tests for tagged text PDF rendering."""

import shutil
import subprocess

import pytest
from gedcom_pdf import TextStyle, render_text_widget_pdf, styled_text_runs


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
        ]

    def tag_cget(self, tag, option):
        options = {
            ("link", "foreground"): "#0066cc",
            ("link", "underline"): "1",
        }
        return options.get((tag, option), "")


def test_styled_text_runs_preserve_header_and_tags():
    runs = styled_text_runs(FakeText(), header="Person")

    assert runs == [
        ("Person\n\n", TextStyle(bold=True)),
        ("Heading Иван שלום", TextStyle()),
        ("\nBold", TextStyle(bold=True)),
        (" link", TextStyle(color="#0066cc", underline=True)),
    ]


def test_render_text_widget_pdf_writes_pdf(tmp_path):
    path = tmp_path / "profile.pdf"

    render_text_widget_pdf(path, FakeText(), header="Person")

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
    assert "Person" in extracted
    assert "Heading" in extracted
    assert "Иван" in extracted
    assert "Bold link" in extracted
