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

**Case is evidence, and is kept.**  The compounds are lowercased for counting,
but each occurrence is also recorded as capitalized, lowercase or *uncertain*
exactly as :func:`wordfreq.corpora.gutenberg_text.analyze_text` records a single
word: a capital at the start of a sentence or a line was forced by position and
decides nothing.  Without this the first report could not tell "jean-luc" from
"well-known", and a handful of names reached the curated list.

**The unhyphenated spellings are counted too.**  A hyphenated form is often not
a word but a spelling: the corpora write "north-east", "north east" and
"northeast" for the same thing, and what belongs in the database is the solid
lemma with the other two as variants of it.  Each document is therefore also
scanned for the solid and spaced spellings of whatever compounds it attested,
and ``preferred_spelling`` reports which one the corpora actually favour.

**What is a word, and what is a pattern.**  Several of the shapes a hyphen
produces are productive rather than lexical, and mixing them into one ranked
list buries the vocabulary in arithmetic.  :func:`classify` separates them, and
the report prints each as its own section (``CATEGORY_ORDER``):

* ``fraction`` -- "two-thirds", "one-half".  Vocabulary, and wanted at a much
  earlier level than the rest, so it leads the report and is decided on its own.
* ``measure`` -- "five-year", "two-week".  A number modifying a unit for one
  attributive use ("a five-year plan"); the words are "five" and "year".
* ``number`` -- "twenty-five".  Arithmetic.
* ``phrase`` -- "black-and-white", "day-to-day".  Three or more parts, so a
  phrase written with hyphens rather than a compound.
* ``attributive`` -- "long-tailed", "horse-drawn".  A participle that describes
  a head noun and means little without it.  Reported apart rather than dropped:
  some ("well-known", "so-called") are worth holding.
* ``prefixed`` -- "non-fiction", "re-established".  Worth holding when the whole
  means something its parts do not; "non-Jewish" is merely the negation of its
  base, and the capital on that base is how the corpus says so.
* ``proper`` -- capitalized in the great majority of its decided occurrences:
  "Jean-Luc", "Anglo-Saxon", "Wiley-Blackwell".  Names.
* ``solid-variant`` -- the corpora mostly write it solid, so it is a variant of
  that word.
* ``general`` -- what is left: the ordinary hyphenated vocabulary.

Corpus differences are handled by
:class:`~wordfreq.corpora.hyphenated.DocumentSource`, which is just an iterator
of ``(slug, raw_text)`` pairs -- the same shape the three builders already feed
to ``frequency_build.analyze_book``.  The counting below is written once and
runs over any of them.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, OrderedDict
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Tuple

from wordfreq.corpora.gutenberg_text import _is_sentence_initial, _normalize

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

# Plain words, for finding the unhyphenated spellings of a compound: "northeast"
# and "north east" alongside "north-east".  The hyphen is a word boundary here,
# so the parts of a compound are not themselves read as a spaced spelling of it.
_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

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


# The denominators of a spelled-out fraction.  "two-thirds" and "one-half" are
# vocabulary a learner needs -- and needs long before level 56 -- but they are
# not the same kind of thing as "well-known", so they are reported as their own
# category rather than mixed into the general list.
_FRACTION_WORDS = frozenset(
    {
        "half",
        "halves",
        "third",
        "thirds",
        "quarter",
        "quarters",
        "fourth",
        "fourths",
        "fifth",
        "fifths",
        "sixth",
        "sixths",
        "seventh",
        "sevenths",
        "eighth",
        "eighths",
        "ninth",
        "ninths",
        "tenth",
        "tenths",
        "hundredth",
        "hundredths",
        "thousandth",
        "thousandths",
    }
)

# The nouns a bare number modifies attributively: "a five-year plan", "a
# two-week delay".  The compound is the two ordinary words it is made of --
# nothing is learned by holding "five-year" that is not already in "five" and
# "year" -- and the pattern is productive over every number and every one of
# these units, so listing the attested combinations is listing arithmetic.
_MEASURE_WORDS = frozenset(
    {
        "second",
        "seconds",
        "minute",
        "minutes",
        "hour",
        "hours",
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
        "year",
        "years",
        "decade",
        "decades",
        "century",
        "centuries",
        "inch",
        "inches",
        "foot",
        "feet",
        "yard",
        "yards",
        "mile",
        "miles",
        "metre",
        "metres",
        "meter",
        "meters",
        "kilometre",
        "kilometres",
        "kilometer",
        "kilometers",
        "pound",
        "pounds",
        "ton",
        "tons",
        "man",
        "men",
        "member",
        "members",
        "story",
        "storey",
        "part",
        "parts",
        "piece",
        "pieces",
        "page",
        "pages",
        "volume",
        "volumes",
        "act",
        "acts",
        "game",
        "games",
        "point",
        "points",
        "time",
        "times",
        "fold",
        "digit",
        "letter",
        "letters",
        "word",
        "words",
        "syllable",
        "syllables",
        "storied",
    }
)

