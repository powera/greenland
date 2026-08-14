#!/usr/bin/env python3
"""
Concept entry generator (``concept.generate.entry``).

"Vovere" means "squirrel" in Lithuanian: it gathers scattered source pages and
stores them as compact encyclopedia entries (concepts).

Given a concept title, a one-sentence description, and 2-10 source URLs, Vovere
fetches the (web-page-length) source text and asks an LLM to write a concise
Markdown entry. Notable related topics are emitted as ``[[Wiki Links]]`` so the
concept corpus self-links.

This module exposes :class:`ConceptEntryGenerator` for application callers.
The animal-named module retains the manual CLI and a ``VovereAgent`` alias for
compatibility.

Usage:
    PYTHONPATH=src python src/agents/vovere/vovere.py \\
        --title "Art Deco" \\
        --summary "A decorative arts style of the 1920s-30s." \\
        --source https://example.com/art-deco \\
        --model gpt-5.4-mini
"""

import logging
import urllib.error
import urllib.request
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional, cast
from clients.lib import ChatMessage
from clients.unified_client import UnifiedLLMClient
from storage.backend.config import DataSourceConfig
from storage.models.concept import MAX_CONCEPT_SOURCES, concept_slug_to_title
from util.prompt_loader import get_context, get_prompt

logger = logging.getLogger(__name__)

STAGE_NAME: str = "concept.generate.entry"

# Category/type used to load prompts/concepts/entry/{context,prompt}.txt.
PROMPT_CATEGORY: str = "concepts"
PROMPT_TYPE: str = "entry"

# Per-source character cap (web-page length, not book length) and total budget
# of source text handed to the LLM.
PER_SOURCE_CHAR_LIMIT: int = 12000
TOTAL_SOURCE_CHAR_LIMIT: int = 40000
FETCH_TIMEOUT_SECONDS: int = 20
DEFAULT_USER_AGENT: str = "Greenland-Vovere/1.0 (concept entry generator)"
BLOCKED_SOURCE_HOSTS: frozenset[str] = frozenset({"wikidata.org", "www.wikidata.org"})


def is_allowed_generation_source_url(url: str) -> bool:
    """Return False for source URLs that are unsuitable as generation text."""
    parsed_url = urlparse(url)
    host = parsed_url.netloc.casefold()
    return host not in BLOCKED_SOURCE_HOSTS


