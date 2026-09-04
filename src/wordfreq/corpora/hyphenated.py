"""Count hyphenated compounds across the corpora, which the tokenizer discards.

The corpus tokenizer deliberately keeps a plain hyphen out of
:data:`wordfreq.corpora.gutenberg_text.DASH_VARIANTS`, so ``RAW_TOKEN_RE``
splits "non-linear" into "non" and "linear" (see the comment there, and
``test_hyphen_still_splits_a_compound``).  That is the right default for an
unknown compound, but it has a cost: the fragments are credited as words.  In
the current database ``non`` ranks 301 and ``self`` 381, with ``re``, ``pre``,
``anti``, ``semi``, ``multi`` and ``ex`` all inside the top 4000 -- none of them
a lemma, none of them excluded, all of them artifacts.

Nothing can be done about that until the real compounds are known: the phrase
index (:mod:`wordfreq.corpora.lemma_phrases`) joins only forms the database
already holds, so a hyphenated lemma has to exist before the tokenizer can be
taught to keep it.  This module is the discovery half of that -- it reports
which hyphenated compounds the corpora actually contain, so they can be curated
and imported.  It writes nothing and changes no counts.

**Why this re-tokenizes rather than reading the corpus JSON.**  The published
``data/wordfreq/*.json`` files are built from the same tokenizer and so have
already lost every hyphen.  The hyphens survive only in the cached source text,
which is why this reads that instead.

**What counts as a hyphenated compound here.**  The text is normalized by
:func:`wordfreq.corpora.gutenberg_text._normalize` first, so em dashes, en
dashes and ``--`` have already become spaces and cannot be mistaken for
compound joiners.  What is left is a plain ASCII hyphen between two letter
runs.  Line-broken words are the trap: a hyphen at end of line is usually
typesetting rather than a compound, so a hyphen followed by a newline is not
counted.

Corpus differences are handled by
:class:`~wordfreq.corpora.hyphenated.DocumentSource`, which is just an iterator
of ``(slug, raw_text)`` pairs -- the same shape the three builders already feed
to ``frequency_build.analyze_book``.  The counting below is written once and
runs over any of them.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Tuple

from wordfreq.corpora.gutenberg_text import _normalize

logger = logging.getLogger(__name__)

#: One document: a stable slug and its raw text.  Matches what the corpus
#: builders already hand to ``frequency_build.analyze_book``.
Document = Tuple[str, str]

#: A named, lazily-read collection of documents.  Lazy because the Gutenberg
#: and SCOTUS caches are hundreds of files and Wikipedia reads a dump.
DocumentSource = Callable[[], Iterator[Document]]

# A hyphenated compound: two letter runs joined by a single ASCII hyphen, with
# optional further hyphenated parts ("well-to-do", "self-similar").  Letters
# only -- a digit anywhere means a date range, a section number or a page
# reference rather than vocabulary.  Apostrophes are allowed inside a part so
# "ne'er-do-well" survives; _normalize has already folded the typographic ones.
# The boundaries exclude digits as well as letters: without that, "19th-century"
# yields the fragment "th-century", which is the same class of artifact this
# module exists to remove.
HYPHENATED_RE = re.compile(
    r"(?<![A-Za-z0-9'-])"
    r"[A-Za-z]+(?:'[A-Za-z]+)?"
    r"(?:-[A-Za-z]+(?:'[A-Za-z]+)?)+"
    r"(?![A-Za-z0-9'-])"
)

# A hyphen immediately before a line break is a typesetter breaking a word
# across lines, not a compound.  Removing the newline would invent "compounds"
# out of every long word in the Gutenberg texts.
_LINE_BROKEN_RE = re.compile(r"-\n")

# Spelled-out compound numbers ("twenty-five", "forty-second") are a productive
# pattern, not vocabulary: the corpora attest dozens of them and importing each
# as its own lemma would be listing arithmetic.  The number words a learner
# needs are already lemmas in their own right.
_NUMBER_WORDS = frozenset(
    {
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "first",
        "second",
        "third",
        "fourth",
        "fifth",
        "sixth",
        "seventh",
        "eighth",
        "ninth",
        "tenth",
    }
)


def is_spelled_number(compound: str) -> bool:
    """Whether ``compound`` is a spelled-out number such as "twenty-five"."""
    parts = compound.split("-")
    return len(parts) == 2 and all(part in _NUMBER_WORDS for part in parts)


@dataclass
class HyphenatedStats:
    """How often each hyphenated compound appears, and where.

    Attributes:
        counts: Total occurrences of each lowercased compound.
        documents: How many distinct documents each compound appeared in.
            This is the spread measure that separates a real word from one
            author's tic -- ``min_documents`` filters on it.
        documents_scanned: How many documents contributed to these counts.
    """

    counts: Counter[str] = field(default_factory=Counter)
    documents: Counter[str] = field(default_factory=Counter)
    documents_scanned: int = 0

    def merge(self, other: "HyphenatedStats") -> None:
        """Fold another source's counts into this one."""
        self.counts.update(other.counts)
        self.documents.update(other.documents)
        self.documents_scanned += other.documents_scanned


