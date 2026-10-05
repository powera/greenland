"""Corpus profiles of Trakaido levels: which corpora a level's words lean toward.

Each levelled English lemma is given *corpus weights*: one unit of weight,
split between the corpora it is clearly over-represented in, relative to the
rest of the collection.  Summing those weights by ``Lemma.difficulty_level``
gives each level a mix -- "330: 80% wiki_arts" -- and inverting the mix answers
the question this exists for: given an arts word, which levels hold mostly arts
words?

Measuring a lemma
-----------------
The measurement is a Zipf delta, the same one ``wordfreq.frequency.corpus_skew``
uses for tokens, applied to the lemma's *share-scaled* frequency rollup
(``wordfreq.lexeme_frequency.get_lexeme_frequency``).  The rollup is the
frequency counterpart of ``combined_rank.get_lemma_corpus_rank``: both split a
contested spelling between its senses by ``sense_prominence``, so "tonic" the
drink and "tonic" the musical note do not inherit identical profiles.  Ranks
are not compared directly because the corpora differ in size, whereas the
frequencies are all per million words and already on one scale.

A corpus that does not list any of the lemma's forms is not skipped: the lemma
is placed at that corpus's *floor*, the Zipf of the rarest form it does list.
Absence from a corpus that keeps its top 6000 words says the word is rarer than
its 6000th, and dropping the corpus instead would let a word seen in only two
corpora look as balanced as one seen in all nineteen.  A share-scaled frequency
below the floor is raised to it for the same reason the rank path caps at the
unknown rank: the corpus cannot measure below its own cutoff.

Then, for each corpus ``c``::

    skew(c) = zipf(c) - mean(zipf(other corpora))

Splitting the weight
--------------------
Every corpus whose skew reaches ``min_skew`` shares the lemma's weight, in
proportion to how far past the threshold it is.  A word twice as far past it in
wiki_arts as in wiki_history counts 2/3 toward arts and 1/3 toward history,
rather than wholly toward whichever happened to edge ahead; a corpus only just
over the line gets almost nothing, so crossing the threshold is not a cliff.

A lemma no corpus reaches the threshold for -- "the", "of", "after" -- puts its
whole weight on :data:`GENERAL`.  Those words say nothing about topic, and
without the bucket every level would be dominated by whichever corpus the
common words happen to tip toward.  :meth:`LevelProfile.share` can leave
GENERAL out of the denominator, giving a level's topical mix on its own.

Limits
------
This works per spelling-weighted sense, not per meaning: the share split
separates senses only as well as their ``sense_prominence`` ratings do, and a
*new* sense with no rating yet profiles as its spelling does.  Deciding which
"tonic" a new word is still needs its definition.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from storage.lexeme import get_lexeme
from storage.models.schema import ExternalLexemeAnnotation, Lemma
from wordfreq.frequency.corpus import get_enabled_corpus_names
from wordfreq.frequency.corpus_skew import MIN_FREQUENCY, zipf_from_frequency
from wordfreq.lexeme_frequency import get_lexeme_frequency

logger = logging.getLogger(__name__)

#: Label for a lemma that leans toward no corpus strongly enough to count.
GENERAL: str = "general"

#: Default minimum skew (in Zipf units) for a corpus to receive any weight.
#: 0.5 is about three times as common there as in the average other corpus.
DEFAULT_MIN_SKEW: float = 0.5


@dataclass(frozen=True)
class LemmaCorpusProfile:
    """One lemma's corpus measurements and how its weight is split."""

    lemma_id: int
    lemma_text: str
    disambiguation: Optional[str]
    level: int
    zipf_by_corpus: Dict[str, float]  # floored; every corpus has a value
    attested_corpora: Tuple[str, ...]  # corpora that actually list a form
    skew_by_corpus: Dict[str, float]
    weights: Dict[str, float]  # corpus name or GENERAL -> fraction; sums to 1.0

    @property
    def display_text(self) -> str:
        if self.disambiguation:
            return f"{self.lemma_text} ({self.disambiguation})"
        return self.lemma_text

    @property
    def top_corpus(self) -> str:
        """The corpus (or GENERAL) holding the largest weight."""
        return min(self.weights.items(), key=lambda pair: (-pair[1], pair[0]))[0]

    @property
    def top_skew(self) -> float:
        """The largest skew toward any corpus, even when under the threshold."""
        return max(self.skew_by_corpus.values(), default=0.0)