def html_to_text(html: str) -> str:
    """Strip HTML to readable text, dropping navigation and other page chrome."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for selector in (
        "script",
        "style",
        "noscript",
        "head",
        "nav",
        "header",
        "footer",
        "aside",
        "form",
        "button",
        "menu",
        "[role='navigation']",
        "[aria-hidden='true']",
        ".mw-editsection",
        ".navbox",
        ".metadata",
        ".reference",
        ".reflist",
        ".sidebar",
        ".toc",
    ):
        for element in soup.select(selector):
            element.decompose()
    return cast(str, soup.get_text(" ", strip=True))


class ConceptEntryGenerator:
    """Generates concept bodies from sources using an LLM."""

    def __init__(self, config: DataSourceConfig, model: Optional[str] = None) -> None:
        """Initialize the agent.

        Args:
            config: Data source configuration (carries model, debug, API keys).
            model: Optional model override; falls back to ``config.model``.
        """
        self.config = config.with_model(model) if model else config
        self.model = self.config.model
        self.client = UnifiedLLMClient.from_config(self.config)

    def fetch_source_text(self, url: str) -> str:
        """Fetch a URL and return its extracted text, capped to web-page length.

        Wikipedia article URLs are routed through the dedicated parse-API
        codepath (:func:`storage.wikidata.fetch_wikipedia_source_from_url`),
        which extracts the article body and preserves internal links as
        ``[[wiki link]]`` markers. Generic ``urllib`` + BeautifulSoup scraping
        of a rendered Wikipedia page only yields page chrome ("Jump to
        content"), so the URL alone is not enough.

        Args:
            url: The source URL to fetch.

        Returns:
            Extracted plain text (possibly empty if the fetch failed).
        """
        from storage.wikidata import fetch_wikipedia_source_from_url

        wikipedia_source = fetch_wikipedia_source_from_url(url)
        if wikipedia_source is not None:
            wikipedia_text = str(wikipedia_source.get("text", "")).strip()
            if wikipedia_text:
                return wikipedia_text[:PER_SOURCE_CHAR_LIMIT]

        request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
                raw = response.read(PER_SOURCE_CHAR_LIMIT * 4)
                charset = response.headers.get_content_charset() or "utf-8"
        except (urllib.error.URLError, ValueError, TimeoutError) as error:
            logger.warning(f"Failed to fetch source {url!r}: {error}")
            return ""

        html = raw.decode(charset, errors="replace")
        return html_to_text(html)[:PER_SOURCE_CHAR_LIMIT]

    def _build_source_messages(self, sources: List[Dict[str, Any]]) -> List[ChatMessage]:
        """Fetch sources and return one user message per usable source.

        Each source becomes its own ``user`` message; the client's dialect layer
        inserts assistant acks where a provider requires alternating roles.

        Args:
            sources: Source dicts with at least a ``url`` key.

        Returns:
            A list of ``{"role": "user", "content": ...}`` messages (possibly
            empty if no source could be fetched).
        """
        messages: List[ChatMessage] = []
        budget = TOTAL_SOURCE_CHAR_LIMIT
        for index, source in enumerate(sources[:MAX_CONCEPT_SOURCES], start=1):
            url = str(source.get("url", "")).strip()
            if not url or not is_allowed_generation_source_url(url):
                continue
            provided_text = str(source.get("text", "")).strip()
            text = (
                provided_text[:PER_SOURCE_CHAR_LIMIT]
                if provided_text
                else self.fetch_source_text(url)
            )
            if not text:
                continue
            text = text[:budget]
            budget -= len(text)
            label = source.get("title") or url
            messages.append({"role": "user", "content": f"Source {index}: {label}\n\n{text}"})
            if budget <= 0:
                break
        return messages

    def build_messages(
        self, title: str, summary: str, sources: List[Dict[str, Any]]
    ) -> List[ChatMessage]:
        """Build the full message list: each source, then the instruction.

        Args:
            title: The concept title (display form, e.g. "Art Deco").
            summary: One-sentence description steering the entry.
            sources: Source dicts with at least a ``url`` key.

        Returns:
            Consecutive ``user`` messages (sources followed by the instruction
            loaded from ``prompts/concepts/entry/prompt.txt``).
        """
        display_title = concept_slug_to_title(title)
        messages = self._build_source_messages(sources)
        if not messages:
            logger.warning(
                "No source text available for %r; generating from summary only.",
                display_title,
            )
        instruction = get_prompt(PROMPT_CATEGORY, PROMPT_TYPE).format(
            title=display_title, summary=summary
        )
        messages.append({"role": "user", "content": instruction})
        return messages

    def build_request_body(
        self, title: str, summary: str, sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build the ``/v1/chat/completions`` request body for one concept.

        This is the batch-API counterpart of :meth:`generate_body`: it fetches
        sources and assembles the exact same system context + user messages, but
        returns the request payload instead of calling the LLM. Submitting this
        body to the Batch API yields the same body text at ~50% of the cost.

        Args:
            title: The concept title (display form, e.g. "Art Deco").
            summary: One-sentence description steering the entry.
            sources: Source dicts with at least a ``url`` key.

        Returns:
            A ``{"model", "messages"}`` dict suitable for ``queue_request``.

        Raises:
            ValueError: If no model is configured on the agent.
        """
        if not self.model:
            raise ValueError(
                "ConceptEntryGenerator requires a model (set config.model or pass model=)"
            )

        system_context = get_context(PROMPT_CATEGORY, PROMPT_TYPE)
        messages: List[ChatMessage] = [{"role": "system", "content": system_context}]
        messages.extend(self.build_messages(title, summary, sources))
        return {"model": self.model, "messages": messages}

    def generate_body(self, title: str, summary: str, sources: List[Dict[str, Any]]) -> str:
        """Generate a Markdown concept body from a title, summary, and sources.

        Sends each source as its own user message followed by the instruction;
        the body may contain ``[[wiki links]]``.

        Args:
            title: The concept title (display form, e.g. "Art Deco").
            summary: One-sentence description steering the entry.
            sources: Source dicts with at least a ``url`` key.

        Returns:
            The generated Markdown body.

        Raises:
            ValueError: If no model is configured on the agent.
        """
        if not self.model:
            raise ValueError(
                "ConceptEntryGenerator requires a model (set config.model or pass model=)"
            )

        # The system context frames the task and tells the model to wait for all
        # source messages; sources and the write instruction are user messages.
        system_context = get_context(PROMPT_CATEGORY, PROMPT_TYPE)
        messages = self.build_messages(title, summary, sources)
        response = self.client.generate_chat(
            "", model=self.model, context=system_context, messages=messages
        )
        return cast(str, response.response_text.strip())


# Compatibility alias while external callers migrate from the animal name.
VovereAgent = ConceptEntryGenerator
