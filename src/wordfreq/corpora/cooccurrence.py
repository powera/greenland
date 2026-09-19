"""Which nouns a verb is actually used with, measured over the raw corpora.

The curriculum wants to introduce a verb alongside the words it goes with:
"eat" belongs with the food group, "wear" with clothing.  Nothing in the
database records that.  ``sentence_words`` looks like it should, but it covers
only 92 of 333 leveled verbs, and those sentences were generated *from* the
curriculum, so the co-occurrence in them partly restates the leveling it would
be used to derive.  The raw corpus text is independent evidence and covers
97% of the same verbs.

The measurement is deliberately crude: for each verb occurrence, count the
noun subtypes appearing in a short window after it.  English is SVO, so the
object follows the verb, and a forward window is a cheap stand-in for "what
does this verb take" without a parser.

**Raw counts are not the answer.**  ``concept_idea`` and ``time_period`` are
large, frequent subtypes that sit near every verb in the language; ranking by
raw count makes them the top "affinity" for almost everything ("ride" ->
time_period, "read" -> concept_idea).  :func:`score_affinity` therefore scores
lift -- how much more often a subtype follows *this* verb than it follows
verbs in general -- which is what lets "drink" -> beverage beat them.

Two things this cannot do, recorded here so the output is read correctly:

* Matching is on surface form, so noun and verb senses of the same spelling
  are conflated ("work", "play", "call").  A count is evidence for a human
  decision, not an assignment.
* ``be``, ``have`` and ``do`` are excluded entirely; see
  :data:`HARDCODED_VERB_LEVELS`.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Final, Iterator, List, Mapping, Optional, Sequence, Tuple

#: Tokens after a verb that count as its neighbourhood.  Six is wide enough to
#: reach past a determiner and an adjective or two ("ate the last green
#: apple") and narrow enough that the next clause rarely intrudes.
DEFAULT_WINDOW: Final[int] = 6

#: A verb needs this many occurrences before its profile means anything.
DEFAULT_MIN_VERB_COUNT: Final[int] = 30

#: A (verb, subtype) pair needs this many before it is scored, so a single
#: chance co-occurrence cannot produce a spectacular lift.
DEFAULT_MIN_PAIR_COUNT: Final[int] = 5

# These verbs are placed by hand, not measured, and the tool must not imply
# otherwise. Two different reasons put a verb here.
#
# ``be`` and ``have``: their English counts are dominated by *auxiliary* uses
# -- "I have seen", "I was going" -- which are periphrastic tense rather than
# the verb. Other languages do not build tenses this way, so an English count
# says nothing about where the lemma belongs in a Lithuanian or Spanish
# course. They are also polysemous: "be" is copula, existential and auxiliary
# at once, stored as a single undisambiguated lemma, unlike "make" which is
# split into create/earn senses.
#
# ``like``: the measurement simply gets it wrong. It scores 4.3x on ``animal``
# because of "animals like wolves" -- the preposition, not the verb -- so the
# flat profile that marks a general-purpose verb never shows up for it. It is
# one of the most broadly combinable verbs in the language and belongs early
# regardless of what the corpus says.
#
# All of them are needed early -- a learner cannot build a sentence without
# them -- so the levels here are a judgment call to be edited by hand. Do not
# replace this with a derived value.
HARDCODED_VERB_LEVELS: Final[Mapping[str, int]] = {
    "be": 3,
    "have": 4,
    "like": 4,
}

# ``do`` is deliberately *not* here, and not in the lemma table either.
#
# ``be`` and ``have`` are stored with their content senses -- "to exist", "to
# possess" -- which are teachable word-for-word. ``do`` has no equivalent: its
# uses are auxiliary ("did you go"), emphatic ("I *do* like it") and pro-verb
# ("she did too"), none of which survives a word-for-word gloss, and none of
# which a Lithuanian or Spanish course expresses with a single verb. Leaving it
# out is a decision, not an oversight; do not "fix" it by adding a level.


def _auxiliary_surface_forms() -> frozenset[str]:
    """Every auxiliary surface form, for exclusion from the scan.

    Sourced from ``langtools.en``'s auxiliary list rather than written out
    again here, so the two cannot disagree about whether "has" is one.  The
    list also carries the modals ("will", "must"), which are excluded for the
    same reason: they are tense and mood machinery, not vocabulary a noun
    group needs.

    This is not the same set as :data:`HARDCODED_VERB_LEVELS`. "like" is
    hardcoded because the measurement misreads it, but its occurrences are
    still ordinary evidence for the verbs around it, so it stays in the scan.
    """
    from langtools.en.grammatical_words import ENGLISH_AUXILIARY_VERBS

    return frozenset(word.lower() for word in ENGLISH_AUXILIARY_VERBS)


@dataclass
class CooccurrenceCounts:
    """Raw verb/subtype co-occurrence tallies from one or more sources."""

    #: How often each verb was seen at all.
    verb_totals: Counter[str] = field(default_factory=Counter)
    #: verb -> subtype -> how often that subtype followed it in the window.
    pair_counts: Dict[str, Counter[str]] = field(default_factory=dict)
    #: How often each subtype was seen in *any* verb's window, which is the
    #: base rate :func:`score_affinity` scores lift against.
    subtype_totals: Counter[str] = field(default_factory=Counter)
    #: Documents scanned, for the report header.
    documents_scanned: int = 0

    def add_pair(self, verb: str, subtype: str) -> None:
        """Record one subtype occurrence inside *verb*'s window."""
        self.pair_counts.setdefault(verb, Counter())[subtype] += 1
        self.subtype_totals[subtype] += 1

    def merge(self, other: "CooccurrenceCounts") -> None:
        """Fold another source's counts into this one."""
        self.verb_totals.update(other.verb_totals)
        for verb, counts in other.pair_counts.items():
            self.pair_counts.setdefault(verb, Counter()).update(counts)
        self.subtype_totals.update(other.subtype_totals)
        self.documents_scanned += other.documents_scanned


