"""Corpus profiles of Trakaido levels: which corpora a level's words lean toward.

Each levelled English lemma gets a *top corpus*: the corpus it is most
over-represented in, relative to the rest of the collection.  Grouping lemmas by
``Lemma.difficulty_level`` then gives each level a mix -- "330: 80% wiki_arts"
-- and inverting that mix answers the question this exists for: given an arts
word, which levels hold mostly arts words?

How a lemma's top corpus is chosen
----------------------------------
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

and the top corpus is the one with the largest skew.  When even that skew is
below ``min_skew``, the word is not characteristic of any corpus ("the", "after")
and is counted as :data:`GENERAL` instead -- otherwise every level would be
dominated by whichever corpus the common words happen to tip toward.

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
from typing import Callable, Dict, List, Optional, Sequence, Tuple

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

#: Default minimum skew (in Zipf units) for a lemma to be assigned a corpus.
#: 0.5 is about three times as common there as in the average other corpus.
DEFAULT_MIN_SKEW: float = 0.5


@dataclass(frozen=True)
class LemmaCorpusProfile:
    """One lemma's corpus measurements and the corpus it leans toward."""

    lemma_id: int
    lemma_text: str
    disambiguation: Optional[str]
    level: int
    zipf_by_corpus: Dict[str, float]  # floored; every corpus has a value
    attested_corpora: Tuple[str, ...]  # corpora that actually list a form
    skew_by_corpus: Dict[str, float]
    top_corpus: str  # a corpus name, or GENERAL
    top_skew: float  # skew of the best corpus, even when below the threshold

    @property
    def display_text(self) -> str:
        if self.disambiguation:
            return f"{self.lemma_text} ({self.disambiguation})"
        return self.lemma_text


@dataclass
class LevelProfile:
    """The corpus mix of one level."""

    level: int
    lemma_count: int = 0  # lemmas profiled (attested in at least one corpus)
    unattested_count: int = 0  # lemmas at this level no corpus lists
    top_corpus_counts: Dict[str, int] = field(default_factory=dict)
    skew_sums: Dict[str, float] = field(default_factory=dict)

    def share(self, corpus_name: str) -> float:
        """Fraction of this level's profiled lemmas whose top corpus is ``corpus_name``."""
        if self.lemma_count == 0:
            return 0.0
        return self.top_corpus_counts.get(corpus_name, 0) / self.lemma_count

    def mean_skew(self, corpus_name: str) -> float:
        """Average skew toward ``corpus_name`` across the level's lemmas.

        A softer signal than :meth:`share`: it counts a word that leans toward
        two corpora toward both, rather than only toward the winner.
        """
        if self.lemma_count == 0:
            return 0.0
        return self.skew_sums.get(corpus_name, 0.0) / self.lemma_count

    def ranked_corpora(self) -> List[Tuple[str, float]]:
        """``(corpus_or_GENERAL, share)`` pairs, largest share first."""
        return sorted(
            ((name, self.share(name)) for name in self.top_corpus_counts),
            key=lambda pair: (-pair[1], pair[0]),
        )


@dataclass(frozen=True)
class LevelCandidate:
    """A level's fit for words that lean toward one corpus."""

    level: int
    share: float  # fraction of the level's lemmas with this top corpus
    count: int
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


def choose_top_corpus(skew_by_corpus: Dict[str, float], min_skew: float) -> Tuple[str, float]:
    """The corpus with the largest skew, or GENERAL when it is under ``min_skew``.

    Ties go to the alphabetically first corpus so the result is stable.
    """
    if not skew_by_corpus:
        return GENERAL, 0.0
    best_name, best_skew = min(skew_by_corpus.items(), key=lambda pair: (-pair[1], pair[0]))
    if best_skew < min_skew:
        return GENERAL, best_skew
    return best_name, best_skew


def profile_lemma(
    session: Session,
    lemma: Lemma,
    corpus_names: Sequence[str],
    floors: Dict[str, float],
    min_skew: float = DEFAULT_MIN_SKEW,
) -> Optional[LemmaCorpusProfile]:
    """Measure one lemma against every corpus.

    Returns None when the lemma has no English forms, or when no corpus lists
    any of them (multi-word lemmas, mostly): with nothing attested, every
    corpus would sit at its floor and the "top corpus" would only say which
    floor is highest.
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

    skew_by_corpus = skew_from_zipfs(zipf_by_corpus)
    top_corpus, top_skew = choose_top_corpus(skew_by_corpus, min_skew)
    return LemmaCorpusProfile(
        lemma_id=lemma.id,
        lemma_text=lemma.lemma_text,
        disambiguation=lemma.disambiguation,
        level=lemma.difficulty_level,
        zipf_by_corpus=zipf_by_corpus,
        attested_corpora=tuple(attested),
        skew_by_corpus=skew_by_corpus,
        top_corpus=top_corpus,
        top_skew=top_skew,
    )


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
        min_skew: Threshold below which a lemma counts as GENERAL.
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

    level_profiles: Dict[int, LevelProfile] = {}
    lemma_profiles: List[LemmaCorpusProfile] = []
    for index, lemma in enumerate(lemmas):
        assert lemma.difficulty_level is not None
        level_profile = level_profiles.setdefault(
            lemma.difficulty_level, LevelProfile(level=lemma.difficulty_level)
        )
        lemma_profile = profile_lemma(session, lemma, names, floors, min_skew)
        if lemma_profile is None:
            level_profile.unattested_count += 1
        else:
            lemma_profiles.append(lemma_profile)
            level_profile.lemma_count += 1
            level_profile.top_corpus_counts[lemma_profile.top_corpus] = (
                level_profile.top_corpus_counts.get(lemma_profile.top_corpus, 0) + 1
            )
            for corpus_name, skew in lemma_profile.skew_by_corpus.items():
                level_profile.skew_sums[corpus_name] = (
                    level_profile.skew_sums.get(corpus_name, 0.0) + skew
                )
        if progress is not None:
            progress(index + 1, len(lemmas))

    return level_profiles, lemma_profiles


def rank_levels_for_corpus(
    level_profiles: Dict[int, LevelProfile],
    corpus_name: str,
    min_lemmas: int = 5,
    limit: Optional[int] = None,
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
    """
    total_lemmas = sum(profile.lemma_count for profile in level_profiles.values())
    total_count = sum(
        profile.top_corpus_counts.get(corpus_name, 0) for profile in level_profiles.values()
    )
    base_share = total_count / total_lemmas if total_lemmas else 0.0

    candidates: List[LevelCandidate] = []
    for profile in level_profiles.values():
        count = profile.top_corpus_counts.get(corpus_name, 0)
        if count == 0 or profile.lemma_count < min_lemmas:
            continue
        share = profile.share(corpus_name)
        candidates.append(
            LevelCandidate(
                level=profile.level,
                share=share,
                count=count,
                lemma_count=profile.lemma_count,
                lift=share / base_share if base_share else math.inf,
            )
        )
    candidates.sort(key=lambda candidate: (-candidate.share, -candidate.count, candidate.level))
    if limit is not None:
        candidates = candidates[:limit]
    return candidates


__all__ = [
    "DEFAULT_MIN_SKEW",
    "GENERAL",
    "LemmaCorpusProfile",
    "LevelCandidate",
    "LevelProfile",
    "build_level_profiles",
    "choose_top_corpus",
    "get_corpus_zipf_floors",
    "profile_lemma",
    "rank_levels_for_corpus",
    "skew_from_zipfs",
]
