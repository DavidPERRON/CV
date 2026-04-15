"""Render the adapted CV markdown into HTML (and optionally PDF via WeasyPrint).

Kept intentionally simple — placeholder substitution, same approach as
ai_press_review.publish.episode_brief.
"""
from __future__ import annotations

import html
import logging
from pathlib import Path

from markdown_it import MarkdownIt

log = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


def markdown_to_html(md_text: str) -> str:
    md = MarkdownIt("commonmark", {"html": False, "breaks": False})
    return md.render(md_text)


def render_cv_html(
    cv_markdown: str,
    *,
    name: str,
    role_target: str,
    contact: str,
    language: str = "en",
    template_name: str = "cv-template.html",
) -> str:
    tmpl_path = TEMPLATE_DIR / template_name
    template = tmpl_path.read_text(encoding="utf-8")
    body_html = markdown_to_html(cv_markdown)
    return (
        template.replace("{{LANG}}", html.escape(language.lower()))
        .replace("{{TITLE}}", html.escape(f"{name} — {role_target}"))
        .replace("{{NAME}}", html.escape(name))
        .replace("{{ROLE_TARGET}}", html.escape(role_target))
        .replace("{{CONTACT}}", html.escape(contact))
        .replace("{{BODY_HTML}}", body_html)
    )


def html_to_pdf(html_content: str, out_path: Path) -> Path:
    """Render HTML to PDF using WeasyPrint. WeasyPrint is an optional dep."""
    try:
        from weasyprint import HTML
    except ImportError as e:
        raise RuntimeError(
            "weasyprint not installed. `pip install weasyprint` and its system deps "
            "(libpango, libcairo, libgdk-pixbuf)."
        ) from e
    HTML(string=html_content).write_pdf(str(out_path))
    return out_path
