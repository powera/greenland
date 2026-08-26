"""Find words that belong to one corpus far more than to the others.

"sugar" is not a rare word, but it is a *cooking* word: rank 26 in the cooking
corpus against rank 2623 in 19th-century books.  "simmer" is the same story
more sharply.  This module scores that lopsidedness so a page can list, per
corpus, the words most characteristic of it -- the cooking vocabulary, the
science vocabulary -- rather than merely the words it happens to rank highest,
which would just be "the" and "and" six times over.

The score is a Zipf delta.  Each corpus file stores frequency per million
words (the sums per source come to ~1e6), so a raw frequency is already
normalized for corpus size and comparable across corpora without refitting
anything::

    zipf = log10(frequency_per_million) + 3

which puts a word occurring once per million at 3.0 and once per thousand at
6.0.  A word's score in a corpus is its Zipf there minus the mean of its Zipf
in every *other* corpus that has it::

    score = zipf_here - mean(zipf_elsewhere)

so +1.0 means "ten times as common here as in the rest of the collection".
Ranks are deliberately not used for the score: the corpora are different sizes
(cooking holds 1000 words, 19th_books 7500), so rank 500 means something
different in each, whereas the frequencies are already on one scale.  The ranks
*are* carried alongside for display, because "rank 26 here vs. 2623 elsewhere"
is what makes the score legible -- the delta orders the list, the ranks explain
it.

A word appearing in only one corpus has no "elsewhere" to compare against.
Those are reported separately (``exclusive``) rather than scored, since any
score for them would be an artifact of the comparison set rather than a
measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from storage.models.schema import ExternalLexemeAnnotation, WordToken
from wordfreq.frequency.corpus import get_enabled_corpus_names

# Frequencies are stored per million words, so log10(f) + 3 is the Zipf value
# on the usual scale (1 per billion = 0, 1 per million = 3, 1 per thousand = 6).
ZIPF_OFFSET: float = 3.0

# Below this stored frequency a value is treated as absent rather than as a
# very negative Zipf: log10 of a near-zero frequency dominates any mean it
# enters, and a count that small is noise in a corpus of this size anyway.
MIN_FREQUENCY: float = 1e-6


def zipf_from_frequency(frequency: float) -> Optional[float]:
    """Convert a per-million corpus frequency to a Zipf value.

    Returns None for a non-positive or negligible frequency, which has no
    meaningful logarithm and should be treated as "not attested here".
    """
    if frequency is None or frequency < MIN_FREQUENCY:
        return None
    return math.log10(frequency) + ZIPF_OFFSET


@dataclass(frozen=True)
class CorpusPresence:
    """One corpus's measurement of one token."""

    corpus_name: str
    ordinal_rank: Optional[int]
    frequency: Optional[float]
    zipf: Optional[float]


@dataclass(frozen=True)
class SkewedWord:
    """A token scored for how strongly it leans toward one corpus.

    ``score`` is the Zipf delta that orders a listing; ``rank_here`` and
    ``mean_rank_elsewhere`` are the human-readable version of the same fact and
    are what the page shows next to it.
    """

    word_token_id: int
    token: str
    language_code: str
    corpus_name: str
    score: float
    zipf_here: float
    mean_zipf_elsewhere: float
    rank_here: Optional[int]
    mean_rank_elsewhere: Optional[float]
    corpus_count: int  # how many corpora attest this token at all
    presences: Sequence[CorpusPresence] = ()

    @property
    def rank_ratio(self) -> Optional[float]:
        """How many times better this token ranks here than elsewhere.

        Display only -- ranks are not comparable across corpora of different
        sizes, which is why ``score`` is a Zipf delta instead. Returns None
        when either rank is missing.
        """
        if self.rank_here is None or not self.rank_here:
            return None
        if self.mean_rank_elsewhere is None:
            return None
        return self.mean_rank_elsewhere / float(self.rank_here)


def _wordfreq_source(corpus_name: str) -> str:
    return f"wordfreq_{corpus_name}"


def _corpus_from_source(source: str) -> Optional[str]:
    prefix = "wordfreq_"
    if source.startswith(prefix):
        return source[len(prefix) :]
    return None


