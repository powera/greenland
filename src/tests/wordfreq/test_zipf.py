"""Tests for wordfreq.frequency.zipf — combining per-form ranks into a lexeme rank."""

from __future__ import annotations

import pytest

from wordfreq.frequency.zipf import (
    DEFAULT_ZIPF_EXPONENT,
    MIN_FIT_SAMPLES,
    combine_ranks,
    fit_zipf_exponent,
)


def test_single_rank_round_trips_unchanged() -> None:
    """A lexeme with one ranked form keeps that form's rank exactly.

    This is what makes the combination safe to apply everywhere: the common
    case of a single ranked form must not move a word's rank at all.
    """
    for exponent in (0.8, 1.0, 1.25):
        assert combine_ranks([2302], exponent) == 2302


def test_combining_forms_improves_the_rank() -> None:
    """Two forms make a lexeme more common than either form alone."""
    combined = combine_ranks([2500, 4500], 1.0)
    assert combined is not None
    assert combined < 2500


def test_combination_is_order_independent() -> None:
    assert combine_ranks([4500, 2500], 1.0) == combine_ranks([2500, 4500], 1.0)


def test_reciprocal_sum_at_exponent_one() -> None:
    """s=1 reduces to 1 / sum(1/rank), the classical Zipf case."""
    assert combine_ranks([2500, 4500], 1.0) == round(1 / (1 / 2500 + 1 / 4500))


def test_higher_exponent_gives_less_credit_for_extra_forms() -> None:
    """A steeper curve means a second form adds less than a flat one does."""
    flat = combine_ranks([2500, 4500], 0.9)
    steep = combine_ranks([2500, 4500], 1.3)
    assert flat is not None and steep is not None
    assert flat < steep


def test_no_usable_ranks_returns_none() -> None:
    assert combine_ranks([]) is None
    assert combine_ranks([0, -3]) is None


def test_non_positive_ranks_are_ignored_not_treated_as_common() -> None:
    """A rank of 0 must not read as "the most common word in the corpus"."""
    assert combine_ranks([0, 2302], 1.0) == 2302


def test_result_never_below_one() -> None:
    combined = combine_ranks([1, 1, 1, 1], 1.0)
    assert combined is not None
    assert combined >= 1


def test_fit_recovers_a_known_exponent() -> None:
    """A synthetic pure-Zipf corpus fits back to the exponent it was built with."""
    for true_exponent in (0.85, 1.0, 1.2):
        pairs = [(rank, float(rank) ** -true_exponent) for rank in range(1, 500)]
        fitted = fit_zipf_exponent(pairs)
        assert fitted is not None
        assert fitted == pytest.approx(true_exponent, abs=1e-6)


def test_fit_needs_enough_samples() -> None:
    pairs = [(rank, float(rank) ** -1.0) for rank in range(1, MIN_FIT_SAMPLES)]
    assert fit_zipf_exponent(pairs) is None


def test_fit_skips_unusable_pairs() -> None:
    """Zero and negative values have no logarithm and are dropped, not crashed on."""
    pairs = [(rank, float(rank) ** -1.0) for rank in range(1, 500)]
    pairs += [(0, 5.0), (-1, 5.0), (10, 0.0), (11, -2.0)]
    fitted = fit_zipf_exponent(pairs)
    assert fitted is not None
    assert fitted == pytest.approx(1.0, abs=1e-6)


def test_fit_rejects_an_implausible_exponent() -> None:
    """A curve nothing like Zipf returns None so the caller uses the default."""
    # Frequency rising with rank gives a negative exponent, far outside bounds.
    pairs = [(rank, float(rank) ** 3) for rank in range(1, 500)]
    assert fit_zipf_exponent(pairs) is None


def test_default_exponent_is_the_classical_value() -> None:
    assert DEFAULT_ZIPF_EXPONENT == 1.0
