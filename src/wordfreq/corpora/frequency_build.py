"""Shared corpus frequency generation with observed spelling and document weighting.

Name detection is diagnostic: names stay in the vocabulary. Casing is resolved
from ordinary-prose evidence before ranking. Sentence/line starts contribute
ambiguous initial capitals; uppercase passages contribute counts but no spelling
evidence. Per-document rates and minimum coverage limit individual texts' influence.
"""

import json
import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import (
    Any,
    Collection,
    Dict,
    FrozenSet,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from wordfreq.corpora.casing import (
    KNOWN_DISTINCT_SPELLINGS,
    pooled_spelling_evidence,
    resolve_spellings,
)
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
        content_counts: All token counts, including diagnostic names.
    """

    slug: str
    stats: TextStats
    names: Dict[str, int] = field(default_factory=dict)
    content_counts: Counter[str] = field(default_factory=Counter)

    @property
    def content_tokens(self) -> int:
        """Number of tokens in the document, including diagnostic names."""
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
    canonical_phrases: Optional[Dict[str, str]] = None,
) -> BookAnalysis:
    """Strip Gutenberg boilerplate, tokenize and diagnose names without removing them.

    ``phrases`` (from ``gutenberg_text.build_phrase_index``) makes known
    multi-word forms count as one token, so "ice cream" is measured as itself
    rather than inflating "ice" and "cream".

    ``canonical_phrases`` (from ``build_canonical_phrase_index``) credits a
    matched variant spelling to its lemma, so "north-east" counts as
    "northeast" rather than as a word of its own.
    """
    body = strip_gutenberg_boilerplate(raw_text)
    stats = analyze_text(body, phrases, canonical_phrases)
    names = detect_names(
        stats,
        capitalization_ratio=capitalization_ratio,
        min_mid_sentence=min_mid_sentence,
        extra_never_names=extra_never_names,
    )
    # Name detection is diagnostic. Document weighting and coverage, rather
    # than capitalization, limit individual characters' influence on ranks.
    content_counts = stats.counts.copy()

    return BookAnalysis(
        slug=slug,
        stats=stats,
        names=names,
        content_counts=content_counts,
    )


def _book_weight(analysis: BookAnalysis, full_weight_tokens: int) -> float:
    """Weight for a book when averaging rates: 1.0 for anything novel-length."""
    if full_weight_tokens <= 0:
        return 1.0
    return min(1.0, analysis.content_tokens / full_weight_tokens)


def _score_counters(
    analyses: Sequence[BookAnalysis],
    counters: Sequence[Mapping[str, float]],
    *,
    weighting: Weighting,
    total_tokens: int,
    full_weight_tokens: int,
) -> Dict[str, float]:
    """Score one set of per-book counters, scaled to the whole corpus.

    ``counters`` runs parallel to ``analyses`` and says *which* count to
    aggregate -- the whole of a book's content, or its resolved spellings.
    Rates are always taken against the book's full
    ``content_tokens``, never against the counter's own sum, so the two case
    sides stay on one scale and add back up to the word's combined score.
    """
    if weighting == "pooled":
        pooled: Dict[str, float] = {}
        for counter in counters:
            for surface, count in counter.items():
                pooled[surface] = pooled.get(surface, 0.0) + count
        return pooled

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
    known_spellings: Collection[str] = (),
) -> Tuple[Dict[str, int], int]:
    """Rank observed spellings after allocating ambiguous casing.

    Rare unsupported capitals fold into the lowercase spelling, conserving
    their score. Known case-sensitive vocabulary can survive below the share
    threshold. Other spellings need reliable evidence across documents as well
    as sufficient count/share; uppercase formatting supplies no such evidence.
    """
    if not analyses:
        return {}, 0
    known_forms = KNOWN_DISTINCT_SPELLINGS | frozenset(known_spellings)
    evidence = pooled_spelling_evidence([analysis.stats for analysis in analyses])
    counters = [resolve_spellings(analysis.stats, evidence, known_forms) for analysis in analyses]
    total_tokens = sum(analysis.content_tokens for analysis in analyses)
    scores = _score_counters(
        analyses,
        counters,
        weighting=weighting,
        total_tokens=total_tokens,
        full_weight_tokens=full_weight_tokens,
    )
    book_count = Counter[str]()
    spelling_documents = Counter[str]()
    for analysis in analyses:
        book_count.update(analysis.content_counts.keys())
        spelling_documents.update(
            surface for forms in analysis.stats.spelling_counts.values() for surface in forms
        )
    effective_min_books = max(1, min(min_books, len(analyses)))
    total_scores: Dict[str, float] = {}
    for surface, score in scores.items():
        total_scores[surface.lower()] = total_scores.get(surface.lower(), 0.0) + score
    combined: Dict[str, float] = {}
    for surface, score in scores.items():
        word = surface.lower()
        if book_count[word] < effective_min_books:
            continue
        reliable_count = evidence.get(word, Counter())[surface]
        keep_case = surface in known_forms and (reliable_count > 0 or surface == "I")
        # Initial-capital words can teach their sentence-start spelling to
        # other documents. Unknown all-capital acronyms require ordinary-prose
        # evidence in multiple documents, so one shouted word cannot do that.
        required_spelling_documents = (
            effective_min_books if surface.isupper() and len(surface) > 1 else 1
        )
        keep_case = keep_case or (
            reliable_count > 0
            and score >= min_uppercase_count
            and score / total_scores[word] >= min_uppercase_share
            and spelling_documents[surface] >= required_spelling_documents
        )
        published = surface if surface == word or keep_case else word
        combined[published] = combined.get(published, 0.0) + score
    return _publish(combined, max_words), len(book_count)


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
    known_spellings: Collection[str] = (),
) -> Dict[str, Any]:
    """Assemble the corpus JSON payload from analyzed books.

    ``generator`` names the builder for the ``generation`` block. Every builder
    shares this casing/weighting path. ``known_spellings`` adds explicit known
    vocabulary to the built-in case-sensitive exceptions.

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
        known_spellings=known_spellings,
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
            "casing_version": 2,
            "known_case_spellings": sorted(KNOWN_DISTINCT_SPELLINGS | frozenset(known_spellings)),
            "name_detection": "diagnostic",
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