def _load_presences(
    session: Session,
    corpus_names: Sequence[str],
    language_code: str,
) -> Dict[int, Dict[str, CorpusPresence]]:
    """Load every token's per-corpus measurement in one pass.

    Returns ``{word_token_id: {corpus_name: CorpusPresence}}``. Done as a
    single query rather than per token because the scoring needs every corpus's
    view of a token before it can score any of them.
    """
    sources = [_wordfreq_source(name) for name in corpus_names]
    if not sources:
        return {}

    rows = (
        session.query(
            ExternalLexemeAnnotation.word_token_id,
            ExternalLexemeAnnotation.source,
            ExternalLexemeAnnotation.ordinal_rank,
            ExternalLexemeAnnotation.frequency,
        )
        .join(WordToken, WordToken.id == ExternalLexemeAnnotation.word_token_id)
        .filter(
            ExternalLexemeAnnotation.source.in_(sources),
            WordToken.language_code == language_code,
        )
        .all()
    )

    out: Dict[int, Dict[str, CorpusPresence]] = {}
    for token_id, source, rank, frequency in rows:
        corpus_name = _corpus_from_source(source)
        if corpus_name is None:
            continue
        zipf = zipf_from_frequency(frequency) if frequency is not None else None
        # A source may emit several rows for one token (different pos_hint or
        # sense_hint). They describe the same surface string in the same
        # corpus, so keep the best-attested one rather than counting it twice.
        existing = out.setdefault(token_id, {}).get(corpus_name)
        if existing is not None:
            existing_zipf = existing.zipf if existing.zipf is not None else -math.inf
            candidate_zipf = zipf if zipf is not None else -math.inf
            if candidate_zipf <= existing_zipf:
                continue
        out[token_id][corpus_name] = CorpusPresence(
            corpus_name=corpus_name,
            ordinal_rank=rank,
            frequency=frequency,
            zipf=zipf,
        )
    return out


def _token_texts(session: Session, token_ids: Sequence[int]) -> Dict[int, str]:
    """Map token ids to their surface strings, in batches SQLite will accept."""
    out: Dict[int, str] = {}
    batch_size = 500
    ids = list(token_ids)
    for start in range(0, len(ids), batch_size):
        chunk = ids[start : start + batch_size]
        for token_id, text in (
            session.query(WordToken.id, WordToken.token).filter(WordToken.id.in_(chunk)).all()
        ):
            out[token_id] = text
    return out


def score_corpus_skew(
    session: Session,
    corpus_name: str,
    language_code: str = "en",
    comparison_corpora: Optional[Sequence[str]] = None,
    min_other_corpora: int = 1,
    limit: Optional[int] = None,
) -> List[SkewedWord]:
    """Rank the words most characteristic of ``corpus_name``.

    Args:
        session: Open session.
        corpus_name: The corpus to find characteristic vocabulary for.
        language_code: Token language; the corpora here are all English.
        comparison_corpora: What to compare against. Defaults to every other
            enabled corpus.
        min_other_corpora: Require a token to appear in at least this many
            other corpora before scoring it. The default of 1 excludes only
            corpus-exclusive words (see :func:`exclusive_words`); raising it
            demands a better-established baseline before trusting the delta.
        limit: Truncate to this many results. None returns all.

    Returns:
        Scored words, most skewed toward ``corpus_name`` first.
    """
    enabled = get_enabled_corpus_names()
    if comparison_corpora is None:
        others = [name for name in enabled if name != corpus_name]
    else:
        others = [name for name in comparison_corpora if name != corpus_name]

    presences = _load_presences(session, [corpus_name] + list(others), language_code)

    scored: List[SkewedWord] = []
    for token_id, by_corpus in presences.items():
        here = by_corpus.get(corpus_name)
        if here is None or here.zipf is None:
            continue

        elsewhere = [
            by_corpus[name]
            for name in others
            if name in by_corpus and by_corpus[name].zipf is not None
        ]
        if len(elsewhere) < min_other_corpora:
            continue

        zipfs = [presence.zipf for presence in elsewhere if presence.zipf is not None]
        mean_zipf_elsewhere = sum(zipfs) / len(zipfs)

        other_ranks = [
            float(presence.ordinal_rank)
            for presence in elsewhere
            if presence.ordinal_rank is not None and presence.ordinal_rank > 0
        ]
        mean_rank_elsewhere = sum(other_ranks) / len(other_ranks) if other_ranks else None

        scored.append(
            SkewedWord(
                word_token_id=token_id,
                token="",  # filled in below, once, for the rows that survive
                language_code=language_code,
                corpus_name=corpus_name,
                score=here.zipf - mean_zipf_elsewhere,
                zipf_here=here.zipf,
                mean_zipf_elsewhere=mean_zipf_elsewhere,
                rank_here=here.ordinal_rank,
                mean_rank_elsewhere=mean_rank_elsewhere,
                corpus_count=len([p for p in by_corpus.values() if p.zipf is not None]),
                presences=tuple(
                    by_corpus[name] for name in ([corpus_name] + list(others)) if name in by_corpus
                ),
            )
        )

    scored.sort(key=lambda word: (-word.score, word.word_token_id))
    if limit is not None:
        scored = scored[:limit]

    # Resolve token text only for the rows being returned, rather than for
    # every annotated token in the corpus.
    texts = _token_texts(session, [word.word_token_id for word in scored])
    return [
        SkewedWord(
            word_token_id=word.word_token_id,
            token=texts.get(word.word_token_id, ""),
            language_code=word.language_code,
            corpus_name=word.corpus_name,
            score=word.score,
            zipf_here=word.zipf_here,
            mean_zipf_elsewhere=word.mean_zipf_elsewhere,
            rank_here=word.rank_here,
            mean_rank_elsewhere=word.mean_rank_elsewhere,
            corpus_count=word.corpus_count,
            presences=word.presences,
        )
        for word in scored
    ]