# ... but not these.  "three-dimensional" and "one-sided" have the shape of a
# number modifying a unit and are nothing of the kind: they are lexicalized,
# and "three-dimensional" was on the first curated list on its own merits.
# Keeping them out of _MEASURE_WORDS is the whole distinction between "a
# five-year plan" (two words) and "a three-dimensional object" (one).

# Prefixes that attach productively to almost any base.  A compound in one of
# these is worth holding only when the whole has a meaning its parts do not
# ("non-fiction", "non-profit"); "non-Muslim" and "non-Jewish" are just the
# negation of the base and belong to whatever the base belongs to.  The
# capitalized base is the tell the corpus can see, which is why this pairs with
# the case evidence rather than standing alone.
_PRODUCTIVE_PREFIXES = frozenset({"non", "un", "re", "pre", "post", "anti", "semi", "sub", "co"})

# A hyphenated participle or adjective that describes a head noun and hardly
# stands alone: "long-tailed", "horse-drawn", "well-known".  These are real
# English and some are worth holding, but they are attributive modifiers rather
# than words with an independent sense, and the curator wants them separated.
# "-ed" and "-ing" catch the regular cases; "-wn", "-lt" and "-nt" catch the
# irregular participles common enough to matter here ("horse-drawn",
# "home-grown", "well-built", "hard-spent").  Deliberately not exhaustive: a
# missed irregular lands in the general list, where the curator sees it, which
# is a better failure than a false positive hiding a real word.
_ATTRIBUTIVE_SUFFIX_RE = re.compile(r"(?:ed|ing|wn|lt|nt)$")

# A compound capitalized in at least this share of its *decided* (mid-sentence)
# occurrences is a name: "Jean-Luc", "Anglo-Saxon", "Wiley-Blackwell".  Lower
# than the 0.9 the proper-noun detector uses on single words, because a
# hyphenated name is nearly always written with the capital and the few
# lowercase occurrences are usually a different word entirely.
DEFAULT_PROPER_SHARE = 0.8
# ... over at least this many decided occurrences.  Below it there is no usable
# evidence and the compound is judged on its shape instead.
DEFAULT_MIN_CASE_EVIDENCE = 4
# The solid spelling must reach this share of the hyphenated count before the
# hyphenated form is called a variant of it rather than a word of its own.
DEFAULT_SOLID_RATIO = 0.25

#: Categories a compound can fall into.  ``general`` is the ordinary
#: hyphenated-vocabulary list; everything else is reported apart from it so the
#: curator sees the productive patterns as patterns rather than as words.
CATEGORY_GENERAL = "general"
CATEGORY_FRACTION = "fraction"
CATEGORY_NUMBER = "number"
CATEGORY_MEASURE = "measure"
CATEGORY_PHRASE = "phrase"
CATEGORY_ATTRIBUTIVE = "attributive"
CATEGORY_PREFIXED = "prefixed"
CATEGORY_PROPER = "proper"
CATEGORY_SOLID_VARIANT = "solid-variant"

#: The order the report prints its sections in.  Fractions first because they
#: are wanted at a much earlier level than the rest and want deciding on their
#: own.
CATEGORY_ORDER = (
    CATEGORY_FRACTION,
    CATEGORY_GENERAL,
    CATEGORY_SOLID_VARIANT,
    CATEGORY_PREFIXED,
    CATEGORY_ATTRIBUTIVE,
    CATEGORY_PHRASE,
    CATEGORY_MEASURE,
    CATEGORY_NUMBER,
    CATEGORY_PROPER,
)


def is_spelled_number(compound: str) -> bool:
    """Whether ``compound`` is a spelled-out number such as "twenty-five"."""
    parts = compound.split("-")
    return len(parts) == 2 and all(part in _NUMBER_WORDS for part in parts)


