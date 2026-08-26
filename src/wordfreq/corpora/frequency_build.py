"""Build corpus word-frequency JSON from downloaded Gutenberg books.

The output matches the existing ``data/wordfreq/*.json`` corpus files:

.. code-block:: json

    {
      "global_word_frequency": {"the": 406936, ...},
      "name_frequency": {"<id>_<Title>": {"elizabeth": 88, ...}, ...},
      "books_processed": ["<id>_<Title>", ...],
      "total_unique_words": 27758,
      "total_names_identified": 37795
    }

Two decisions matter for how representative the result is.

**Proper nouns are removed per book.**  A word counts as a name in a given book
when its occurrences away from a sentence or line start are almost always
capitalized (see :mod:`wordfreq.corpora.gutenberg_text`).  This is decided book
by book, so "rose" can be a character in one novel and a flower in the next.
Removed words are reported in ``name_frequency`` rather than silently dropped.

**Words are ranked by their average rate across books, not by pooled counts.**
Pooling lets one long book dictate a word's rank - the reason "whale" sat at
rank ~150 in the old 19th-century corpus, on the strength of a single novel.
Averaging each book's rate divides such a word by the number of books, while a
word that is genuinely common everywhere keeps its rank.  ``min_books`` then
drops anything that never spread beyond a couple of books.
"""

import json
import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Collection, Dict, FrozenSet, List, Literal, Optional, Sequence, Tuple

from wordfreq.corpora.gutenberg_text import (
    TextStats,
    analyze_text,
    strip_gutenberg_boilerplate,
)

logger = logging.getLogger(__name__)

Weighting = Literal["per-book-mean", "pooled"]

# A word must be capitalized in at least this share of its mid-sentence
# occurrences to count as a proper noun.
DEFAULT_CAPITALIZATION_RATIO = 0.9
# ... over at least this many mid-sentence occurrences.  Below it there is no
# usable evidence and the word is left in the ordinary vocabulary.
DEFAULT_MIN_MID_SENTENCE = 4
# Names below this count are detected but not written to ``name_frequency``.
DEFAULT_MIN_NAME_COUNT = 8
# A word must appear in at least this many books to enter the global list.
DEFAULT_MIN_BOOKS = 3
# Books shorter than this contribute proportionally less than a full book, so a
# short text cannot swing an averaged rate the way a novel-length one does.
DEFAULT_FULL_WEIGHT_TOKENS = 20000

# Always-capitalized English words that are not proper nouns.  Without this the
# capitalization test eats the first-person pronoun, which is how "I" went
# missing from the previous 19th-century corpus.
NEVER_NAMES = frozenset(
    {
        "i",
        "i'd",
        "i'll",
        "i'm",
        "i've",
        "o",
        "o'er",
    }
)


@dataclass
class BookAnalysis:
    """One analyzed book: its token stats and the names found in it.

    Attributes:
        slug: ``<id>_<Title>`` key used in the corpus JSON.
        stats: Token counts and capitalization evidence.
        names: Every detected proper noun mapped to its count in this book.
        content_counts: Token counts with the detected names removed.
    """

    slug: str
    stats: TextStats
    names: Dict[str, int] = field(default_factory=dict)
    content_counts: Counter[str] = field(default_factory=Counter)

    @property
    def content_tokens(self) -> int:
        """Number of non-name tokens in the book."""
        return sum(self.content_counts.values())


def resolve_never_names(extra_never_names: Collection[str] = ()) -> FrozenSet[str]:
    """Combine the built-in never-names with a corpus's own allowlist."""
    return NEVER_NAMES | frozenset(word.lower() for word in extra_never_names)