@dataclass
class LevelProfile:
    """The corpus mix of one level."""

    level: int
    lemma_count: int = 0  # lemmas profiled (attested in at least one corpus)
    unattested_count: int = 0  # lemmas at this level no corpus lists
    weight_totals: Dict[str, float] = field(default_factory=dict)  # corpus/GENERAL -> sum

    def add(self, lemma_profile: LemmaCorpusProfile) -> None:
        self.lemma_count += 1
        for name, weight in lemma_profile.weights.items():
            self.weight_totals[name] = self.weight_totals.get(name, 0.0) + weight

    @property
    def topical_weight(self) -> float:
        """Total weight on real corpora, i.e. everything but GENERAL."""
        return self.lemma_count - self.weight_totals.get(GENERAL, 0.0)

    def share(self, name: str, include_general: bool = True) -> float:
        """Fraction of this level's weight on ``name`` (a corpus or GENERAL).

        With ``include_general=False`` the denominator is only the topical
        weight, so a level of 30 everyday words and 10 arts words reads as
        100% arts rather than 25%.
        """
        if not include_general and name == GENERAL:
            return 0.0
        denominator = self.lemma_count if include_general else self.topical_weight
        if denominator <= 0:
            return 0.0
        return self.weight_totals.get(name, 0.0) / denominator

    def ranked_corpora(self, include_general: bool = True) -> List[Tuple[str, float]]:
        """``(corpus_or_GENERAL, share)`` pairs, largest share first."""
        names = [name for name in self.weight_totals if include_general or name != GENERAL]
        return sorted(
            ((name, self.share(name, include_general)) for name in names),
            key=lambda pair: (-pair[1], pair[0]),
        )


@dataclass(frozen=True)
class LevelCandidate:
    """A level's fit for words that lean toward one corpus."""

    level: int
    share: float  # fraction of the level's weight on this corpus
    weight: float  # summed lemma weight on this corpus
    lemma_count: int
    lift: float  # share relative to the corpus's share across all levels


def get_corpus_zipf_floors(session: Session, corpus_names: Sequence[str]) -> Dict[str, float]:
    """The Zipf of the rarest form each corpus lists -- where absence places a word.

    A corpus with no usable frequencies falls back to the Zipf of
    :data:`corpus_skew.MIN_FREQUENCY`, below anything a real corpus would hold.
    """
    fallback = zipf_from_frequency(MIN_FREQUENCY)
    assert fallback is not None
    floors: Dict[str, float] = {}
    for corpus_name in corpus_names:
        min_frequency = (
            session.query(func.min(ExternalLexemeAnnotation.frequency))
            .filter(
                ExternalLexemeAnnotation.source == f"wordfreq_{corpus_name}",
                ExternalLexemeAnnotation.frequency >= MIN_FREQUENCY,
            )
            .scalar()
        )
        zipf = zipf_from_frequency(min_frequency) if min_frequency is not None else None
        floors[corpus_name] = zipf if zipf is not None else fallback
    return floors


def skew_from_zipfs(zipf_by_corpus: Dict[str, float]) -> Dict[str, float]:
    """Each corpus's Zipf minus the mean of every other corpus's.

    Needs at least two corpora; with one there is no "elsewhere" and every
    skew is 0.0.
    """
    count = len(zipf_by_corpus)
    if count < 2:
        return {name: 0.0 for name in zipf_by_corpus}
    total = sum(zipf_by_corpus.values())
    return {name: zipf - (total - zipf) / (count - 1) for name, zipf in zipf_by_corpus.items()}


