"""Render concept bodies: resolve ``[[wiki links]]`` and minimal Markdown to HTML.

Wiki-link targets are resolved against existing :class:`~storage.models.concept.Concept`
slugs (space/underscore equivalent). Existing targets become links to the concept
page; missing targets render as plain (unlinked) text -- there are deliberately no
"red links" to a create page.
"""

import re
from typing import Dict, Set

from flask import url_for
from markupsafe import Markup, escape
from sqlalchemy.orm import Session

from storage.models.concept import Concept, parse_wiki_links

# Inline emphasis on already-escaped text (markers are literal there).
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def get_existing_link_targets(session: Session, body: str) -> Set[str]:
    """Return the set of wiki-link target slugs in ``body`` that exist as concepts.

    Args:
        session: Database session.
        body: A concept body containing ``[[...]]`` links.

    Returns:
        Canonical slugs that are both linked-to and present in the database.
    """
    targets = {link.target_slug for link in parse_wiki_links(body or "") if link.target_slug}
    if not targets:
        return set()
    rows = session.query(Concept.slug).filter(Concept.slug.in_(targets)).all()
    return {row[0] for row in rows}


def _render_inline(text: str) -> str:
    """Apply bold/italic to an already-HTML-escaped line."""
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _ITALIC_RE.sub(r"<em>\1</em>", text)
    return text


def _render_blocks(escaped: str) -> str:
    """Convert escaped text into paragraph/heading HTML (minimal Markdown)."""
    blocks = re.split(r"\n\s*\n", escaped.strip())
    html_blocks = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        heading = _HEADING_RE.match(block)
        if heading and "\n" not in block:
            level = min(len(heading.group(1)) + 2, 6)  # # -> h3, to stay below page h1/h2
            html_blocks.append(f"<h{level}>{_render_inline(heading.group(2))}</h{level}>")
            continue
        # Treat single newlines within a paragraph as line breaks.
        inner = "<br>".join(_render_inline(line) for line in block.split("\n"))
        html_blocks.append(f"<p>{inner}</p>")
    return "\n".join(html_blocks)


def render_concept_body(body: str, existing_slugs: Set[str]) -> Markup:
    """Render a concept body to safe HTML with resolved wiki links.

    Args:
        body: The raw concept body (Markdown + ``[[wiki links]]``).
        existing_slugs: Slugs known to exist (links to these become anchors).

    Returns:
        A :class:`~markupsafe.Markup` HTML fragment safe to embed in a template.
    """
    if not body:
        return Markup("")

    # Replace each wiki link with an unescapable placeholder token, remembering
    # the anchor/plain HTML to splice back in after escaping + block rendering.
    placeholders: Dict[str, Markup] = {}
    text = body
    for index, link in enumerate(parse_wiki_links(body)):
        token = f"\x00WL{index}\x00"
        text = text.replace(link.raw, token, 1)
        if link.target_slug in existing_slugs:
            href = url_for("concepts.detail", slug=link.target_slug)
            placeholders[token] = Markup('<a href="{}">{}</a>').format(href, link.display)
        else:
            placeholders[token] = Markup('<span class="wikilink-missing">{}</span>').format(
                link.display
            )

    html = _render_blocks(str(escape(text)))
    for token, anchor in placeholders.items():
        html = html.replace(token, str(anchor))
    return Markup(html)
