"""Tests for dialog vocabulary coverage.

The classification these tests pin is what the whole review flow rests on:
which words are already vocabulary, which are names, and which are genuinely
missing and worth staging for import. Two distinctions get particular
attention, because getting either wrong makes the report useless:

* a name must not be swallowed by a same-spelled lemma ("Rose"/"rose");
* a function word we happen not to have as a lemma is not a missing dictionary
  word, and must not be offered for staging.
"""

from __future__ import annotations

from typing import Iterator, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sentences.dialog_coverage import (
    STATUS_ABOVE_LEVEL,
    STATUS_GRAMMATICAL,
    STATUS_KNOWN,
    STATUS_MISSING,
    STATUS_NAME,
    analyze_line,
    analyze_lines,
    classify_line_tokens,
    classify_token,
    dialog_difficulty_level,
)
from storage.crud.name_entity import create_name
from storage.models.schema import Base, DerivativeForm, Lemma


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _add_lemma(
    session: Session,
    text: str,
    *,
    level: Optional[int] = 2,
    pos_type: str = "noun",
) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=f"a {text}",
        pos_type=pos_type,
        difficulty_level=level,
        guid=f"X_{text}",
    )
    session.add(lemma)
    session.flush()
    return lemma


def test_known_lemma_at_level(session: Session) -> None:
    _add_lemma(session, "tomato", level=3)

    token = classify_token(session, "tomato", target_level=3)

    assert token.status == STATUS_KNOWN
    assert token.lemma_text == "tomato"
    assert token.difficulty_level == 3


def test_lemma_above_the_target_level_is_reported_separately(session: Session) -> None:
    _add_lemma(session, "aubergine", level=12)

    token = classify_token(session, "aubergine", target_level=3)

    assert token.status == STATUS_ABOVE_LEVEL
    assert token.difficulty_level == 12


def test_unknown_word_is_missing(session: Session) -> None:
    token = classify_token(session, "cashier", target_level=3)

    assert token.status == STATUS_MISSING
    assert token.is_missing is True
    assert token.lemma_id is None


def test_grammatical_words_are_never_missing(session: Session) -> None:
    for word in ("the", "is", "I"):
        assert classify_token(session, word, target_level=3).status == STATUS_GRAMMATICAL


def test_function_words_without_a_lemma_are_not_staged(session: Session) -> None:
    """ "of" is a gap in function-word data, not a vocabulary word to import."""
    token = classify_token(session, "of", target_level=3)

    assert token.status == STATUS_GRAMMATICAL


def test_numbers_are_not_vocabulary(session: Session) -> None:
    assert classify_token(session, "42", target_level=3).status == STATUS_GRAMMATICAL


def test_inflected_form_resolves_through_a_derivative_form(session: Session) -> None:
    lemma = _add_lemma(session, "come", level=1, pos_type="verb")
    session.add(
        DerivativeForm(
            lemma_id=lemma.id,
            language_code="en",
            derivative_form_text="came",
            grammatical_form="past",
        )
    )
    session.flush()

    token = classify_token(session, "came", target_level=3)

    assert token.status == STATUS_KNOWN
    assert token.lemma_text == "come"


def test_regular_plural_resolves_without_stored_forms(session: Session) -> None:
    """Lemmas whose forms have not been generated must still match their plural."""
    _add_lemma(session, "tomato", level=3)

    token = classify_token(session, "tomatoes", target_level=3)

    assert token.status == STATUS_KNOWN
    assert token.lemma_text == "tomato"


def test_registered_name_beats_a_same_spelled_lemma(session: Session) -> None:
    """Capitalized "Rose" is the character, not the flower."""
    _add_lemma(session, "rose", level=2)
    create_name(session, name_text="Rose", kind="given_name")

    as_name = classify_token(session, "Rose", target_level=3)
    as_word = classify_token(session, "rose", target_level=3)

    assert as_name.status == STATUS_NAME
    assert as_word.status == STATUS_KNOWN
    assert as_word.lemma_text == "rose"