def detect_names(
    stats: TextStats,
    *,
    capitalization_ratio: float = DEFAULT_CAPITALIZATION_RATIO,
    min_mid_sentence: int = DEFAULT_MIN_MID_SENTENCE,
    extra_never_names: Collection[str] = (),
) -> Dict[str, int]:
    """Return ``{word: count}`` for the proper nouns in one book.

    A word qualifies when it appears mid-sentence often enough to judge and is
    capitalized in at least ``capitalization_ratio`` of those occurrences.
    Words that only ever appear at a sentence or line start carry no evidence
    and are never treated as names.

    Args:
        stats: Token statistics for the book.
        capitalization_ratio: Required share of capitalized mid-sentence uses.
        min_mid_sentence: Minimum mid-sentence occurrences needed to decide.
        extra_never_names: Words this corpus wants kept as vocabulary even
            though they are always capitalized (see
            ``BookList.always_vocabulary``).

    Returns:
        Mapping of name to its total count in the book.
    """
    never_names = resolve_never_names(extra_never_names)
    names: Dict[str, int] = {}
    for word, count in stats.counts.items():
        if word in never_names:
            continue
        if stats.mid_sentence_total[word] < min_mid_sentence:
            continue
        ratio = stats.capitalization_ratio(word)
        if ratio is not None and ratio >= capitalization_ratio:
            names[word] = count
    return names


def analyze_book(
    slug: str,
    raw_text: str,
    *,
    capitalization_ratio: float = DEFAULT_CAPITALIZATION_RATIO,
    min_mid_sentence: int = DEFAULT_MIN_MID_SENTENCE,
    extra_never_names: Collection[str] = (),
    phrases: Optional[Dict[str, int]] = None,
) -> BookAnalysis:
    """Strip Gutenberg boilerplate, tokenize and split names from vocabulary.

    ``phrases`` (from ``gutenberg_text.build_phrase_index``) makes known
    multi-word forms count as one token, so "ice cream" is measured as itself
    rather than inflating "ice" and "cream".
    """
    body = strip_gutenberg_boilerplate(raw_text)
    stats = analyze_text(body, phrases)
    names = detect_names(
        stats,
        capitalization_ratio=capitalization_ratio,
        min_mid_sentence=min_mid_sentence,
        extra_never_names=extra_never_names,
    )
    content_counts = Counter(
        {word: count for word, count in stats.counts.items() if word not in names}
    )
    return BookAnalysis(slug=slug, stats=stats, names=names, content_counts=content_counts)


def _book_weight(analysis: BookAnalysis, full_weight_tokens: int) -> float:
    """Weight for a book when averaging rates: 1.0 for anything novel-length."""
    if full_weight_tokens <= 0:
        return 1.0
    return min(1.0, analysis.content_tokens / full_weight_tokens)


def aggregate_frequencies(
    analyses: Sequence[BookAnalysis],
    *,
    weighting: Weighting = "per-book-mean",
    min_books: int = DEFAULT_MIN_BOOKS,
    max_words: Optional[int] = None,
    full_weight_tokens: int = DEFAULT_FULL_WEIGHT_TOKENS,
) -> Tuple[Dict[str, int], int]:
    """Combine per-book counts into one frequency table.

    Args:
        analyses: Analyzed books, names already separated out.
        weighting: ``"per-book-mean"`` averages each word's rate across books
            (each book weighted by length up to ``full_weight_tokens``);
            ``"pooled"`` simply sums raw counts, as the older corpora did.
        min_books: Minimum number of books a word must appear in.  Clamped to
            the number of books available.
        max_words: Keep only this many words (highest frequency first).
        full_weight_tokens: Book length at which a book gets full weight.

    Returns:
        ``(frequencies, total_unique_words)`` where ``frequencies`` maps word to
        an integer count scaled to the size of the whole corpus, and
        ``total_unique_words`` counts every distinct non-name word seen.
    """
    if not analyses:
        return {}, 0

    total_tokens = sum(analysis.content_tokens for analysis in analyses)
    book_count = Counter[str]()
    for analysis in analyses:
        book_count.update(analysis.content_counts.keys())
    total_unique_words = len(book_count)

    effective_min_books = max(1, min(min_books, len(analyses)))

    scores: Dict[str, float] = {}
    if weighting == "pooled":
        pooled = Counter[str]()
        for analysis in analyses:
            pooled.update(analysis.content_counts)
        scores = {word: float(count) for word, count in pooled.items()}
    else:
        weights = [_book_weight(analysis, full_weight_tokens) for analysis in analyses]
        weight_total = sum(weights)
        if weight_total <= 0:
            return {}, total_unique_words
        rate_sums: Dict[str, float] = {}
        for analysis, weight in zip(analyses, weights):
            book_tokens = analysis.content_tokens
            if book_tokens == 0 or weight == 0:
                continue
            for word, count in analysis.content_counts.items():
                rate_sums[word] = rate_sums.get(word, 0.0) + weight * (count / book_tokens)
        scores = {word: rate / weight_total * total_tokens for word, rate in rate_sums.items()}

    filtered = {
        word: score for word, score in scores.items() if book_count[word] >= effective_min_books
    }

    ordered = sorted(filtered.items(), key=lambda item: (-item[1], item[0]))
    if max_words is not None:
        ordered = ordered[:max_words]

    frequencies = {word: max(1, int(round(score))) for word, score in ordered}
    return frequencies, total_unique_words


