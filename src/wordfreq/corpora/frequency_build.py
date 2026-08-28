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

**Capitalized and lowercase spellings are counted separately.**  A word whose
capitalized uses are frequent enough is published twice, as "march" and as
"March", so a lemma spelled with a capital has a token of its own to link to.
Sentence-initial occurrences carry no evidence and are apportioned between the
two by the ratio the mid-sentence ones show (see
:meth:`wordfreq.corpora.gutenberg_text.TextStats.case_split`).  This is what
the lowercased-whitelist approach could not do: crediting the month "May" with
every use of the modal verb is worse than leaving it out.

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
# A word's capitalized uses must reach this scaled count, and this share of its
# total, before the capitalized spelling is published as its own entry.
#
# The count is the noise filter: it stops a word sprouting a capitalized twin on
# a couple of stray occurrences.
#
# The share is *not* a confidence threshold, and must stay low.  A word whose
# capitalized sense is genuinely rarer than its lowercase one belongs low on the
# frequency list, not off it -- that is what a ranking is for.  "May" the month
# is 2.6% of that spelling's uses in the 19th-century books, and 2.6% of a
# common word is still hundreds of real occurrences.
#
# What the share does exclude is the residue of capitals that context forces
# rather than meaning: titles of works ("The Willing Mind", "The Dashing White
# Sergeant") and quotation openings, which the sentence-initial test cannot see
# because only the *first* word of a line is exempt.  Those land an order of
# magnitude lower than any real word -- "the" at 0.004 and "and" at 0.002,
# against "may" at 0.026 and "chapter" at 0.057 -- so 0.02 separates them
# cleanly.
DEFAULT_MIN_UPPERCASE_COUNT = 8
DEFAULT_MIN_UPPERCASE_SHARE = 0.02

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
        upper_counts: Of ``content_counts``, the share written capitalized.
        lower_counts: Of ``content_counts``, the share written lowercase.
    """

    slug: str
    stats: TextStats
    names: Dict[str, int] = field(default_factory=dict)
    content_counts: Counter[str] = field(default_factory=Counter)
    upper_counts: Counter[str] = field(default_factory=Counter)
    lower_counts: Counter[str] = field(default_factory=Counter)

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

    # Round to integers once, here, so every later stage works in whole counts.
    upper_counts = Counter[str]()
    lower_counts = Counter[str]()
    for word in content_counts:
        upper_total, lower_total = stats.case_split(word)
        upper = int(round(upper_total))
        if upper:
            upper_counts[word] = upper
        # Give the rounding remainder to the lowercase side, so the two always
        # add back up to content_counts[word].
        lower = content_counts[word] - upper
        if lower:
            lower_counts[word] = lower

    return BookAnalysis(
        slug=slug,
        stats=stats,
        names=names,
        content_counts=content_counts,
        upper_counts=upper_counts,
        lower_counts=lower_counts,
    )


def _book_weight(analysis: BookAnalysis, full_weight_tokens: int) -> float:
    """Weight for a book when averaging rates: 1.0 for anything novel-length."""
    if full_weight_tokens <= 0:
        return 1.0
    return min(1.0, analysis.content_tokens / full_weight_tokens)


def titlecase_token(word: str) -> str:
    """Capitalize each whitespace-separated word, leaving the rest alone.

    ``str.title`` treats an apostrophe as a word boundary, so "court's" comes
    back as "Court'S" and "int'l" as "Int'L" -- 71 such entries in a single
    build of the SCOTUS corpus, where possessives are everywhere.  Splitting on
    whitespace alone keeps the possessive intact and still titlecases each word
    of a multi-word token ("united states" -> "United States").

    "O'Connor" is therefore published as "O'connor".  That is the lesser
    error: the tokenizer records only that a token's first character was
    uppercase, so the interior capital was never recoverable here anyway.
    """
    return " ".join(part[:1].upper() + part[1:] for part in word.split(" "))


def _score_counters(
    analyses: Sequence[BookAnalysis],
    counters: Sequence[Counter[str]],
    *,
    weighting: Weighting,
    total_tokens: int,
    full_weight_tokens: int,
) -> Dict[str, float]:
    """Score one set of per-book counters, scaled to the whole corpus.

    ``counters`` runs parallel to ``analyses`` and says *which* count to
    aggregate -- the whole of a book's content, or just its uppercase or
    lowercase share.  Rates are always taken against the book's full
    ``content_tokens``, never against the counter's own sum, so the two case
    sides stay on one scale and add back up to the word's combined score.
    """
    if weighting == "pooled":
        pooled = Counter[str]()
        for counter in counters:
            pooled.update(counter)
        return {word: float(count) for word, count in pooled.items()}

    weights = [_book_weight(analysis, full_weight_tokens) for analysis in analyses]
    weight_total = sum(weights)
    if weight_total <= 0:
        return {}

    rate_sums: Dict[str, float] = {}
    for analysis, counter, weight in zip(analyses, counters, weights):
        book_tokens = analysis.content_tokens
        if book_tokens == 0 or weight == 0:
            continue
        for word, count in counter.items():
            rate_sums[word] = rate_sums.get(word, 0.0) + weight * (count / book_tokens)

    return {word: rate / weight_total * total_tokens for word, rate in rate_sums.items()}


def _publish(scores: Dict[str, float], max_words: Optional[int] = None) -> Dict[str, int]:
    """Round scores to published integers and order them, highest first.

    Rank on the published integer, not the float score behind it.  Two words
    whose scores differ only below the rounding threshold (2002.6 and 2003.4)
    both publish 2003, and ordering them by the float leaves the file looking
    unsorted and -- worse -- reshuffles those ties whenever an unrelated corpus
    change nudges the scores.  Rounding first makes the tie-break alphabetical
    and the file diff-stable.
    """
    rounded = {word: max(1, int(round(score))) for word, score in scores.items()}
    ordered = sorted(rounded.items(), key=lambda item: (-item[1], item[0]))
    if max_words is not None:
        ordered = ordered[:max_words]
    return dict(ordered)


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

    scores = _score_counters(
        analyses,
        [analysis.content_counts for analysis in analyses],
        weighting=weighting,
        total_tokens=total_tokens,
        full_weight_tokens=full_weight_tokens,
    )

    filtered = {
        word: score for word, score in scores.items() if book_count[word] >= effective_min_books
    }

    return _publish(filtered, max_words), total_unique_words


def aggregate_case_frequencies(
    analyses: Sequence[BookAnalysis],
    *,
    weighting: Weighting = "per-book-mean",
    min_books: int = DEFAULT_MIN_BOOKS,
    max_words: Optional[int] = None,
    full_weight_tokens: int = DEFAULT_FULL_WEIGHT_TOKENS,
    min_uppercase_count: int = DEFAULT_MIN_UPPERCASE_COUNT,
    min_uppercase_share: float = DEFAULT_MIN_UPPERCASE_SHARE,
) -> Tuple[Dict[str, int], int]:
    """Aggregate as :func:`aggregate_frequencies`, but split by capitalization.

    A word whose capitalized uses clear both thresholds is published twice: as
    its lowercase spelling, and as a titlecased entry carrying the uppercase
    share.  That is what separates the month "March" from the verb "march",
    which no lowercased count can do -- a whitelist keyed on the lowercased
    string would hand the month the verb's frequency.

    Both thresholds matter.  ``min_uppercase_share`` keeps an ordinary word
    that merely follows a full stop from sprouting a capitalized twin, and
    ``min_uppercase_count`` stops a rare word doing so on a couple of
    occurrences.  A word clearing neither is published exactly as before.

    Titlecasing is the only reconstruction available: the tokenizer records
    that a token's first character was uppercase, not what its true spelling
    was, so "DNA" and "iPhone" cannot be recovered here.

    Args:
        min_uppercase_count: Minimum scaled uppercase count to publish the
            capitalized entry.
        min_uppercase_share: Minimum share of the word's total that must be
            capitalized to publish the capitalized entry.

    Returns:
        ``(frequencies, total_unique_words)``, as
        :func:`aggregate_frequencies`, with capitalized entries merged in.
    """
    if not analyses:
        return {}, 0

    total_tokens = sum(analysis.content_tokens for analysis in analyses)
    book_count = Counter[str]()
    for analysis in analyses:
        book_count.update(analysis.content_counts.keys())
    total_unique_words = len(book_count)

    effective_min_books = max(1, min(min_books, len(analyses)))

    def score_side(counters: Sequence[Counter[str]]) -> Dict[str, float]:
        return _score_counters(
            analyses,
            counters,
            weighting=weighting,
            total_tokens=total_tokens,
            full_weight_tokens=full_weight_tokens,
        )

    upper_scores = score_side([analysis.upper_counts for analysis in analyses])
    lower_scores = score_side([analysis.lower_counts for analysis in analyses])

    # min_books is judged on the word as a whole, as it always was: it exists to
    # drop one book's invented vocabulary, and a word that spread across the
    # corpus has done so whichever way it is written.
    combined: Dict[str, float] = {}
    for word in book_count:
        if book_count[word] < effective_min_books:
            continue
        upper = upper_scores.get(word, 0.0)
        lower = lower_scores.get(word, 0.0)
        total = upper + lower
        if total <= 0:
            continue
        if upper >= min_uppercase_count and upper / total >= min_uppercase_share:
            combined[titlecase_token(word)] = upper
            if lower > 0:
                combined[word] = lower
        else:
            combined[word] = total

    return _publish(combined, max_words), total_unique_words


def build_corpus_payload(
    analyses: Sequence[BookAnalysis],
    *,
    corpus_name: str,
    weighting: Weighting = "per-book-mean",
    min_books: int = DEFAULT_MIN_BOOKS,
    max_words: Optional[int] = None,
    min_name_count: int = DEFAULT_MIN_NAME_COUNT,
    full_weight_tokens: int = DEFAULT_FULL_WEIGHT_TOKENS,
    min_uppercase_count: int = DEFAULT_MIN_UPPERCASE_COUNT,
    min_uppercase_share: float = DEFAULT_MIN_UPPERCASE_SHARE,
    generator: str = "wordfreq.corpora.build_gutenberg",
) -> Dict[str, Any]:
    """Assemble the corpus JSON payload from analyzed books.

    ``generator`` names the builder for the ``generation`` block; it defaults
    to the Gutenberg builder, which is what every corpus but ``legal_scotus``
    is made by.

    ``global_word_frequency`` carries capitalized and lowercase spellings as
    separate entries; see :func:`aggregate_case_frequencies`.
    """
    frequencies, total_unique_words = aggregate_case_frequencies(
        analyses,
        weighting=weighting,
        min_books=min_books,
        max_words=max_words,
        full_weight_tokens=full_weight_tokens,
        min_uppercase_count=min_uppercase_count,
        min_uppercase_share=min_uppercase_share,
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
            "min_uppercase_count": min_uppercase_count,
            "min_uppercase_share": min_uppercase_share,
            "total_tokens": sum(analysis.content_tokens for analysis in analyses),
            "books": len(analyses),
            "generator": generator,
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
