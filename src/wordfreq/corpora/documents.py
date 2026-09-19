"""Readers for the locally cached corpus text, as ``(slug, text)`` documents.

These are the three sources with text on disk: the downloaded Gutenberg books,
the cached SCOTUS case JSON, and the Wikipedia articles read out of the dump.
Each yields the same ``Document`` shape the corpus builders already hand to
``frequency_build.analyze_book``, so a new analysis can be written against the
cache without knowing how any one source stores itself.

They were written for ``scripts/find_hyphenated_candidates.py`` and live here
now because the co-occurrence build needs the same three readers.  Copying them
would have meant two definitions of "every cached book, deduplicated" drifting
apart -- and the deduplication is the part worth stating once: a book belongs
to more than one book list, and an article to more than one wiki corpus, so
both are yielded once or their contents are counted twice.

Nothing here touches the network or the database, and nothing writes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator, Tuple

from wordfreq.corpora.book_lists import get_book_list, get_corpus_names
from wordfreq.corpora.download_gutenberg import text_path
from wordfreq.corpora.gutenberg_text import strip_gutenberg_boilerplate
from wordfreq.corpora.scotus_text import iter_opinions

logger = logging.getLogger(__name__)

#: One document: a stable slug and its raw text.
Document = Tuple[str, str]

#: The sources this module can read, for CLI ``--sources`` validation.
SOURCE_NAMES: Tuple[str, ...] = ("gutenberg", "scotus", "wikipedia")

# The SCOTUS builder's own floors, so a scan sees the same text the corpus does
# rather than a wider or narrower slice of it.
SCOTUS_MIN_CHARS = 2000
SCOTUS_MIN_YEAR = 1950


def gutenberg_documents(cache_dir: Path) -> Iterator[Document]:
    """Every cached book across all Gutenberg book lists, deduplicated.

    A book may appear in more than one list; it is yielded once, or its
    contents would be counted twice for no reason.
    """
    seen: set[int] = set()
    for corpus_name in get_corpus_names():
        book_list = get_book_list(corpus_name)
        for book in book_list.books:
            if book.gutenberg_id in seen:
                continue
            seen.add(book.gutenberg_id)
            path = text_path(cache_dir, book.gutenberg_id)
            if not path.exists():
                logger.debug("not cached, skipping: %s", path)
                continue
            raw_text = path.read_text(encoding="utf-8", errors="replace")
            # The same strip analyze_book performs. Without it the licence
            # header dominates any count: "re-use", "machine-readable",
            # "non-profit" and "e-mail" appear in every single book because
            # Project Gutenberg's boilerplate says so, not because the
            # 19th-century novels do.
            yield book.slug, strip_gutenberg_boilerplate(raw_text)


def scotus_documents(cache_dir: Path) -> Iterator[Document]:
    """Every opinion in every cached CAP case."""
    for path in sorted(cache_dir.glob("case_*.json")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            logger.warning("%s: unreadable, skipping", path)
            continue
        for opinion in iter_opinions(case, min_chars=SCOTUS_MIN_CHARS, min_year=SCOTUS_MIN_YEAR):
            yield opinion.slug, opinion.text


def wikipedia_documents() -> Iterator[Document]:
    """Every article of every Wikipedia corpus, deduplicated by title.

    Imported lazily: ``build_wikipedia`` reaches the dump snapshot at import
    time, and that lives on an external drive.
    """
    from wordfreq.corpora.build_wikipedia import (
        WIKIPEDIA_CORPORA,
        slugify_title,
        wikitext_to_plain_text,
    )
    from wordfreq.corpora.wikipedia.article_lists import flatten
    from wordfreq.corpora.wikipedia.wiki_dump import WikiLoader

    loader = WikiLoader()
    seen: set[str] = set()
    for corpus in WIKIPEDIA_CORPORA.values():
        for title in flatten(corpus.articles):
            if title in seen:
                continue
            seen.add(title)
            try:
                wikitext = loader.get_text_from_page(title)
            except (ValueError, RuntimeError) as error:
                logger.debug("%s: %s", title, error)
                continue
            text = wikitext_to_plain_text(wikitext, title)
            if text:
                yield slugify_title(title), text