def is_fraction(compound: str) -> bool:
    """Whether ``compound`` is a spelled-out fraction such as "two-thirds"."""
    parts = compound.split("-")
    return len(parts) == 2 and parts[0] in _NUMBER_WORDS and parts[1] in _FRACTION_WORDS


def is_measure_phrase(compound: str) -> bool:
    """Whether ``compound`` is a number modifying a unit: "five-year", "two-week".

    These are two ordinary words that a hyphen joined for one attributive use
    ("a five-year plan"), not vocabulary of their own.
    """
    parts = compound.split("-")
    return len(parts) == 2 and parts[0] in _NUMBER_WORDS and parts[1] in _MEASURE_WORDS


def is_attributive_modifier(compound: str) -> bool:
    """Whether ``compound`` ends in a participle, as "long-tailed" does.

    A hyphenated participle describes a head noun and rarely means anything on
    its own -- "long-tailed" needs the deer.  Reported separately rather than
    dropped, because some of them ("well-known", "so-called") are worth having.
    """
    parts = compound.split("-")
    return len(parts) == 2 and bool(_ATTRIBUTIVE_SUFFIX_RE.search(parts[-1]))


def productive_prefix(compound: str) -> Optional[str]:
    """The productive prefix ``compound`` is built on, if any."""
    prefix = compound.split("-", 1)[0]
    return prefix if prefix in _PRODUCTIVE_PREFIXES else None


@dataclass
class HyphenatedStats:
    """How often each hyphenated compound appears, where, and in what case.

    The case counters mirror :class:`wordfreq.corpora.gutenberg_text.TextStats`
    exactly, and for the same reason: a capital at the start of a sentence is
    forced by position and is evidence of nothing.  Only the mid-sentence
    occurrences decide, and the sentence-initial ones are held separately as
    ``uncertain`` so a compound attested only in headings does not read as a
    proper noun.  Without this the report cannot tell "jean-luc" from
    "well-known" -- both are lowercased before counting.

    Attributes:
        counts: Total occurrences of each lowercased compound.
        documents: How many distinct documents each compound appeared in.
            This is the spread measure that separates a real word from one
            author's tic -- ``min_documents`` filters on it.
        upper_counts: Mid-sentence occurrences written with a leading capital.
        lower_counts: Mid-sentence occurrences written lowercase.
        uncertain_counts: Sentence- or line-initial occurrences, whose case
            carries no evidence either way.
        inner_upper_counts: Occurrences capitalized on a part after the first
            ("non-Jewish").  Position can never force such a capital, so this
            is decisive evidence however few occurrences there are.
        solid_counts: Occurrences of the same compound written solid
            ("northeast" for "north-east"), collected so a hyphenated form can
            be recognized as a spelling variant of a word rather than a new one.
        spaced_counts: Occurrences written as separate words ("north east").
        documents_scanned: How many documents contributed to these counts.
    """

    counts: Counter[str] = field(default_factory=Counter)
    documents: Counter[str] = field(default_factory=Counter)
    upper_counts: Counter[str] = field(default_factory=Counter)
    lower_counts: Counter[str] = field(default_factory=Counter)
    uncertain_counts: Counter[str] = field(default_factory=Counter)
    inner_upper_counts: Counter[str] = field(default_factory=Counter)
    solid_counts: Counter[str] = field(default_factory=Counter)
    spaced_counts: Counter[str] = field(default_factory=Counter)
    documents_scanned: int = 0

    def merge(self, other: "HyphenatedStats") -> None:
        """Fold another source's counts into this one."""
        self.counts.update(other.counts)
        self.documents.update(other.documents)
        self.upper_counts.update(other.upper_counts)
        self.lower_counts.update(other.lower_counts)
        self.uncertain_counts.update(other.uncertain_counts)
        self.inner_upper_counts.update(other.inner_upper_counts)
        self.solid_counts.update(other.solid_counts)
        self.spaced_counts.update(other.spaced_counts)
        self.documents_scanned += other.documents_scanned

    def capitalized_share(self, compound: str) -> Optional[float]:
        """Share of *decided* occurrences written with a leading capital.

        Returns ``None`` when every occurrence was sentence-initial, which is
        the same "no usable evidence" answer
        :meth:`TextStats.capitalization_ratio` gives.
        """
        decided = self.upper_counts[compound] + self.lower_counts[compound]
        if decided == 0:
            return None
        return self.upper_counts[compound] / decided