def test_cast_name_counts_before_it_is_registered(session: Session) -> None:
    token = classify_token(session, "George", target_level=3, cast_names={"George"})

    assert token.status == STATUS_NAME
    assert token.name_id is None


def test_lowercase_word_is_not_treated_as_a_name(session: Session) -> None:
    create_name(session, name_text="Mark", kind="given_name")

    token = classify_token(session, "mark", target_level=3)

    assert token.status == STATUS_MISSING


def test_lowest_level_sense_wins_for_a_homograph(session: Session) -> None:
    """Matching the rare sense would inflate the dialog's computed level."""
    _add_lemma(session, "bank", level=2)
    session.add(
        Lemma(
            lemma_text="bank",
            definition_text="the side of a river",
            pos_type="noun",
            difficulty_level=17,
            guid="X_bank_river",
        )
    )
    session.flush()

    token = classify_token(session, "bank", target_level=5)

    assert token.difficulty_level == 2


def test_classify_line_tokens_keeps_order_and_repeats(session: Session) -> None:
    _add_lemma(session, "tomato", level=3)

    tokens = classify_line_tokens(session, "A tomato, and one more tomato.", target_level=3)

    surfaces = [token.surface for token in tokens]
    assert surfaces.count("tomato") == 2
    assert surfaces.index("tomato") < surfaces.index("more")


def test_classify_line_tokens_uses_the_cache(session: Session) -> None:
    _add_lemma(session, "tomato", level=3)
    cache: dict = {}

    classify_line_tokens(session, "A tomato.", target_level=3, cache=cache)
    classify_line_tokens(session, "Another tomato.", target_level=3, cache=cache)

    assert "tomato" in cache


def test_analyze_lines_dedupes_and_records_where_words_appear(session: Session) -> None:
    _add_lemma(session, "tomato", level=3)

    report = analyze_lines(
        session,
        ["I want a tomato.", "The tomato is fresh.", "A cashier waits."],
        target_level=3,
    )

    tomato = next(token for token in report.tokens if token.surface == "tomato")
    assert tomato.line_indices == [0, 1]
    assert tomato.example_line == "I want a tomato."
    assert [token.surface for token in report.missing] == [
        "want",
        "fresh",
        "cashier",
        "waits",
    ]


def test_a_sentence_initial_capital_does_not_leak_across_lines(session: Session) -> None:
    """The shared cache folds case; it must not stamp "My" onto a later "my"."""
    _add_lemma(session, "bag", level=2)

    cache: dict = {}
    first = classify_line_tokens(session, "My bag is here.", target_level=3, cache=cache)
    second = classify_line_tokens(session, "I have a bag in my bag.", target_level=3, cache=cache)

    assert first[0].surface == "My"
    assert [token.surface for token in second] == ["I", "have", "a", "bag", "in", "my", "bag"]


def test_report_prefers_the_uncapitalized_spelling_of_a_word(session: Session) -> None:
    """Staging a pending import must not import a sentence-initial capital."""
    report = analyze_lines(session, ["Cashiers are busy.", "I see the cashiers."], target_level=3)

    # "Cashiers" led the first line and recurs mid-sentence in the second.
    assert [token.surface for token in report.missing] == ["cashiers", "busy", "see"]


def test_a_name_keeps_its_capital_across_lines(session: Session) -> None:
    """Case-preservation for names is the reason the surface is verbatim."""
    create_name(session, name_text="George", kind="given_name")

    report = analyze_lines(session, ["George waits.", "We saw George."], target_level=3)

    assert [token.surface for token in report.names] == ["George"]


def test_difficulty_level_takes_the_85th_percentile() -> None:
    """The top ~15% of the vocabulary is allowed to sit above the level."""
    levels = [1] * 17 + [20, 20, 20]

    # 85% of 20 words is rank 17, the last of the easy ones.
    assert dialog_difficulty_level(levels, target_level=1) == 1
    assert dialog_difficulty_level([1] * 16 + [20] * 4, target_level=1) == 20