@dataclass(frozen=True)
class ExclusiveWord:
    """A token attested in exactly one corpus, so it cannot be scored."""

    word_token_id: int
    token: str
    corpus_name: str
    ordinal_rank: Optional[int]
    frequency: Optional[float]


def exclusive_words(
    session: Session,
    corpus_name: str,
    language_code: str = "en",
    comparison_corpora: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
) -> List[ExclusiveWord]:
    """Words this corpus attests and no comparison corpus does.

    Reported apart from :func:`score_corpus_skew` because there is no baseline
    to subtract: these are maximally characteristic by definition, and giving
    them a numeric score would invite comparing them against words that do have
    one. Ordered by their rank within this corpus, best first.
    """
    enabled = get_enabled_corpus_names()
    if comparison_corpora is None:
        others = [name for name in enabled if name != corpus_name]
    else:
        others = [name for name in comparison_corpora if name != corpus_name]

    presences = _load_presences(session, [corpus_name] + list(others), language_code)

    found: List[ExclusiveWord] = []
    for token_id, by_corpus in presences.items():
        here = by_corpus.get(corpus_name)
        if here is None:
            continue
        if any(name in by_corpus for name in others):
            continue
        found.append(
            ExclusiveWord(
                word_token_id=token_id,
                token="",
                corpus_name=corpus_name,
                ordinal_rank=here.ordinal_rank,
                frequency=here.frequency,
            )
        )

    found.sort(
        key=lambda word: (
            word.ordinal_rank if word.ordinal_rank is not None else 1 << 30,
            word.word_token_id,
        )
    )
    if limit is not None:
        found = found[:limit]

    texts = _token_texts(session, [word.word_token_id for word in found])
    return [
        ExclusiveWord(
            word_token_id=word.word_token_id,
            token=texts.get(word.word_token_id, ""),
            corpus_name=word.corpus_name,
            ordinal_rank=word.ordinal_rank,
            frequency=word.frequency,
        )
        for word in found
    ]


@dataclass(frozen=True)
class SteadyWord:
    """A token whose Zipf barely moves between corpora.

    The complement of :class:`SkewedWord`: instead of leaning toward one
    corpus, these sit at the same frequency in every corpus that has them.
    ``spread`` (max minus min Zipf) is the readable companion to ``stdev``,
    the way the ranks are to a skew score -- "never further apart than 0.2
    Zipf" is a claim someone can check.
    """

    word_token_id: int
    token: str
    language_code: str
    stdev: float
    spread: float  # max Zipf minus min Zipf
    mean_zipf: float
    min_zipf: float
    max_zipf: float
    corpus_count: int
    lowest_corpus: str
    highest_corpus: str
    presences: Sequence[CorpusPresence] = ()