def corpus_weights(skew_by_corpus: Dict[str, float], min_skew: float) -> Dict[str, float]:
    """Split one unit of weight between the corpora at or past ``min_skew``.

    Each qualifying corpus gets weight in proportion to its excess over the
    threshold.  When none qualifies, or every qualifier sits exactly on it,
    the whole weight goes to GENERAL (or, in the second case, is split evenly
    between the qualifiers).
    """
    qualifying = {name: skew for name, skew in skew_by_corpus.items() if skew >= min_skew}
    if not qualifying:
        return {GENERAL: 1.0}
    excess = {name: skew - min_skew for name, skew in qualifying.items()}
    total = sum(excess.values())
    if total <= 0:
        return {name: 1.0 / len(qualifying) for name in qualifying}
    return {name: value / total for name, value in excess.items() if value > 0}


def profile_from_zipfs(
    lemma_id: int,
    lemma_text: str,
    disambiguation: Optional[str],
    level: int,
    zipf_by_corpus: Dict[str, float],
    attested_corpora: Sequence[str],
    min_skew: float = DEFAULT_MIN_SKEW,
) -> LemmaCorpusProfile:
    """Score an already-measured lemma.

    Split from :func:`profile_lemma` so a saved measurement can be re-scored
    at a different ``min_skew`` without touching the database.
    """
    skew_by_corpus = skew_from_zipfs(zipf_by_corpus)
    return LemmaCorpusProfile(
        lemma_id=lemma_id,
        lemma_text=lemma_text,
        disambiguation=disambiguation,
        level=level,
        zipf_by_corpus=dict(zipf_by_corpus),
        attested_corpora=tuple(attested_corpora),
        skew_by_corpus=skew_by_corpus,
        weights=corpus_weights(skew_by_corpus, min_skew),
    )


def profile_lemma(
    session: Session,
    lemma: Lemma,
    corpus_names: Sequence[str],
    floors: Dict[str, float],
    min_skew: float = DEFAULT_MIN_SKEW,
) -> Optional[LemmaCorpusProfile]:
    """Measure one lemma against every corpus.

    Returns None when the lemma has no level or no English forms, or when no
    corpus lists any of its forms (multi-word lemmas, mostly): with nothing
    attested, every corpus would sit at its floor and the weights would only
    say which floor is highest.
    """
    if lemma.difficulty_level is None:
        return None
    lexeme = get_lexeme(session, lemma.id, "en")
    if lexeme is None:
        return None

    zipf_by_corpus: Dict[str, float] = {}
    attested: List[str] = []
    for corpus_name in corpus_names:
        rollup = get_lexeme_frequency(session, lexeme, corpus_name)
        floor = floors[corpus_name]
        zipf = zipf_from_frequency(rollup.total_frequency) if rollup.form_breakdown else None
        if rollup.form_breakdown:
            attested.append(corpus_name)
        zipf_by_corpus[corpus_name] = floor if zipf is None else max(zipf, floor)

    if not attested:
        return None

    return profile_from_zipfs(
        lemma.id,
        lemma.lemma_text,
        lemma.disambiguation,
        lemma.difficulty_level,
        zipf_by_corpus,
        attested,
        min_skew,
    )


def aggregate_levels(
    lemma_profiles: Iterable[LemmaCorpusProfile],
    unattested_by_level: Optional[Dict[int, int]] = None,
) -> Dict[int, LevelProfile]:
    """Sum lemma weights into one :class:`LevelProfile` per level."""
    level_profiles: Dict[int, LevelProfile] = {}
    for level, count in (unattested_by_level or {}).items():
        level_profiles.setdefault(level, LevelProfile(level=level)).unattested_count = count
    for lemma_profile in lemma_profiles:
        level_profiles.setdefault(lemma_profile.level, LevelProfile(level=lemma_profile.level)).add(
            lemma_profile
        )
    return level_profiles