@dataclass(frozen=True)
class HyphenatedOccurrences:
    """One document's hyphenated compounds, with their case evidence.

    ``solid`` and ``spaced`` cover the same compounds written without the
    hyphen, which is what makes "north-east" recognizable as a spelling of
    "northeast" rather than a word in its own right.
    """

    counts: Counter[str] = field(default_factory=Counter)
    upper: Counter[str] = field(default_factory=Counter)
    lower: Counter[str] = field(default_factory=Counter)
    uncertain: Counter[str] = field(default_factory=Counter)
    inner_upper: Counter[str] = field(default_factory=Counter)
    solid: Counter[str] = field(default_factory=Counter)
    spaced: Counter[str] = field(default_factory=Counter)


def find_hyphenated(text: str) -> Counter[str]:
    """Count the hyphenated compounds in one document's text.

    Kept as the simple entry point for callers that want counts alone; the
    scan uses :func:`find_hyphenated_occurrences`, which also carries the case
    and unhyphenated-spelling evidence.

    Args:
        text: Raw document text.

    Returns:
        Lowercased compound -> occurrences in this document.
    """
    return find_hyphenated_occurrences(text).counts


def find_hyphenated_occurrences(text: str) -> HyphenatedOccurrences:
    """Find one document's hyphenated compounds with their case evidence.

    The text is normalized exactly as the real tokenizer normalizes it, so the
    dashes that separate words are already gone and what matches here is a
    genuine hyphen join.  Each occurrence is then classified by position and
    case the way :func:`wordfreq.corpora.gutenberg_text.analyze_text` does it:
    a compound opening a sentence or a line is *uncertain* rather than
    capitalized, because the position forced the capital.

    The unhyphenated spellings of whatever was found are counted in the same
    pass -- solid ("northeast") and spaced ("north east") -- so the report can
    say whether a hyphenated form is a variant of a word the corpora already
    write another way.

    Args:
        text: Raw document text.

    Returns:
        This document's counts and case evidence.
    """
    normalized = _normalize(text)
    # Drop end-of-line hyphenation before matching, so "inter-\nesting" does not
    # become the compound "inter-esting".
    normalized = _LINE_BROKEN_RE.sub("", normalized)

    found = HyphenatedOccurrences()
    for match in HYPHENATED_RE.finditer(normalized):
        raw = match.group(0)
        compound = raw.lower()
        found.counts[compound] += 1
        if any(part[:1].isupper() for part in raw.split("-")[1:]):
            # A capital on a part that no sentence start could have forced.
            # This is the whole tell for "non-Jewish" against "non-fiction":
            # the prefix is lowercase in both, and only the base differs.
            found.inner_upper[compound] += 1
        if _is_sentence_initial(normalized, match.start()):
            found.uncertain[compound] += 1
        elif raw[0].isupper():
            found.upper[compound] += 1
        else:
            found.lower[compound] += 1

    if found.counts:
        # Blank out the hyphenated matches first: their own parts would
        # otherwise read as the spaced spelling, and "north-east" would be
        # counted as evidence for "north east".
        masked = HYPHENATED_RE.sub(lambda match: " " * len(match.group(0)), normalized)
        _count_unhyphenated(masked, found)
    return found


