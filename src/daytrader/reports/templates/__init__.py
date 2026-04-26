"""AI prompt templates per report type."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent


def load_template(name: str) -> str:
    """Read template by name (without .md suffix)."""
    path = TEMPLATE_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {name}")
    return path.read_text()
