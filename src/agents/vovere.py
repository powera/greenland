#!/usr/bin/env python3
"""
Vovere - Concept entry generator.

"Vovere" means "squirrel" in Lithuanian: it gathers scattered source pages and
stores them as compact encyclopedia entries (concepts).

Given a concept title, a one-sentence description, and 2-10 source URLs, Vovere
fetches the (web-page-length) source text and asks an LLM to write a concise
Markdown entry. Notable related topics are emitted as ``[[Wiki Links]]`` so the
concept corpus self-links.

This module exposes :class:`VovereAgent` for use by Barsukas (the
``concepts`` routes) and as bulk-operation scripts, plus a small CLI for manual
generation.

Usage:
    PYTHONPATH=src python src/agents/vovere.py \\
        --title "Art Deco" \\
        --summary "A decorative arts style of the 1920s-30s." \\
        --source https://example.com/art-deco \\
        --model gpt-5.4-mini
"""

import argparse
import logging
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from clients.lib import ChatMessage
from clients.unified_client import UnifiedLLMClient
from storage.backend.config import DataSourceConfig
from storage.models.concept import MAX_CONCEPT_SOURCES, concept_slug_to_title
from util.prompt_loader import get_context, get_prompt

logger = logging.getLogger(__name__)

# Category/type used to load prompts/concepts/entry/{context,prompt}.txt.
PROMPT_CATEGORY: str = "concepts"
PROMPT_TYPE: str = "entry"

# Per-source character cap (web-page length, not book length) and total budget
# of source text handed to the LLM.
PER_SOURCE_CHAR_LIMIT: int = 12000
TOTAL_SOURCE_CHAR_LIMIT: int = 40000
FETCH_TIMEOUT_SECONDS: int = 20
DEFAULT_USER_AGENT: str = "Greenland-Vovere/1.0 (concept entry generator)"


class _TextExtractor(HTMLParser):
    """Minimal HTML-to-text extractor that skips script/style content."""

    _SKIP_TAGS = {"script", "style", "noscript", "head"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Any]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._chunks.append(text)

    def get_text(self) -> str:
        return " ".join(self._chunks)


def html_to_text(html: str) -> str:
    """Strip HTML to readable text, dropping script/style content."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception as error:  # malformed HTML should not crash generation
        logger.warning(f"HTML parse error, using partial text: {error}")
    return parser.get_text()


class VovereAgent:
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

        Args:
            url: The source URL to fetch.

        Returns:
            Extracted plain text (possibly empty if the fetch failed).
        """
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
            if not url:
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
            raise ValueError("VovereAgent requires a model (set config.model or pass model=)")

        # The system context frames the task and tells the model to wait for all
        # source messages; sources and the write instruction are user messages.
        system_context = get_context(PROMPT_CATEGORY, PROMPT_TYPE)
        messages = self.build_messages(title, summary, sources)
        response = self.client.generate_chat(
            "", model=self.model, context=system_context, messages=messages
        )
        return cast(str, response.response_text.strip())


def main() -> int:
    """CLI entry point for manual concept-body generation."""
    parser = argparse.ArgumentParser(description="Vovere - generate a concept entry body")
    parser.add_argument("--title", required=True, help="Concept title, e.g. 'Art Deco'")
    parser.add_argument("--summary", default="", help="One-sentence description of the topic")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        dest="sources",
        help="Source URL (repeatable, up to %d)" % MAX_CONCEPT_SOURCES,
    )
    parser.add_argument("--model", required=True, help="LLM model, e.g. gpt-5.4-mini")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = DataSourceConfig.from_env().with_model(args.model, debug=args.debug)
    agent = VovereAgent(config)
    sources: List[Dict[str, Any]] = [{"url": url} for url in args.sources]
    body = agent.generate_body(args.title, args.summary, sources)
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