def _count_unhyphenated(masked: str, found: HyphenatedOccurrences) -> None:
    """Count the solid and spaced spellings of the compounds already found.

    ``masked`` is the normalized text with the hyphenated forms themselves
    blanked out, so only the genuinely unhyphenated spellings are counted.

    Only the compounds this document attests are looked for, so the cost is one
    pass over the text per document rather than a scan for every compound in
    the corpus.  Two-part compounds only: "black-and-white" written out is a
    phrase, and counting it as a spelling of the compound would say the wrong
    thing about what the compound is.
    """
    solid_wanted: Dict[str, str] = {}
    spaced_wanted: Dict[str, str] = {}
    for compound in found.counts:
        parts = compound.split("-")
        if len(parts) != 2:
            continue
        solid_wanted["".join(parts)] = compound
        spaced_wanted[" ".join(parts)] = compound

    words = [match.group(0).lower() for match in _WORD_RE.finditer(masked)]
    for index, word in enumerate(words):
        solid_match = solid_wanted.get(word)
        if solid_match:
            found.solid[solid_match] += 1
        if index + 1 < len(words):
            spaced_match = spaced_wanted.get(f"{word} {words[index + 1]}")
            if spaced_match:
                found.spaced[spaced_match] += 1


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
        found = find_hyphenated_occurrences(text)
        stats.counts.update(found.counts)
        stats.upper_counts.update(found.upper)
        stats.lower_counts.update(found.lower)
        stats.uncertain_counts.update(found.uncertain)
        stats.inner_upper_counts.update(found.inner_upper)
        stats.solid_counts.update(found.solid)
        stats.spaced_counts.update(found.spaced)
        # One increment per document per distinct compound, however often it
        # occurred there, so `documents` measures spread rather than volume.
        for compound in found.counts:
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
    """One compound, with the evidence for importing it.

    Attributes:
        text: The lowercased compound.
        count: Pooled occurrences across every corpus.
        documents: Pooled distinct documents.
        corpora: The corpora that attest it.
        category: Which report section it belongs to; see ``CATEGORY_ORDER``.
        upper: Mid-sentence occurrences written with a leading capital.
        lower: Mid-sentence occurrences written lowercase.
        uncertain: Sentence-initial occurrences, whose case decides nothing.
        inner_upper: Occurrences with a capital on a part after the first --
            the "non-Jewish" tell, which no sentence position can force.
        solid: Occurrences of the solid spelling ("northeast").
        spaced: Occurrences of the spaced spelling ("north east").
    """

    text: str
    count: int
    documents: int
    corpora: Tuple[str, ...]
    category: str = CATEGORY_GENERAL
    upper: int = 0
    lower: int = 0
    uncertain: int = 0
    inner_upper: int = 0
    solid: int = 0
    spaced: int = 0

    @property
    def corpus_count(self) -> int:
        """How many distinct corpora attest this compound."""
        return len(self.corpora)

    @property
    def capitalized_share(self) -> Optional[float]:
        """Share of decided occurrences written capitalized, or ``None``.

        ``None`` means every occurrence opened a sentence or a line, so the
        capitals were forced by position and say nothing.
        """
        decided = self.upper + self.lower
        if decided == 0:
            return None
        return self.upper / decided

    @property
    def preferred_spelling(self) -> str:
        """Which spelling the corpora favour: hyphenated, solid or spaced.

        A compound the corpora usually write solid is a spelling variant of
        that word rather than a lemma of its own -- "north-east" is how some
        writers spell "northeast" -- and belongs in ``variant_forms`` against
        it.  The counts here are what decides that.
        """
        options = ((self.count, "hyphenated"), (self.solid, "solid"), (self.spaced, "spaced"))
        return max(options, key=lambda option: option[0])[1]


def classify(
    candidate: HyphenatedCandidate,
    *,
    proper_share: float = DEFAULT_PROPER_SHARE,
    min_case_evidence: int = DEFAULT_MIN_CASE_EVIDENCE,
    solid_ratio: float = DEFAULT_SOLID_RATIO,
) -> str:
    """Which report section a compound belongs in.

    The order matters.  A capitalized compound is a name whatever else it looks
    like ("Jean-Luc", "Anglo-Saxon"), so that test comes first.  It is really
    two tests.  A capital on a part *after* the first cannot be forced by
    sentence position, so it counts on its own -- that is what separates
    "non-Jewish" from "non-fiction", where the prefix is lowercase in both.  A
    capital on the first part is only evidence away from a sentence or line
    start, so that half uses the mid-sentence occurrences and needs
    ``min_case_evidence`` of them; a compound seen only in headings is not
    condemned on the strength of the heading's capital.  Then the arithmetic
    patterns, then the spelling-variant test, then the shapes that are phrases
    rather than words.

    ``proper_share`` serves both tests: the share of decided occurrences
    capitalized on the first part, and the share of *all* occurrences carrying
    an inner capital.

    Args:
        candidate: The compound and its pooled evidence.
        proper_share: Capitalized share above which a compound reads as a name.
        min_case_evidence: Decided occurrences needed before the share is
            trusted at all.
        solid_ratio: How much of the hyphenated count the solid spelling must
            reach before the compound is called a variant of the solid word.

    Returns:
        One of the ``CATEGORY_*`` constants.
    """
    # A capital on a part after the first is unforceable by position, so it
    # needs no minimum: "non-Jewish" and "Anglo-Saxon" declare themselves on
    # the strength of the evidence alone.
    if candidate.inner_upper >= max(1, candidate.count * proper_share):
        return CATEGORY_PROPER

    share = candidate.capitalized_share
    if share is not None and candidate.upper + candidate.lower >= min_case_evidence:
        if share >= proper_share:
            return CATEGORY_PROPER

    if is_fraction(candidate.text):
        return CATEGORY_FRACTION
    if is_spelled_number(candidate.text):
        return CATEGORY_NUMBER
    if is_measure_phrase(candidate.text):
        return CATEGORY_MEASURE

    if candidate.solid >= max(1, candidate.count * solid_ratio):
        return CATEGORY_SOLID_VARIANT

    if candidate.text.count("-") > 1:
        return CATEGORY_PHRASE
    if productive_prefix(candidate.text):
        return CATEGORY_PREFIXED
    if is_attributive_modifier(candidate.text):
        return CATEGORY_ATTRIBUTIVE
    return CATEGORY_GENERAL