def find_hyphenated(text: str) -> Counter[str]:
    """Count the hyphenated compounds in one document's text.

    The text is normalized exactly as the real tokenizer normalizes it, so the
    dashes that separate words are already gone and what matches here is a
    genuine hyphen join.

    Args:
        text: Raw document text.

    Returns:
        Lowercased compound -> occurrences in this document.
    """
    normalized = _normalize(text)
    # Drop end-of-line hyphenation before matching, so "inter-\nesting" does not
    # become the compound "inter-esting".
    normalized = _LINE_BROKEN_RE.sub("", normalized)
    return Counter(match.group(0).lower() for match in HYPHENATED_RE.finditer(normalized))


def scan_source(
    source: DocumentSource,
    *,
    name: str = "corpus",
    log_every: int = 100,
) -> HyphenatedStats:
    """Count hyphenated compounds across every document of one source.

    Args:
        source: Callable yielding ``(slug, raw_text)`` pairs.
        name: Corpus name, for progress logging.
        log_every: Log progress every this many documents.

    Returns:
        The pooled counts for this source.
    """
    stats = HyphenatedStats()
    for index, (slug, text) in enumerate(source(), start=1):
        found = find_hyphenated(text)
        stats.counts.update(found)
        # One increment per document per distinct compound, however often it
        # occurred there, so `documents` measures spread rather than volume.
        for compound in found:
            stats.documents[compound] += 1
        stats.documents_scanned += 1
        if log_every and index % log_every == 0:
            logger.info("[%s] %d documents, %d distinct compounds", name, index, len(stats.counts))
    logger.info(
        "[%s] done: %d documents, %d distinct compounds",
        name,
        stats.documents_scanned,
        len(stats.counts),
    )
    return stats


@dataclass(frozen=True)
class HyphenatedCandidate:
    """One compound, with the evidence for importing it."""

    text: str
    count: int
    documents: int
    corpora: Tuple[str, ...]

    @property
    def corpus_count(self) -> int:
        """How many distinct corpora attest this compound."""
        return len(self.corpora)


def rank_candidates(
    stats_by_corpus: Dict[str, HyphenatedStats],
    *,
    min_count: int = 5,
    min_documents: int = 3,
    min_corpora: int = 1,
    exclude: Optional[Iterable[str]] = None,
    drop_spelled_numbers: bool = True,
) -> List[HyphenatedCandidate]:
    """Pool per-corpus counts and rank what is worth importing.

    The thresholds are all about spread rather than volume.  A compound used
    forty times in one book is one author's habit; one used five times across
    five documents is vocabulary.  ``min_documents`` is therefore the filter
    that matters most, and ``min_corpora`` is the stricter version of it for
    when the corpora disagree about register.

    Args:
        stats_by_corpus: Corpus name -> its scan results.
        min_count: Minimum pooled occurrences.
        min_documents: Minimum pooled distinct documents.
        min_corpora: Minimum number of corpora attesting the compound.
        exclude: Compounds to drop regardless of counts -- typically the ones
            the database already holds.
        drop_spelled_numbers: Drop "twenty-five" and friends, which are a
            productive pattern rather than vocabulary.

    Returns:
        Candidates sorted by document spread, then raw count, then text, so the
        ordering is stable across runs.
    """
    excluded = {word.strip().lower() for word in (exclude or ()) if word.strip()}

    pooled_counts: Counter[str] = Counter()
    pooled_documents: Counter[str] = Counter()
    corpora_by_word: Dict[str, List[str]] = {}
    for corpus_name, stats in sorted(stats_by_corpus.items()):
        pooled_counts.update(stats.counts)
        pooled_documents.update(stats.documents)
        for word in stats.counts:
            corpora_by_word.setdefault(word, []).append(corpus_name)

    candidates: List[HyphenatedCandidate] = []
    for word, count in pooled_counts.items():
        if word in excluded:
            continue
        if drop_spelled_numbers and is_spelled_number(word):
            continue
        documents = pooled_documents[word]
        corpora = tuple(corpora_by_word.get(word, ()))
        if count < min_count or documents < min_documents or len(corpora) < min_corpora:
            continue
        candidates.append(
            HyphenatedCandidate(
                text=word,
                count=count,
                documents=documents,
                corpora=corpora,
            )
        )

    candidates.sort(key=lambda item: (-item.documents, -item.count, item.text))
    return candidates
