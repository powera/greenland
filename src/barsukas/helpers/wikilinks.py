"""Render concept bodies: resolve ``[[wiki links]]`` and minimal Markdown to HTML.

Wiki-link targets are resolved against both encyclopedia tables
(:class:`~storage.models.concept.Concept` and
:class:`~storage.models.concept.SubConcept`) via
:func:`storage.queries.concept.resolve_wiki_link_targets`: slug targets resolve
main-concept-first, and ``[[Q...]]`` targets resolve through the shared Wikidata
index. Resolved targets become links to the matching detail page; missing
targets render as plain (unlinked) text -- there are deliberately no "red links"
to a create page.
"""

import re
from typing import Dict

from flask import url_for
from markupsafe import Markup, escape
from sqlalchemy.orm import Session

from storage.models.concept import parse_wiki_links, wiki_target_qid
from storage.queries.concept import ResolvedWikiTarget, resolve_wiki_link_targets

# Inline emphasis on already-escaped text (markers are literal there).
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def get_resolved_link_targets(session: Session, body: str) -> Dict[str, ResolvedWikiTarget]:
    """Resolve the wiki-link targets in ``body`` against both concept tables.

    Args:
        session: Database session (concepts backend).
        body: A concept body containing ``[[...]]`` links.

    Returns:
        Mapping of target slug (including Q-id targets like "Q42") to where it
        resolves; unresolvable targets are absent.
    """
    return resolve_wiki_link_targets(session, body or "")


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


def render_concept_body(body: str, resolved: Dict[str, ResolvedWikiTarget]) -> Markup:
    """Render a concept body to safe HTML with resolved wiki links.

    Args:
        body: The raw concept body (Markdown + ``[[wiki links]]``).
        resolved: Target resolution from :func:`get_resolved_link_targets`
            (links to these become anchors; the rest render as plain text).

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
        target = resolved.get(link.target_slug)
        if target is None:
            placeholders[token] = Markup('<span class="wikilink-missing">{}</span>').format(
                link.display
            )
            continue
        # Unpiped [[Q...]] links display the resolved page title, not the Q-id.
        display = link.display
        if "|" not in link.raw and wiki_target_qid(link.target_slug):
            display = target.title
        if target.kind == "sub_concept":
            href = url_for("concepts.sub_detail", slug=target.slug)
            placeholders[token] = Markup('<a class="wikilink-sub" href="{}">{}</a>').format(
                href, display
            )
        else:
            href = url_for("concepts.detail", slug=target.slug)
            placeholders[token] = Markup('<a href="{}">{}</a>').format(href, display)

    html = _render_blocks(str(escape(text)))
    for token, anchor in placeholders.items():
        html = html.replace(token, str(anchor))
    return Markup(html)
