"""PDF renderer: markdown → HTML → PDF via weasyprint.

Phase 6 v1: markdown-it-py + weasyprint. Chinese fonts rely on weasyprint's
default font fallback chain (typically picks a CJK-capable system font).

If weasyprint fails (e.g., missing system libs cairo/pango), the orchestrator
catches the exception and degrades to text-only push (per spec §5.6).
"""

from __future__ import annotations

from pathlib import Path

import markdown_it


_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
@page {{ size: A4; margin: 1.5cm; }}
body {{ font-family: -apple-system, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif; font-size: 10pt; line-height: 1.4; }}
h1 {{ font-size: 16pt; }}
h2 {{ font-size: 13pt; margin-top: 1em; }}
h3 {{ font-size: 11pt; }}
code, pre {{ font-family: "JetBrains Mono", "Menlo", monospace; font-size: 9pt; background: #f4f4f4; padding: 2px 4px; }}
pre {{ padding: 8px; overflow-x: auto; }}
table {{ border-collapse: collapse; }}
table, th, td {{ border: 1px solid #ccc; padding: 4px 8px; font-size: 9pt; }}
ul, ol {{ padding-left: 20px; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


class PDFRenderer:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._md = markdown_it.MarkdownIt(
            "commonmark", {"breaks": True, "html": False}
        ).enable("table")

    def render_to_pdf(
        self,
        markdown_text: str,
        title: str,
        filename_stem: str,
    ) -> Path:
        # Lazy-import weasyprint inside the method so the module can be
        # imported (and tests / dry-run paths can run) even when system libs
        # are missing. Import-time failures of weasyprint propagate to the
        # caller only when actual PDF rendering is attempted.
        from weasyprint import HTML

        body_html = self._md.render(markdown_text)
        full_html = _HTML_TEMPLATE.format(title=title, body=body_html)
        path = self.output_dir / f"{filename_stem}.pdf"
        HTML(string=full_html).write_pdf(str(path))
        return path
