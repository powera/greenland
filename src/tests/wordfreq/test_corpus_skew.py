"""Tests for per-corpus vocabulary skew scoring."""

from __future__ import annotations

import math
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import Base, ExternalLexemeAnnotation, WordToken
from wordfreq.frequency.corpus_skew import (
    MIN_FREQUENCY,
    ZIPF_OFFSET,
    exclusive_words,
    score_corpus_skew,
    score_zipf_steadiness,
    zipf_from_frequency,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_token(session: Session, token: str, language_code: str = "en") -> WordToken:
    row = WordToken(token=token, language_code=language_code)
    session.add(row)
    session.flush()
    return row


def _annotate(
    session: Session,
    token: WordToken,
    corpus_name: str,
    frequency: Optional[float],
    ordinal_rank: Optional[int] = None,
    pos_hint: Optional[str] = None,
) -> None:
    session.add(
        ExternalLexemeAnnotation(
            word_token_id=token.id,
            source=f"wordfreq_{corpus_name}",
            tier_name=corpus_name,
            ordinal_rank=ordinal_rank,
            frequency=frequency,
            pos_hint=pos_hint,
        )
    )
    session.flush()


def test_zipf_from_frequency_uses_the_per_million_scale() -> None:
    """One occurrence per million is 3.0; ten times that is 4.0."""
    assert zipf_from_frequency(1.0) == ZIPF_OFFSET
    assert zipf_from_frequency(10.0) == ZIPF_OFFSET + 1.0
    assert zipf_from_frequency(1000.0) == ZIPF_OFFSET + 3.0


def test_zipf_rejects_absent_and_negligible_frequencies() -> None:
    """A near-zero frequency is 'not attested', not an enormous negative Zipf."""
    assert zipf_from_frequency(0.0) is None
    assert zipf_from_frequency(-1.0) is None
    assert zipf_from_frequency(MIN_FREQUENCY / 2) is None


def test_score_is_the_zipf_delta_against_the_other_corpora() -> None:
    """A word ten times as common here as elsewhere scores +1.00."""
    session = _make_session()
    try:
        token = _add_token(session, "sugar")
        _annotate(session, token, "cooking", frequency=1000.0, ordinal_rank=26)
        _annotate(session, token, "19th_books", frequency=100.0, ordinal_rank=2623)

        results = score_corpus_skew(session, "cooking", comparison_corpora=["19th_books"])
        assert len(results) == 1
        word = results[0]
        assert word.token == "sugar"
        assert math.isclose(word.score, 1.0)
        assert word.rank_here == 26
        assert word.mean_rank_elsewhere == 2623.0
        assert word.corpus_count == 2
    finally:
        session.close()


def test_results_are_sorted_by_score_descending() -> None:
    session = _make_session()
    try:
        mild = _add_token(session, "water")
        sharp = _add_token(session, "simmer")
        _annotate(session, mild, "cooking", frequency=200.0, ordinal_rank=100)
        _annotate(session, mild, "19th_books", frequency=100.0, ordinal_rank=400)
        _annotate(session, sharp, "cooking", frequency=1000.0, ordinal_rank=30)
        _annotate(session, sharp, "19th_books", frequency=1.0, ordinal_rank=6000)

        results = score_corpus_skew(session, "cooking", comparison_corpora=["19th_books"])
        assert [word.token for word in results] == ["simmer", "water"]
        assert results[0].score > results[1].score
    finally:
        session.close()


def test_a_word_common_everywhere_scores_near_zero() -> None:
    """ "will" is frequent in every corpus, so it is characteristic of none."""
    session = _make_session()
    try:
        token = _add_token(session, "will")
        _annotate(session, token, "cooking", frequency=3000.0, ordinal_rank=46)
        _annotate(session, token, "19th_books", frequency=3000.0, ordinal_rank=59)

        results = score_corpus_skew(session, "cooking", comparison_corpora=["19th_books"])
        assert math.isclose(results[0].score, 0.0, abs_tol=1e-9)
    finally:
        session.close()


def test_mean_is_taken_over_every_other_attesting_corpus() -> None:
    session = _make_session()
    try:
        token = _add_token(session, "sugar")
        _annotate(session, token, "cooking", frequency=1000.0, ordinal_rank=26)
        _annotate(session, token, "19th_books", frequency=10.0, ordinal_rank=3000)
        _annotate(session, token, "wiki_society", frequency=1000.0, ordinal_rank=200)

        results = score_corpus_skew(
            session, "cooking", comparison_corpora=["19th_books", "wiki_society"]
        )
        word = results[0]
        # Zipf elsewhere is mean(4.0, 6.0) = 5.0 against 6.0 here.
        assert math.isclose(word.score, 1.0)
        assert word.mean_rank_elsewhere == 1600.0
    finally:
        session.close()


def test_exclusive_words_are_not_scored() -> None:
    """A word no other corpus attests has no baseline, so it is left out."""
    session = _make_session()
    try:
        only_here = _add_token(session, "ramekin")
        shared = _add_token(session, "sugar")
        _annotate(session, only_here, "cooking", frequency=50.0, ordinal_rank=800)
        _annotate(session, shared, "cooking", frequency=1000.0, ordinal_rank=26)
        _annotate(session, shared, "19th_books", frequency=100.0, ordinal_rank=2623)

        scored = score_corpus_skew(session, "cooking", comparison_corpora=["19th_books"])
        assert [word.token for word in scored] == ["sugar"]

        found = exclusive_words(session, "cooking", comparison_corpora=["19th_books"])
        assert [word.token for word in found] == ["ramekin"]
        assert found[0].ordinal_rank == 800
    finally:
        session.close()


def test_min_other_corpora_demands_a_broader_baseline() -> None:
    session = _make_session()
    try:
        thin = _add_token(session, "thin")
        broad = _add_token(session, "broad")
        _annotate(session, thin, "cooking", frequency=1000.0, ordinal_rank=10)
        _annotate(session, thin, "19th_books", frequency=100.0, ordinal_rank=2000)
        _annotate(session, broad, "cooking", frequency=1000.0, ordinal_rank=11)
        _annotate(session, broad, "19th_books", frequency=100.0, ordinal_rank=2100)
        _annotate(session, broad, "wiki_society", frequency=100.0, ordinal_rank=2200)

        comparison = ["19th_books", "wiki_society"]
        loose = score_corpus_skew(
            session, "cooking", comparison_corpora=comparison, min_other_corpora=1
        )
        assert {word.token for word in loose} == {"thin", "broad"}

        strict = score_corpus_skew(
            session, "cooking", comparison_corpora=comparison, min_other_corpora=2
        )
        assert [word.token for word in strict] == ["broad"]
    finally:
        session.close()


def test_limit_truncates_after_sorting() -> None:
    session = _make_session()
    try:
        for index, (text, frequency) in enumerate([("a", 10.0), ("b", 100.0), ("c", 1000.0)]):
            token = _add_token(session, text)
            _annotate(session, token, "cooking", frequency=frequency, ordinal_rank=index + 1)
            _annotate(session, token, "19th_books", frequency=10.0, ordinal_rank=500)

        results = score_corpus_skew(session, "cooking", comparison_corpora=["19th_books"], limit=2)
        # The two best, not the first two encountered.
        assert [word.token for word in results] == ["c", "b"]
    finally:
        session.close()


def test_duplicate_source_rows_are_not_double_counted() -> None:
    """A corpus emitting several rows for one token still measures it once."""
    session = _make_session()
    try:
        token = _add_token(session, "top")
        _annotate(session, token, "cooking", frequency=1000.0, ordinal_rank=134, pos_hint="n")
        _annotate(session, token, "cooking", frequency=10.0, ordinal_rank=900, pos_hint="v")
        _annotate(session, token, "19th_books", frequency=100.0, ordinal_rank=675)

        results = score_corpus_skew(session, "cooking", comparison_corpora=["19th_books"])
        assert len(results) == 1
        # The better-attested of the two rows is kept.
        assert results[0].rank_here == 134
        assert math.isclose(results[0].score, 1.0)
        assert results[0].corpus_count == 2
    finally:
        session.close()


def test_rank_ratio_reports_the_readable_comparison() -> None:
    session = _make_session()
    try:
        token = _add_token(session, "sauce")
        _annotate(session, token, "cooking", frequency=1000.0, ordinal_rank=36)
        _annotate(session, token, "19th_books", frequency=10.0, ordinal_rank=7200)

        word = score_corpus_skew(session, "cooking", comparison_corpora=["19th_books"])[0]
        assert word.rank_ratio == 200.0
    finally:
        session.close()


def test_rank_ratio_is_none_without_ranks() -> None:
    """A frequency-only corpus still scores; only the display ratio is absent."""
    session = _make_session()
    try:
        token = _add_token(session, "sauce")
        _annotate(session, token, "cooking", frequency=1000.0, ordinal_rank=None)
        _annotate(session, token, "19th_books", frequency=100.0, ordinal_rank=None)

        word = score_corpus_skew(session, "cooking", comparison_corpora=["19th_books"])[0]
        assert word.rank_ratio is None
        assert word.mean_rank_elsewhere is None
        assert math.isclose(word.score, 1.0)
    finally:
        session.close()


def test_scoring_is_scoped_to_one_language() -> None:
    session = _make_session()
    try:
        english = _add_token(session, "sauce", language_code="en")
        other = _add_token(session, "sauce", language_code="fr")
        for token in (english, other):
            _annotate(session, token, "cooking", frequency=1000.0, ordinal_rank=36)
            _annotate(session, token, "19th_books", frequency=100.0, ordinal_rank=7200)

        results = score_corpus_skew(
            session, "cooking", language_code="en", comparison_corpora=["19th_books"]
        )
        assert len(results) == 1
        assert results[0].word_token_id == english.id
    finally:
        session.close()


def test_unattested_frequency_is_ignored_rather_than_scored() -> None:
    """A row with no frequency cannot be placed on the Zipf scale."""
    session = _make_session()
    try:
        token = _add_token(session, "sauce")
        _annotate(session, token, "cooking", frequency=None, ordinal_rank=36)
        _annotate(session, token, "19th_books", frequency=100.0, ordinal_rank=7200)

        assert score_corpus_skew(session, "cooking", comparison_corpora=["19th_books"]) == []
    finally:
        session.close()


# --- Zipf steadiness ---------------------------------------------------------


def test_a_word_at_the_same_zipf_everywhere_has_zero_deviation() -> None:
    """The ideal register-neutral word: identical frequency in every corpus."""
    session = _make_session()
    try:
        token = _add_token(session, "for")
        for corpus in ("cooking", "19th_books", "wiki_society"):
            _annotate(session, token, corpus, frequency=1000.0, ordinal_rank=10)

        results = score_zipf_steadiness(session, corpora=["cooking", "19th_books", "wiki_society"])
        assert len(results) == 1
        word = results[0]
        assert word.token == "for"
        assert word.stdev == 0.0
        assert word.spread == 0.0
        assert word.corpus_count == 3
    finally:
        session.close()


def test_steadier_words_sort_first() -> None:
    session = _make_session()
    try:
        steady = _add_token(session, "through")
        swingy = _add_token(session, "salt")
        for corpus in ("cooking", "19th_books"):
            _annotate(session, steady, corpus, frequency=1000.0, ordinal_rank=10)
        _annotate(session, swingy, "cooking", frequency=10000.0, ordinal_rank=5)
        _annotate(session, swingy, "19th_books", frequency=10.0, ordinal_rank=3000)

        results = score_zipf_steadiness(session, corpora=["cooking", "19th_books"])
        assert [word.token for word in results] == ["through", "salt"]
        assert results[0].stdev < results[1].stdev
    finally:
        session.close()


def test_spread_reports_the_extremes_and_names_them() -> None:
    """Spread is max minus min Zipf, with the corpora at each end labelled."""
    session = _make_session()
    try:
        token = _add_token(session, "wine")
        _annotate(session, token, "cooking", frequency=10000.0, ordinal_rank=5)
        _annotate(session, token, "19th_books", frequency=1000.0, ordinal_rank=50)
        _annotate(session, token, "wiki_society", frequency=100.0, ordinal_rank=500)

        word = score_zipf_steadiness(session, corpora=["cooking", "19th_books", "wiki_society"])[0]
        # Zipf values are 7.0, 6.0, 5.0.
        assert math.isclose(word.spread, 2.0)
        assert math.isclose(word.mean_zipf, 6.0)
        assert word.lowest_corpus == "wiki_society"
        assert word.highest_corpus == "cooking"
        assert math.isclose(word.min_zipf, 5.0)
        assert math.isclose(word.max_zipf, 7.0)
    finally:
        session.close()


def test_require_all_excludes_partly_attested_words() -> None:
    """A word missing from one corpus is not comparable to one present in all."""
    session = _make_session()
    try:
        everywhere = _add_token(session, "for")
        partial = _add_token(session, "shalt")
        for corpus in ("cooking", "19th_books", "religious_translated"):
            _annotate(session, everywhere, corpus, frequency=1000.0, ordinal_rank=10)
        # Absent from cooking, exactly like an archaic form.
        _annotate(session, partial, "19th_books", frequency=1000.0, ordinal_rank=10)
        _annotate(session, partial, "religious_translated", frequency=1000.0, ordinal_rank=10)

        corpora = ["cooking", "19th_books", "religious_translated"]
        strict = score_zipf_steadiness(session, corpora=corpora, require_all=True)
        assert [word.token for word in strict] == ["for"]

        loose = score_zipf_steadiness(session, corpora=corpora, require_all=False)
        assert {word.token for word in loose} == {"for", "shalt"}
    finally:
        session.close()


def test_min_corpora_needs_at_least_two_measurements() -> None:
    """One corpus has no variance to speak of, so it is never scored."""
    session = _make_session()
    try:
        lonely = _add_token(session, "ramekin")
        _annotate(session, lonely, "cooking", frequency=1000.0, ordinal_rank=10)

        corpora = ["cooking", "19th_books"]
        assert score_zipf_steadiness(session, corpora=corpora, require_all=False) == []
        # Even asking for a single corpus does not lower the floor below two.
        assert (
            score_zipf_steadiness(session, corpora=corpora, require_all=False, min_corpora=1) == []
        )
    finally:
        session.close()


def test_max_rank_drops_a_corpus_long_tail() -> None:
    """A corpus ranking the word worse than the cutoff stops measuring it."""
    session = _make_session()
    try:
        token = _add_token(session, "sugar")
        _annotate(session, token, "cooking", frequency=1000.0, ordinal_rank=26)
        _annotate(session, token, "19th_books", frequency=1000.0, ordinal_rank=2623)

        corpora = ["cooking", "19th_books"]
        # Without a cutoff both corpora count, so the word is scored.
        assert len(score_zipf_steadiness(session, corpora=corpora)) == 1
        # With one, the 19th_books measurement is dropped, leaving too few.
        assert score_zipf_steadiness(session, corpora=corpora, max_rank=2000) == []
    finally:
        session.close()


def test_more_corpora_wins_a_tie_on_steadiness() -> None:
    """Equal deviation across six beats the same figure across two."""
    session = _make_session()
    try:
        broad = _add_token(session, "broad")
        thin = _add_token(session, "thin")
        for corpus in ("cooking", "19th_books", "wiki_society"):
            _annotate(session, broad, corpus, frequency=1000.0, ordinal_rank=10)
        for corpus in ("cooking", "19th_books"):
            _annotate(session, thin, corpus, frequency=1000.0, ordinal_rank=10)

        results = score_zipf_steadiness(
            session,
            corpora=["cooking", "19th_books", "wiki_society"],
            require_all=False,
        )
        assert [word.stdev for word in results] == [0.0, 0.0]
        assert [word.token for word in results] == ["broad", "thin"]
    finally:
        session.close()


def test_steadiness_limit_truncates_after_sorting() -> None:
    session = _make_session()
    try:
        for text, other_frequency in [("a", 1000.0), ("b", 2000.0), ("c", 8000.0)]:
            token = _add_token(session, text)
            _annotate(session, token, "cooking", frequency=1000.0, ordinal_rank=10)
            _annotate(session, token, "19th_books", frequency=other_frequency, ordinal_rank=10)

        results = score_zipf_steadiness(session, corpora=["cooking", "19th_books"], limit=2)
        assert [word.token for word in results] == ["a", "b"]
    finally:
        session.close()


def test_steadiness_is_scoped_to_one_language() -> None:
    session = _make_session()
    try:
        english = _add_token(session, "for", language_code="en")
        other = _add_token(session, "for", language_code="fr")
        for token in (english, other):
            for corpus in ("cooking", "19th_books"):
                _annotate(session, token, corpus, frequency=1000.0, ordinal_rank=10)

        results = score_zipf_steadiness(
            session, language_code="en", corpora=["cooking", "19th_books"]
        )
        assert len(results) == 1
        assert results[0].word_token_id == english.id
    finally:
        session.close()
