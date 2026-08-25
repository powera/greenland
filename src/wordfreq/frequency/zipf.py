"""Combine a lexeme's per-form corpus ranks into one rank for that lexeme.

A corpus file gives a rank to every *surface form* it saw: ``wiki_vital`` ranks
"block" 2500 and "blocks" 4500 separately.  What a lemma needs is a single rank
for the lexeme those forms belong to, and that rank should be better than
either input -- a word spelled two moderately common ways is a more common word
than either spelling alone suggests.

Ranks are not additive, so they cannot simply be averaged.  Frequencies are.
Zipf's law relates the two::

    frequency  proportional to  rank ** -s

so a lexeme's rank follows from converting each form's rank to an implied
frequency, adding those, and converting back::

    lemma_rank = (sum_i rank_i ** -s) ** (-1/s)

With ``s = 1`` this is the reciprocal sum.  The exponent is fitted per corpus
rather than assumed, because the corpora here disagree about it: the Gutenberg
book corpora sit near 1.2 while ``wiki_vital`` is near 0.96, and using 1.0
everywhere would misprice both.  See :func:`fit_zipf_exponent`.

Two properties make this safe to use in place of a global ordering:

* A single form round-trips exactly -- a lexeme with one form keeps that form's
  rank, unchanged.
* The result depends only on the lexeme's own forms.  Nothing about any other
  lemma enters, so one lemma can be rescored on its own without recomputing
  the database.  The previous implementation derived a rank by sorting every
  lemma's summed frequency and taking each one's position in that ordering,
  which made a single-word update cost a full pass.

The output is a rank-like number, not an index into an ordering: two lexemes
may legitimately land on the same value, and values may be skipped.
"""

from __future__ import annotations

import logging
import math
from typing import Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

#: Exponent used when a corpus has too few (rank, frequency) pairs to fit one.
#: 1.0 is the classical Zipf value and makes the combination a reciprocal sum.
DEFAULT_ZIPF_EXPONENT: float = 1.0

#: Minimum number of (rank, frequency) pairs needed before fitting is trusted.
MIN_FIT_SAMPLES: int = 50

#: Bounds on a fitted exponent.  Real corpora land near 0.9-1.3; a value far
#: outside that means the fit found noise rather than a Zipf curve, and the
#: default is safer than propagating it into every rank.
MIN_ZIPF_EXPONENT: float = 0.5
MAX_ZIPF_EXPONENT: float = 2.0


def fit_zipf_exponent(
    rank_frequency_pairs: Iterable[Tuple[int, float]],
) -> Optional[float]:
    """Fit ``s`` in ``frequency ~ rank ** -s`` by least squares in log-log space.

    The corpus annotations already carry both a rank and a frequency for every
    token, so the exponent is measured from the corpus itself rather than
    assumed.

    Args:
        rank_frequency_pairs: ``(ordinal_rank, frequency)`` from one corpus.
            Pairs with a non-positive rank or frequency are dropped, since
            their logarithm is undefined.

    Returns:
        The fitted exponent, or None when there are too few usable pairs or
        the fit falls outside :data:`MIN_ZIPF_EXPONENT`..:data:`MAX_ZIPF_EXPONENT`.
        Callers should fall back to :data:`DEFAULT_ZIPF_EXPONENT`.
    """
    log_ranks: List[float] = []
    log_frequencies: List[float] = []
    for rank, frequency in rank_frequency_pairs:
        if rank is None or frequency is None or rank <= 0 or frequency <= 0:
            continue
        log_ranks.append(math.log(rank))
        log_frequencies.append(math.log(frequency))

    count = len(log_ranks)
    if count < MIN_FIT_SAMPLES:
        return None

    mean_x = sum(log_ranks) / count
    mean_y = sum(log_frequencies) / count
    variance_x = sum((x - mean_x) ** 2 for x in log_ranks)
    if variance_x <= 0.0:
        return None

    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(log_ranks, log_frequencies))
    # The slope of log(frequency) against log(rank) is -s.
    exponent = -covariance / variance_x

    if not MIN_ZIPF_EXPONENT <= exponent <= MAX_ZIPF_EXPONENT:
        logger.warning(
            "Fitted Zipf exponent %.3f outside [%.1f, %.1f]; using the default instead",
            exponent,
            MIN_ZIPF_EXPONENT,
            MAX_ZIPF_EXPONENT,
        )
        return None
    return exponent


def combine_ranks(ranks: Sequence[int], exponent: float = DEFAULT_ZIPF_EXPONENT) -> Optional[int]:
    """Combine per-form ranks into one rank for the lexeme they belong to.

    Args:
        ranks: Each form's rank in a single corpus.  Non-positive ranks are
            dropped rather than treated as very common.
        exponent: The corpus's Zipf exponent, from :func:`fit_zipf_exponent`.

    Returns:
        The combined rank, rounded to an integer and never below 1, or None
        when no usable rank was supplied.  A single rank is returned unchanged.
    """
    if exponent <= 0.0:
        exponent = DEFAULT_ZIPF_EXPONENT

    implied_frequency = 0.0
    for rank in ranks:
        if rank is None or rank <= 0:
            continue
        implied_frequency += float(rank) ** -exponent

    if implied_frequency <= 0.0:
        return None
    return max(1, int(round(implied_frequency ** (-1.0 / exponent))))


__all__ = [
    "DEFAULT_ZIPF_EXPONENT",
    "MAX_ZIPF_EXPONENT",
    "MIN_FIT_SAMPLES",
    "MIN_ZIPF_EXPONENT",
    "combine_ranks",
    "fit_zipf_exponent",
]