def test_difficulty_level_result_is_always_a_level_some_word_has() -> None:
    """Nearest-rank, so no interpolated level that no word actually carries."""
    assert dialog_difficulty_level([2, 4, 8, 9], target_level=2) in {2, 4, 8, 9}


def test_difficulty_level_floors_at_the_requested_level() -> None:
    """Easy words in a level-5 dialog do not make it a level-2 dialog."""
    assert dialog_difficulty_level([2, 2, 2, 5], target_level=5) == 5


def test_difficulty_level_drops_below_target_when_every_word_is_easier() -> None:
    """A dialog whose vocabulary is entirely below target is described by it."""
    assert dialog_difficulty_level([1, 2, 2, 3], target_level=8) == 3


def test_difficulty_level_without_a_target_has_no_floor() -> None:
    assert dialog_difficulty_level([1] * 9 + [4], target_level=None) == 1


def test_difficulty_level_keeps_the_max_for_a_tiny_vocabulary() -> None:
    """Nearest-rank cannot discount an outlier until ~7 words are in play.

    A dialog using four leveled words has no 15% tail to trim, so its level is
    still the hardest of them -- which is the right answer for a dialog that
    short.
    """
    assert dialog_difficulty_level([1, 1, 1, 4], target_level=None) == 4


def test_difficulty_level_of_nothing_is_none() -> None:
    assert dialog_difficulty_level([], target_level=3) is None


def test_one_hard_word_does_not_define_the_computed_level(session: Session) -> None:
    """The 85th percentile, not the max: a lone rare word is expected."""
    for index in range(9):
        _add_lemma(session, f"easyword{index}", level=3)
    _add_lemma(session, "aubergine", level=12)

    line = " ".join(f"easyword{index}" for index in range(9)) + " aubergine."
    report = analyze_lines(session, [line], target_level=3)

    assert report.computed_minimum_level == 3


def test_names_do_not_raise_the_computed_level(session: Session) -> None:
    """A dialog full of names is not a harder dialog."""
    _add_lemma(session, "tomato", level=3)
    create_name(session, name_text="George", kind="given_name")

    report = analyze_lines(session, ["George bought a tomato."], target_level=3)

    assert report.computed_minimum_level == 3
    assert [token.surface for token in report.names] == ["George"]


def test_computed_minimum_level_is_none_without_leveled_vocabulary(session: Session) -> None:
    report = analyze_lines(session, ["The is a."], target_level=3)

    assert report.computed_minimum_level is None


def test_counts_cover_every_status(session: Session) -> None:
    _add_lemma(session, "tomato", level=3)
    _add_lemma(session, "aubergine", level=12)
    create_name(session, name_text="George", kind="given_name")

    report = analyze_line(
        session, "George likes the tomato and the aubergine and the cashier.", target_level=3
    )

    counts = report.counts
    assert counts[STATUS_KNOWN] == 1
    assert counts[STATUS_ABOVE_LEVEL] == 1
    assert counts[STATUS_NAME] == 1
    assert counts[STATUS_MISSING] == 2  # likes, cashier
    assert counts[STATUS_GRAMMATICAL] >= 2


def test_known_ratio_counts_names_as_covered(session: Session) -> None:
    _add_lemma(session, "tomato", level=3)
    create_name(session, name_text="George", kind="given_name")

    report = analyze_line(session, "George ate the tomato.", target_level=3)

    # George + tomato are covered; "ate" is not.
    assert report.vocabulary_token_count == 3
    assert report.known_ratio == pytest.approx(2 / 3)


def test_known_ratio_of_a_dialog_with_no_vocabulary(session: Session) -> None:
    assert analyze_line(session, "The is a.", target_level=3).known_ratio == 1.0