def rank_candidates(
    stats_by_corpus: Dict[str, HyphenatedStats],
    *,
    min_count: int = 5,
    min_documents: int = 3,
    min_corpora: int = 1,
    exclude: Optional[Iterable[str]] = None,
    drop_spelled_numbers: bool = True,
    proper_share: float = DEFAULT_PROPER_SHARE,
    min_case_evidence: int = DEFAULT_MIN_CASE_EVIDENCE,
    solid_ratio: float = DEFAULT_SOLID_RATIO,
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
        drop_spelled_numbers: Drop "twenty-five" and friends entirely rather
            than reporting them under ``CATEGORY_NUMBER``.
        proper_share: Capitalized share above which a compound is a name.
        min_case_evidence: Decided occurrences needed to trust that share.
        solid_ratio: Solid-spelling share above which the hyphenated form is a
            variant rather than a word.

    Returns:
        Candidates sorted by document spread, then raw count, then text, so the
        ordering is stable across runs.  Each carries a ``category``; grouping
        by it is the caller's job (:func:`group_by_category`).
    """
    excluded = {word.strip().lower() for word in (exclude or ()) if word.strip()}

    pooled_counts: Counter[str] = Counter()
    pooled_documents: Counter[str] = Counter()
    pooled_upper: Counter[str] = Counter()
    pooled_lower: Counter[str] = Counter()
    pooled_uncertain: Counter[str] = Counter()
    pooled_inner_upper: Counter[str] = Counter()
    pooled_solid: Counter[str] = Counter()
    pooled_spaced: Counter[str] = Counter()
    corpora_by_word: Dict[str, List[str]] = {}
    for corpus_name, stats in sorted(stats_by_corpus.items()):
        pooled_counts.update(stats.counts)
        pooled_documents.update(stats.documents)
        pooled_upper.update(stats.upper_counts)
        pooled_lower.update(stats.lower_counts)
        pooled_uncertain.update(stats.uncertain_counts)
        pooled_inner_upper.update(stats.inner_upper_counts)
        pooled_solid.update(stats.solid_counts)
        pooled_spaced.update(stats.spaced_counts)
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
        candidate = HyphenatedCandidate(
            text=word,
            count=count,
            documents=documents,
            corpora=corpora,
            upper=pooled_upper[word],
            lower=pooled_lower[word],
            uncertain=pooled_uncertain[word],
            inner_upper=pooled_inner_upper[word],
            solid=pooled_solid[word],
            spaced=pooled_spaced[word],
        )
        candidates.append(
            replace(
                candidate,
                category=classify(
                    candidate,
                    proper_share=proper_share,
                    min_case_evidence=min_case_evidence,
                    solid_ratio=solid_ratio,
                ),
            )
        )

    candidates.sort(key=lambda item: (-item.documents, -item.count, item.text))
    return candidates


def group_by_category(
    candidates: Iterable[HyphenatedCandidate],
) -> "OrderedDict[str, List[HyphenatedCandidate]]":
    """Split ranked candidates into report sections, in ``CATEGORY_ORDER``.

    Within a section the order the caller supplied is preserved, so a ranked
    list stays ranked.  Empty sections are omitted.

    Args:
        candidates: Ranked candidates, each carrying a ``category``.

    Returns:
        Category -> its candidates, ordered as ``CATEGORY_ORDER`` says.
    """
    grouped: Dict[str, List[HyphenatedCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.category, []).append(candidate)

    ordered: "OrderedDict[str, List[HyphenatedCandidate]]" = OrderedDict()
    for category in CATEGORY_ORDER:
        if grouped.get(category):
            ordered[category] = grouped[category]
    # Anything a future category adds without updating CATEGORY_ORDER still
    # reaches the report rather than vanishing from it.
    for category, group in sorted(grouped.items()):
        if category not in ordered:
            ordered[category] = group
    return ordered