def build_level_profiles(
    session: Session,
    min_skew: float = DEFAULT_MIN_SKEW,
    levels: Optional[Sequence[int]] = None,
    corpus_names: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> Tuple[Dict[int, LevelProfile], List[LemmaCorpusProfile]]:
    """Profile every levelled lemma and roll the results up by level.

    Read-only.  Uses the base ``Lemma.difficulty_level``; per-language
    overrides and excluded (``-1``) or unset levels are ignored.

    Args:
        session: Open session.
        min_skew: Skew a corpus needs to receive any of a lemma's weight.
        levels: Restrict to these levels.  None profiles every level.
        corpus_names: Corpora to measure against.  Defaults to every enabled one.
        limit: Profile at most this many lemmas (for a quick look).
        progress: Called as ``progress(done, total)`` after each lemma.

    Returns:
        ``({level: LevelProfile}, [LemmaCorpusProfile, ...])``.
    """
    names = list(corpus_names) if corpus_names is not None else get_enabled_corpus_names()
    floors = get_corpus_zipf_floors(session, names)

    query = session.query(Lemma).filter(
        Lemma.difficulty_level.isnot(None), Lemma.difficulty_level > 0
    )
    if levels is not None:
        query = query.filter(Lemma.difficulty_level.in_(list(levels)))
    lemmas = query.order_by(Lemma.difficulty_level, Lemma.id).all()
    if limit is not None:
        lemmas = lemmas[:limit]

    lemma_profiles: List[LemmaCorpusProfile] = []
    unattested_by_level: Dict[int, int] = {}
    for index, lemma in enumerate(lemmas):
        assert lemma.difficulty_level is not None
        lemma_profile = profile_lemma(session, lemma, names, floors, min_skew)
        if lemma_profile is None:
            unattested_by_level[lemma.difficulty_level] = (
                unattested_by_level.get(lemma.difficulty_level, 0) + 1
            )
        else:
            lemma_profiles.append(lemma_profile)
        if progress is not None:
            progress(index + 1, len(lemmas))

    return aggregate_levels(lemma_profiles, unattested_by_level), lemma_profiles


def rank_levels_for_corpus(
    level_profiles: Dict[int, LevelProfile],
    corpus_name: str,
    min_lemmas: int = 5,
    limit: Optional[int] = None,
    include_general: bool = True,
) -> List[LevelCandidate]:
    """Levels ordered by how much of their vocabulary leans toward ``corpus_name``.

    This is the "an arts word belongs near 330, 335, 105" lookup.  ``lift``
    compares a level's share with the corpus's share across every level, so a
    level that is 20% arts in a collection that is 2% arts reads as 10x.

    Args:
        level_profiles: From :func:`build_level_profiles`.
        corpus_name: A corpus name (or GENERAL).
        min_lemmas: Skip levels with fewer profiled lemmas than this; a level of
            two words is 50% anything.
        limit: Truncate to this many candidates.
        include_general: Whether shares count GENERAL weight in the denominator;
            see :meth:`LevelProfile.share`.
    """
    corpus_total = sum(
        profile.weight_totals.get(corpus_name, 0.0) for profile in level_profiles.values()
    )
    if include_general:
        denominator = float(sum(profile.lemma_count for profile in level_profiles.values()))
    else:
        denominator = sum(profile.topical_weight for profile in level_profiles.values())
    base_share = corpus_total / denominator if denominator > 0 else 0.0

    candidates: List[LevelCandidate] = []
    for profile in level_profiles.values():
        weight = profile.weight_totals.get(corpus_name, 0.0)
        if weight <= 0 or profile.lemma_count < min_lemmas:
            continue
        share = profile.share(corpus_name, include_general)
        candidates.append(
            LevelCandidate(
                level=profile.level,
                share=share,
                weight=weight,
                lemma_count=profile.lemma_count,
                lift=share / base_share if base_share else math.inf,
            )
        )
    candidates.sort(key=lambda candidate: (-candidate.share, -candidate.weight, candidate.level))
    if limit is not None:
        candidates = candidates[:limit]
    return candidates


__all__ = [
    "DEFAULT_MIN_SKEW",
    "GENERAL",
    "LemmaCorpusProfile",
    "LevelCandidate",
    "LevelProfile",
    "aggregate_levels",
    "build_level_profiles",
    "corpus_weights",
    "get_corpus_zipf_floors",
    "profile_from_zipfs",
    "profile_lemma",
    "rank_levels_for_corpus",
    "skew_from_zipfs",
]
