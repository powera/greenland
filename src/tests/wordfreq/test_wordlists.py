"""Tests for turning corpus rankings into learnable wordlists."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import Base, ExternalLexemeAnnotation, WordToken
from wordfreq.frequency.wordlists import (
    MIN_TOKEN_LENGTH,
    corpus_exclusive_words,
    filter_function_words,
    high_skew_words,
    is_probable_fragment,
    is_probable_proper_noun,
)

CORPORA = ["cooking", "19th_books", "wiki_linguistics"]


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
) -> None:
    session.add(
        ExternalLexemeAnnotation(
            word_token_id=token.id,
            source=f"wordfreq_{corpus_name}",
            tier_name=corpus_name,
            ordinal_rank=ordinal_rank,
            frequency=frequency,
        )
    )
    session.flush()


# ---------- function-word filtering ----------


def test_filter_function_words_keeps_content_words() -> None:
    """The closed-class items go; the vocabulary stays."""
    kept = filter_function_words(["the", "morpheme", "of", "diacritic", "which"])
    assert kept == ["morpheme", "diacritic"]


def test_filter_function_words_preserves_input_order() -> None:
    kept = filter_function_words(["vowel", "and", "consonant", "but", "syllable"])
    assert kept == ["vowel", "consonant", "syllable"]


def test_filter_function_words_checks_all_four_tiers() -> None:
    """Pronouns and prepositions are dropped, not only articles."""
    kept = filter_function_words(["she", "under", "whom", "phoneme"])
    assert kept == ["phoneme"]


def test_unregistered_language_keeps_the_list_whole_by_default() -> None:
    """No inventory means no filtering, rather than a silently empty result."""
    words = ["the", "vowel"]
    assert filter_function_words(words, language_code="xx") == words


def test_unregistered_language_can_raise_instead() -> None:
    """A caller that must not silently skip filtering can opt into an error."""
    try:
        filter_function_words(["the"], language_code="xx", keep_unknown_language=False)
    except ValueError as error:
        assert "xx" in str(error)
    else:
        raise AssertionError("expected ValueError for an unregistered language")


def test_filtering_is_per_language() -> None:
    """'die' is a German article and an English verb."""
    assert filter_function_words(["die"], language_code="de") == []
    assert filter_function_words(["die"], language_code="en") == ["die"]


# ---------- token heuristics ----------


def test_proper_noun_heuristic_reads_the_stored_capital() -> None:
    assert is_probable_proper_noun("River")
    assert not is_probable_proper_noun("river")
    assert not is_probable_proper_noun("")


def test_fragment_heuristic_catches_structural_debris() -> None:
    """Digits, underscores and vowelless tokens are not words."""
    assert is_probable_fragment("www")
    assert is_probable_fragment("x9")
    assert is_probable_fragment("a_b")
    assert not is_probable_fragment("vowel")
    assert not is_probable_fragment("syzygy")  # 'y' counts as a vowel


# ---------- high_skew_words ----------


def test_high_skew_drops_function_words_from_the_ranking() -> None:
    """A function word that skews hard is still not vocabulary."""
    session = _make_session()
    try:
        content = _add_token(session, "phoneme")
        _annotate(session, content, "wiki_linguistics", frequency=1000.0, ordinal_rank=10)
        _annotate(session, content, "cooking", frequency=1.0, ordinal_rank=900)

        grammatical = _add_token(session, "whom")
        _annotate(session, grammatical, "wiki_linguistics", frequency=2000.0, ordinal_rank=5)
        _annotate(session, grammatical, "cooking", frequency=1.0, ordinal_rank=950)

        results = high_skew_words(session, "wiki_linguistics", comparison_corpora=CORPORA)
        assert [word.token for word in results] == ["phoneme"]
    finally:
        session.close()


def test_high_skew_drops_proper_nouns_and_short_tokens() -> None:
    session = _make_session()
    try:
        for token in ("Devanagari", "ox", "allophone"):
            row = _add_token(session, token)
            _annotate(session, row, "wiki_linguistics", frequency=500.0, ordinal_rank=20)
            _annotate(session, row, "cooking", frequency=1.0, ordinal_rank=900)

        results = high_skew_words(session, "wiki_linguistics", comparison_corpora=CORPORA)
        assert [word.token for word in results] == ["allophone"]
    finally:
        session.close()


def test_high_skew_filters_can_be_turned_off() -> None:
    """The cleanup is a default, not a policy the caller cannot escape."""
    session = _make_session()
    try:
        row = _add_token(session, "Devanagari")
        _annotate(session, row, "wiki_linguistics", frequency=500.0, ordinal_rank=20)
        _annotate(session, row, "cooking", frequency=1.0, ordinal_rank=900)

        results = high_skew_words(
            session,
            "wiki_linguistics",
            comparison_corpora=CORPORA,
            drop_proper_nouns=False,
        )
        assert [word.token for word in results] == ["Devanagari"]
    finally:
        session.close()


def test_high_skew_limit_counts_words_kept_not_rows_scanned() -> None:
    """Asking for two usable words returns two, not two rows of which one is 'the'."""
    session = _make_session()
    try:
        # "the" outscores both content words, so an unfiltered limit=2 would
        # spend one of its two slots on it.
        for token, frequency in (("the", 9000.0), ("morpheme", 800.0), ("diacritic", 700.0)):
            row = _add_token(session, token)
            _annotate(session, row, "wiki_linguistics", frequency=frequency, ordinal_rank=5)
            _annotate(session, row, "cooking", frequency=1.0, ordinal_rank=900)

        results = high_skew_words(session, "wiki_linguistics", comparison_corpora=CORPORA, limit=2)
        assert [word.token for word in results] == ["morpheme", "diacritic"]
    finally:
        session.close()


def test_high_skew_min_score_filters_on_the_zipf_delta() -> None:
    session = _make_session()
    try:
        strong = _add_token(session, "allophone")
        _annotate(session, strong, "wiki_linguistics", frequency=1000.0, ordinal_rank=10)
        _annotate(session, strong, "cooking", frequency=1.0, ordinal_rank=900)

        weak = _add_token(session, "pattern")
        _annotate(session, weak, "wiki_linguistics", frequency=12.0, ordinal_rank=400)
        _annotate(session, weak, "cooking", frequency=10.0, ordinal_rank=420)

        results = high_skew_words(
            session, "wiki_linguistics", comparison_corpora=CORPORA, min_score=1.0
        )
        assert [word.token for word in results] == ["allophone"]
    finally:
        session.close()


# ---------- corpus_exclusive_words ----------


def test_exclusive_words_are_cleaned_the_same_way() -> None:
    """Exclusivity attracts proper nouns and fragments, so cleanup matters more."""
    session = _make_session()
    try:
        for token in ("Rongorongo", "www", "abugida"):
            row = _add_token(session, token)
            _annotate(session, row, "wiki_linguistics", frequency=50.0, ordinal_rank=100)

        shared = _add_token(session, "language")
        _annotate(session, shared, "wiki_linguistics", frequency=900.0, ordinal_rank=3)
        _annotate(session, shared, "cooking", frequency=20.0, ordinal_rank=300)

        results = corpus_exclusive_words(session, "wiki_linguistics", comparison_corpora=CORPORA)
        assert [word.token for word in results] == ["abugida"]
    finally:
        session.close()


def test_exclusive_words_max_rank_trims_the_tail() -> None:
    """Deep in the tail an exclusive word may be a typo rather than vocabulary."""
    session = _make_session()
    try:
        near = _add_token(session, "abugida")
        _annotate(session, near, "wiki_linguistics", frequency=50.0, ordinal_rank=100)
        far = _add_token(session, "reduplicative")
        _annotate(session, far, "wiki_linguistics", frequency=1.0, ordinal_rank=8000)

        results = corpus_exclusive_words(
            session, "wiki_linguistics", comparison_corpora=CORPORA, max_rank=1000
        )
        assert [word.token for word in results] == ["abugida"]
    finally:
        session.close()


def test_min_token_length_default_is_applied() -> None:
    """The module constant is the default, so a caller sees one rule, not two."""
    session = _make_session()
    try:
        short = _add_token(session, "a" * (MIN_TOKEN_LENGTH - 1))
        _annotate(session, short, "wiki_linguistics", frequency=50.0, ordinal_rank=10)
        long_enough = _add_token(session, "a" * MIN_TOKEN_LENGTH)
        _annotate(session, long_enough, "wiki_linguistics", frequency=50.0, ordinal_rank=11)

        results = corpus_exclusive_words(session, "wiki_linguistics", comparison_corpora=CORPORA)
        assert [word.token for word in results] == ["a" * MIN_TOKEN_LENGTH]
    finally:
        session.close()