def score_zipf_steadiness(
    session: Session,
    language_code: str = "en",
    corpora: Optional[Sequence[str]] = None,
    require_all: bool = True,
    min_corpora: Optional[int] = None,
    max_rank: Optional[int] = None,
    limit: Optional[int] = None,
) -> List[SteadyWord]:
    """Rank words by how *little* their Zipf varies across corpora.

    These are the register-neutral words: "for", "on", "after", "through" turn
    up at the same rate in cookbooks, scripture and science writing alike,
    which is exactly what makes them uninformative about genre and useful as a
    core vocabulary.

    Comparing a standard deviation across tokens is only fair when they are
    measured over the same number of corpora. Variance over four points is
    systematically smaller than over six -- in this database the median stdev
    climbs from 0.09 at two corpora to 0.28 at six -- so a mixed ranking puts
    the thinnest evidence on top. ``require_all`` therefore defaults to True,
    and a caller that lowers the bar gets ``corpus_count`` on every row to
    surface the difference rather than hiding it.

    Args:
        session: Open session.
        language_code: Token language.
        corpora: Which corpora to measure across. Defaults to every enabled one.
        require_all: Only score tokens attested in every corpus in ``corpora``.
            Keeps the comparison like-for-like; see above.
        min_corpora: Used when ``require_all`` is False. A token needs at least
            this many corpora to be scored. Defaults to 2, below which a
            standard deviation is not meaningful.
        max_rank: Only consider a corpus's measurement when its rank is at
            least this good. Sharpens the result toward the common core and
            keeps a corpus's long tail from contributing noise.
        limit: Truncate to this many results. None returns all.

    Returns:
        Words with the steadiest Zipf first.
    """
    names = list(corpora) if corpora is not None else get_enabled_corpus_names()
    presences = _load_presences(session, names, language_code)

    if require_all:
        needed = len(names)
    else:
        needed = max(2, min_corpora if min_corpora is not None else 2)

    def _counts(presence: CorpusPresence) -> bool:
        """Whether this corpus's measurement of the token may be used.

        A rank cutoff drops a corpus's long tail: a corpus that ranks the word
        worse than the cutoff is treated as not measuring it here, which can in
        turn drop the token below ``needed``.
        """
        if presence.zipf is None:
            return False
        if max_rank is None:
            return True
        return presence.ordinal_rank is not None and presence.ordinal_rank <= max_rank

    scored: List[SteadyWord] = []
    for token_id, by_corpus in presences.items():
        usable = [
            by_corpus[name] for name in names if name in by_corpus and _counts(by_corpus[name])
        ]
        if len(usable) < needed:
            continue

        zipfs = [presence.zipf for presence in usable if presence.zipf is not None]
        mean_zipf = sum(zipfs) / len(zipfs)
        variance = sum((value - mean_zipf) ** 2 for value in zipfs) / len(zipfs)
        lowest = min(usable, key=lambda presence: presence.zipf or 0.0)
        highest = max(usable, key=lambda presence: presence.zipf or 0.0)

        scored.append(
            SteadyWord(
                word_token_id=token_id,
                token="",
                language_code=language_code,
                stdev=math.sqrt(variance),
                spread=(highest.zipf or 0.0) - (lowest.zipf or 0.0),
                mean_zipf=mean_zipf,
                min_zipf=lowest.zipf or 0.0,
                max_zipf=highest.zipf or 0.0,
                corpus_count=len(usable),
                lowest_corpus=lowest.corpus_name,
                highest_corpus=highest.corpus_name,
                presences=tuple(usable),
            )
        )

    # More corpora first at equal steadiness: agreement across six measurements
    # is a stronger claim than the same figure across two.
    scored.sort(key=lambda word: (word.stdev, -word.corpus_count, word.word_token_id))
    if limit is not None:
        scored = scored[:limit]

    texts = _token_texts(session, [word.word_token_id for word in scored])
    return [
        SteadyWord(
            word_token_id=word.word_token_id,
            token=texts.get(word.word_token_id, ""),
            language_code=word.language_code,
            stdev=word.stdev,
            spread=word.spread,
            mean_zipf=word.mean_zipf,
            min_zipf=word.min_zipf,
            max_zipf=word.max_zipf,
            corpus_count=word.corpus_count,
            lowest_corpus=word.lowest_corpus,
            highest_corpus=word.highest_corpus,
            presences=word.presences,
        )
        for word in scored
    ]


__all__ = [
    "MIN_FREQUENCY",
    "ZIPF_OFFSET",
    "CorpusPresence",
    "ExclusiveWord",
    "SkewedWord",
    "SteadyWord",
    "exclusive_words",
    "score_corpus_skew",
    "score_zipf_steadiness",
    "zipf_from_frequency",
]
