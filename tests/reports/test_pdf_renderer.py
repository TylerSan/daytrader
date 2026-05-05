"""Tests for PDFRenderer (markdown → HTML → PDF via weasyprint).

These tests skip cleanly if weasyprint cannot load its system libraries
(pango/cairo). On macOS, install with: `brew install pango cairo libffi`.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _weasyprint_works() -> bool:
    try:
        from weasyprint import HTML
        # Try a minimal render to detect missing system libs at runtime
        HTML(string="<html><body>x</body></html>").write_pdf()
        return True
    except Exception:
        return False


WEASYPRINT_AVAILABLE = _weasyprint_works()


@pytest.mark.skipif(not WEASYPRINT_AVAILABLE, reason="weasyprint system libs missing (brew install pango cairo libffi)")
def test_render_to_pdf_creates_file(tmp_path):
    from daytrader.reports.delivery.pdf_renderer import PDFRenderer

    markdown = (
        "# Test Report\n\n"
        "## Section A\n\n"
        "Some body text.\n\n"
        "## Section B\n\n"
        "- bullet 1\n- bullet 2\n"
    )
    renderer = PDFRenderer(output_dir=tmp_path)
    path = renderer.render_to_pdf(
        markdown_text=markdown,
        title="Premarket 2026-04-26",
        filename_stem="2026-04-26-premarket",
    )
    assert path.exists()
    assert path.suffix == ".pdf"
    assert path.read_bytes().startswith(b"%PDF")


@pytest.mark.skipif(not WEASYPRINT_AVAILABLE, reason="weasyprint system libs missing")
def test_render_to_pdf_handles_chinese_text(tmp_path):
    from daytrader.reports.delivery.pdf_renderer import PDFRenderer

    markdown = "# 盘前日报\n\n中文测试内容。\n"
    renderer = PDFRenderer(output_dir=tmp_path)
    path = renderer.render_to_pdf(
        markdown_text=markdown,
        title="测试",
        filename_stem="cn-test",
    )
    assert path.exists()
    assert path.read_bytes().startswith(b"%PDF")


def test_pdf_renderer_imports_cleanly():
    """Even when weasyprint libs are missing, the PDFRenderer module should import."""
    from daytrader.reports.delivery import pdf_renderer
    assert hasattr(pdf_renderer, "PDFRenderer")
