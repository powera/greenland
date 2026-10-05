"""Tests for per-level corpus profiles."""

from __future__ import annotations

from typing import Dict, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import (
    SENSE_PROMINENCE_RARE,
    SENSE_PROMINENCE_VERY_COMMON,
    Base,
    DerivativeForm,
    ExternalLexemeAnnotation,
    Lemma,
    WordToken,
)
from wordfreq.frequency.level_profile import (
    GENERAL,
    build_level_profiles,
    choose_top_corpus,
    get_corpus_zipf_floors,
    rank_levels_for_corpus,
    skew_from_zipfs,
)

CORPORA = ["arts", "cooking", "books"]


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _token(session: Session, text: str, frequencies: Dict[str, float]) -> WordToken:
    token = WordToken(token=text, language_code="en")
    session.add(token)
    session.flush()
    for corpus_name, frequency in frequencies.items():
        session.add(
            ExternalLexemeAnnotation(
                word_token_id=token.id,
                source=f"wordfreq_{corpus_name}",
                tier_name=corpus_name,
                frequency=frequency,
            )
        )
    session.flush()
    return token


def _lemma(
    session: Session,
    text: str,
    level: Optional[int],
    token: Optional[WordToken],
    sense_prominence: Optional[str] = None,
    disambiguation: Optional[str] = None,
) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=text,
        pos_type="noun",
        difficulty_level=level,
        sense_prominence=sense_prominence,
        disambiguation=disambiguation,
    )
    session.add(lemma)
    session.flush()
    session.add(
        DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text=text,
            word_token_id=token.id if token is not None else None,
            language_code="en",
            grammatical_form="singular",
            is_base_form=True,
        )
    )
    session.flush()
    return lemma


def _floor_tokens(session: Session) -> None:
    """Give every corpus a rare word, so each has a floor of Zipf 3.0 (1 per million)."""
    _token(session, "zzrare", {name: 1.0 for name in CORPORA})


def test_skew_is_zipf_minus_mean_of_the_others() -> None:
    skew = skew_from_zipfs({"a": 5.0, "b": 3.0, "c": 4.0})
    assert skew["a"] == pytest.approx(1.5)
    assert skew["b"] == pytest.approx(-1.5)
    assert skew["c"] == pytest.approx(0.0)


def test_skew_with_one_corpus_has_no_elsewhere() -> None:
    assert skew_from_zipfs({"a": 5.0}) == {"a": 0.0}


def test_choose_top_corpus_falls_back_to_general_under_threshold() -> None:
    assert choose_top_corpus({"a": 0.2, "b": -0.2}, 0.5) == (GENERAL, 0.2)
    assert choose_top_corpus({"a": 0.9, "b": -0.9}, 0.5) == ("a", 0.9)


def test_corpus_floor_is_the_rarest_listed_form() -> None:
    session = _make_session()
    _token(session, "common", {"arts": 1000.0})
    _token(session, "rare", {"arts": 10.0})
    floors = get_corpus_zipf_floors(session, ["arts", "empty"])
    assert floors["arts"] == pytest.approx(4.0)
    assert floors["empty"] < 0.0


def test_levels_profile_by_top_corpus() -> None:
    session = _make_session()
    _floor_tokens(session)
    # Level 330: arts words.  Level 105: cooking words plus one general word.
    _lemma(session, "fresco", 330, _token(session, "fresco", {"arts": 100.0, "books": 1.0}))
    _lemma(session, "sonata", 330, _token(session, "sonata", {"arts": 200.0}))
    _lemma(session, "simmer", 105, _token(session, "simmer", {"cooking": 500.0, "books": 2.0}))
    _lemma(
        session,
        "the",
        105,
        _token(session, "the", {"arts": 50000.0, "cooking": 50000.0, "books": 50000.0}),
    )
    # Ignored: no level, excluded level.
    _lemma(session, "unlevelled", None, _token(session, "unlevelled", {"arts": 100.0}))
    _lemma(session, "excluded", -1, _token(session, "excluded", {"arts": 100.0}))
    # Counted as unattested: no corpus lists it.
    _lemma(session, "ice cream", 105, None)
    session.commit()

    level_profiles, lemma_profiles = build_level_profiles(session, corpus_names=CORPORA)

    assert sorted(level_profiles) == [105, 330]
    arts_level = level_profiles[330]
    assert arts_level.lemma_count == 2
    assert arts_level.share("arts") == pytest.approx(1.0)

    cooking_level = level_profiles[105]
    assert cooking_level.lemma_count == 2
    assert cooking_level.unattested_count == 1
    assert cooking_level.share("cooking") == pytest.approx(0.5)
    assert cooking_level.share(GENERAL) == pytest.approx(0.5)

    by_text = {profile.lemma_text: profile for profile in lemma_profiles}
    # Absent from cooking and books puts sonata at their floors, so it skews to arts.
    assert by_text["sonata"].top_corpus == "arts"
    assert by_text["sonata"].attested_corpora == ("arts",)
    assert by_text["the"].top_corpus == GENERAL

    candidates = rank_levels_for_corpus(level_profiles, "arts", min_lemmas=1)
    assert [candidate.level for candidate in candidates] == [330]
    assert candidates[0].lift == pytest.approx(2.0)  # 100% here vs 50% (2 of 4) overall


def test_rank_levels_for_corpus_orders_by_share_and_skips_small_levels() -> None:
    session = _make_session()
    _floor_tokens(session)
    for index in range(3):
        _lemma(session, f"art{index}", 330, _token(session, f"art{index}", {"arts": 100.0}))
    _lemma(session, "art3", 335, _token(session, "art3", {"arts": 100.0}))
    for index in range(2):
        _lemma(session, f"cook{index}", 335, _token(session, f"cook{index}", {"cooking": 100.0}))
    _lemma(session, "art4", 7, _token(session, "art4", {"arts": 100.0}))
    session.commit()

    level_profiles, _ = build_level_profiles(session, corpus_names=CORPORA)
    candidates = rank_levels_for_corpus(level_profiles, "arts", min_lemmas=2)
    assert [(candidate.level, candidate.count) for candidate in candidates] == [
        (330, 3),
        (335, 1),
    ]


def test_contested_spelling_profiles_each_sense_by_its_share() -> None:
    """A rare sense of a shared spelling falls to the floor where its share is tiny."""
    session = _make_session()
    _floor_tokens(session)
    tonic = _token(session, "tonic", {"arts": 30.0, "cooking": 30.0, "books": 30.0})
    _lemma(session, "tonic", 330, tonic, SENSE_PROMINENCE_VERY_COMMON, "music")
    _lemma(session, "tonic", 105, tonic, SENSE_PROMINENCE_RARE, "drink")
    session.commit()

    _, lemma_profiles = build_level_profiles(session, corpus_names=CORPORA)
    zipfs = {profile.disambiguation: profile.zipf_by_corpus["arts"] for profile in lemma_profiles}
    assert zipfs["music"] > zipfs["drink"]


def test_levels_filter_and_limit() -> None:
    session = _make_session()
    _floor_tokens(session)
    _lemma(session, "fresco", 330, _token(session, "fresco", {"arts": 100.0}))
    _lemma(session, "simmer", 105, _token(session, "simmer", {"cooking": 100.0}))
    session.commit()

    level_profiles, _ = build_level_profiles(session, levels=[330], corpus_names=CORPORA)
    assert list(level_profiles) == [330]

    level_profiles, lemma_profiles = build_level_profiles(session, limit=1, corpus_names=CORPORA)
    assert len(lemma_profiles) == 1