def build_corpus_payload(
    analyses: Sequence[BookAnalysis],
    *,
    corpus_name: str,
    weighting: Weighting = "per-book-mean",
    min_books: int = DEFAULT_MIN_BOOKS,
    max_words: Optional[int] = None,
    min_name_count: int = DEFAULT_MIN_NAME_COUNT,
    full_weight_tokens: int = DEFAULT_FULL_WEIGHT_TOKENS,
) -> Dict[str, Any]:
    """Assemble the corpus JSON payload from analyzed books."""
    frequencies, total_unique_words = aggregate_frequencies(
        analyses,
        weighting=weighting,
        min_books=min_books,
        max_words=max_words,
        full_weight_tokens=full_weight_tokens,
    )

    name_frequency: Dict[str, Dict[str, int]] = {}
    total_names_identified = 0
    for analysis in analyses:
        total_names_identified += len(analysis.names)
        reported = {
            word: count for word, count in analysis.names.items() if count >= min_name_count
        }
        name_frequency[analysis.slug] = dict(
            sorted(reported.items(), key=lambda item: (-item[1], item[0]))
        )

    return {
        "global_word_frequency": frequencies,
        "name_frequency": name_frequency,
        "books_processed": [analysis.slug for analysis in analyses],
        "total_unique_words": total_unique_words,
        "total_names_identified": total_names_identified,
        "generation": {
            "corpus": corpus_name,
            "weighting": weighting,
            "min_books": min_books,
            "max_words": max_words,
            "min_name_count": min_name_count,
            "full_weight_tokens": full_weight_tokens,
            "total_tokens": sum(analysis.content_tokens for analysis in analyses),
            "books": len(analyses),
            "generator": "wordfreq.corpora.build_wordfreq",
        },
    }


def write_corpus_json(payload: Dict[str, Any], output_path: str) -> None:
    """Write ``payload`` to ``output_path`` in the corpus file format."""
    directory = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(directory, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    logger.info(
        "Wrote %s (%d words, %d books)",
        output_path,
        len(payload["global_word_frequency"]),
        len(payload["books_processed"]),
    )


def book_report_rows(analyses: Sequence[BookAnalysis]) -> List[Dict[str, Any]]:
    """Per-book numbers for the CLI report."""
    rows: List[Dict[str, Any]] = []
    for analysis in analyses:
        rows.append(
            {
                "book": analysis.slug,
                "tokens": analysis.stats.token_total,
                "content_tokens": analysis.content_tokens,
                "unique_words": len(analysis.content_counts),
                "names": len(analysis.names),
                "weight": round(_book_weight(analysis, DEFAULT_FULL_WEIGHT_TOKENS), 3),
            }
        )
    return rows