@dataclass(frozen=True)
class Affinity:
    """One scored (verb, subtype) pairing."""

    verb: str
    subtype: str
    count: int
    #: Share of this verb's windowed nouns that were this subtype.
    share: float
    #: ``share`` divided by the subtype's overall share. 1.0 means "no more
    #: often than after any verb"; 4.0 means four times as often.
    lift: float

    @property
    def log_lift(self) -> float:
        """Lift on a log scale, for ranking and clustering."""
        return math.log2(self.lift) if self.lift > 0 else float("-inf")


def iter_windows(
    tokens: Sequence[str],
    verbs: Mapping[str, str],
    nouns: Mapping[str, str],
    *,
    window: int = DEFAULT_WINDOW,
    excluded: Optional[frozenset[str]] = None,
) -> Iterator[Tuple[str, str]]:
    """Yield ``(verb, noun_subtype)`` for each noun following a verb.

    *verbs* and *nouns* map a surface form to its ``pos_subtype``; only the
    keys matter for verbs, but the mapping is what callers already hold.
    *excluded* forms are skipped on **both** sides: an auxiliary "have" is not
    a verb whose objects we want, and it is not evidence about the noun it
    happens to precede either.

    The window is forward-only and stops at the end of the token list, so a
    verb in the last few tokens simply contributes fewer pairs.
    """
    skip = excluded or frozenset()
    for index, token in enumerate(tokens):
        if token not in verbs or token in skip:
            continue
        for offset in range(index + 1, min(index + 1 + window, len(tokens))):
            neighbour = tokens[offset]
            if neighbour in skip:
                continue
            subtype = nouns.get(neighbour)
            if subtype is not None:
                yield token, subtype


def count_document(
    tokens: Sequence[str],
    verbs: Mapping[str, str],
    nouns: Mapping[str, str],
    counts: CooccurrenceCounts,
    *,
    window: int = DEFAULT_WINDOW,
    excluded: Optional[frozenset[str]] = None,
) -> None:
    """Fold one document's tokens into *counts*, in place."""
    skip = excluded or frozenset()
    for token in tokens:
        if token in verbs and token not in skip:
            counts.verb_totals[token] += 1
    for verb, subtype in iter_windows(tokens, verbs, nouns, window=window, excluded=excluded):
        counts.add_pair(verb, subtype)
    counts.documents_scanned += 1


def score_affinity(
    counts: CooccurrenceCounts,
    *,
    min_verb_count: int = DEFAULT_MIN_VERB_COUNT,
    min_pair_count: int = DEFAULT_MIN_PAIR_COUNT,
) -> Dict[str, List[Affinity]]:
    """Score each verb's subtypes by lift, best first.

    A verb below *min_verb_count*, or a pairing below *min_pair_count*, is
    left out rather than scored on evidence too thin to mean anything.
    """
    total_subtype_occurrences = sum(counts.subtype_totals.values())
    if total_subtype_occurrences == 0:
        return {}

    scored: Dict[str, List[Affinity]] = {}
    for verb, subtype_counts in counts.pair_counts.items():
        if counts.verb_totals.get(verb, 0) < min_verb_count:
            continue
        verb_total = sum(subtype_counts.values())
        if verb_total == 0:
            continue
        affinities: List[Affinity] = []
        for subtype, count in subtype_counts.items():
            if count < min_pair_count:
                continue
            share = count / verb_total
            base_rate = counts.subtype_totals[subtype] / total_subtype_occurrences
            if base_rate == 0:
                continue
            affinities.append(
                Affinity(
                    verb=verb,
                    subtype=subtype,
                    count=count,
                    share=share,
                    lift=share / base_rate,
                )
            )
        if affinities:
            affinities.sort(key=lambda item: (-item.lift, -item.count, item.subtype))
            scored[verb] = affinities
    return scored


def top_verbs_for_subtype(
    scored: Mapping[str, Sequence[Affinity]],
    subtype: str,
    *,
    min_lift: float = 1.5,
) -> List[Affinity]:
    """Every verb whose affinity for *subtype* clears *min_lift*, best first.

    This is the "which verbs does this noun group need" view: the same scores
    read by subtype rather than by verb.
    """
    matches: List[Affinity] = []
    for affinities in scored.values():
        for affinity in affinities:
            if affinity.subtype == subtype and affinity.lift >= min_lift:
                matches.append(affinity)
    matches.sort(key=lambda item: (-item.lift, -item.count, item.verb))
    return matches


def verb_clusters(
    scored: Mapping[str, Sequence[Affinity]],
    *,
    top_n: int = 2,
    min_lift: float = 1.5,
) -> Dict[Tuple[str, ...], List[str]]:
    """Group verbs sharing their strongest subtypes.

    The key is the verb's top *top_n* subtypes clearing *min_lift*, as a
    sorted tuple, so "eat" and "taste" land together if both lean on food.
    Returned groups are raw material for naming a verb unit by hand -- a
    two-verb group is a suggestion, not a unit.
    """
    clusters: Dict[Tuple[str, ...], List[str]] = {}
    for verb, affinities in scored.items():
        signature = tuple(
            sorted(affinity.subtype for affinity in affinities[:top_n] if affinity.lift >= min_lift)
        )
        if not signature:
            continue
        clusters.setdefault(signature, []).append(verb)
    for verbs in clusters.values():
        verbs.sort()
    return clusters


def excluded_surface_forms() -> frozenset[str]:
    """Every surface form the scan must ignore on both sides of a window."""
    return _auxiliary_surface_forms()
