"""Tests for multi-word phrase selection and phrase-aware tokenization."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import Base, DerivativeForm, Lemma
from wordfreq.corpora.gutenberg_text import analyze_text, build_phrase_index, iter_tokens
from wordfreq.corpora.lemma_phrases import (
    is_indexable_phrase,
    is_periphrastic,
    load_lemma_phrases,
    load_phrase_index,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_form(
    session: Session,
    lemma_text: str,
    form_text: str,
    grammatical_form: str,
    pos_type: str = "noun",
    language_code: str = "en",
) -> None:
    lemma = (
        session.query(Lemma)
        .filter(Lemma.lemma_text == lemma_text, Lemma.pos_type == pos_type)
        .first()
    )
    if lemma is None:
        lemma = Lemma(
            lemma_text=lemma_text,
            definition_text=lemma_text,
            pos_type=pos_type,
        )
        session.add(lemma)
        session.flush()
    session.add(
        DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text=form_text,
            language_code=language_code,
            grammatical_form=grammatical_form,
        )
    )
    session.flush()


# --- Which multi-word forms belong in the index ------------------------------


def test_future_tense_conjugations_are_periphrastic() -> None:
    """ "will exist" is syntax, not a compound word."""
    assert is_periphrastic("will exist", "verb/en_1s_future")
    assert not is_indexable_phrase("will exist", "verb/en_1s_future")


def test_comparatives_are_periphrastic() -> None:
    assert is_periphrastic("more quickly", "adverb/en_comparative")
    assert is_periphrastic("most careful", "adjective/en_superlative")
    assert not is_indexable_phrase("more quickly", "adverb/en_comparative")


def test_auxiliary_leading_word_is_caught_without_a_tag() -> None:
    """A loosely tagged row cannot smuggle a conjugation into the index."""
    assert is_periphrastic("will become", None)
    assert is_periphrastic("has finished", "lemma")
    assert not is_indexable_phrase("will become", "synonym")


def test_lexical_compounds_are_indexable() -> None:
    assert is_indexable_phrase("ice cream", "noun/en_singular")
    assert is_indexable_phrase("ice creams", "noun/en_plural")
    assert is_indexable_phrase("police officer", "noun/en_singular")
    assert not is_periphrastic("ice cream", "noun/en_singular")


def test_single_words_are_not_phrases() -> None:
    assert not is_indexable_phrase("cream", "noun/en_singular")


def test_dictionary_annotations_are_rejected() -> None:
    """Counters and parenthetical glosses are never corpus surface strings."""
    assert not is_indexable_phrase("head (of cattle)", "noun/en_singular")
    assert not is_indexable_phrase("(counter for horses)", "noun/en_singular")


def test_lemma_text_is_indexed_even_without_derivative_forms() -> None:
    """ "ice cream" is a lemma with no forms; it must still be indexed."""
    session = _make_session()
    try:
        lemma = Lemma(
            lemma_text="ice cream",
            definition_text="a frozen dessert",
            pos_type="noun",
        )
        session.add(lemma)
        session.flush()

        assert load_lemma_phrases(session) == ["ice cream"]
    finally:
        session.close()


def test_slash_separated_alternatives_are_rejected() -> None:
    """ "flock / herd / swarm" lists alternatives; it is not a phrase."""
    assert not is_indexable_phrase("flock / herd / swarm", "noun/en_singular")
    assert not is_indexable_phrase("litter / brood", "noun/en_singular")


def test_periphrastic_forms_can_be_opted_out() -> None:
    """Joined by default -- "will want" is a form of "want" -- but optional."""
    session = _make_session()
    try:
        _add_form(session, "ice cream", "ice cream", "noun/en_singular")
        _add_form(session, "exist", "will exist", "verb/en_1s_future", pos_type="verb")

        assert load_lemma_phrases(session) == ["ice cream", "will exist"]
        assert load_lemma_phrases(session, include_periphrastic=False) == ["ice cream"]
    finally:
        session.close()


def test_load_lemma_phrases_drops_annotations_but_keeps_the_rest() -> None:
    """Compounds and periphrastic forms both index; dictionary glosses do not."""
    session = _make_session()
    try:
        _add_form(session, "ice cream", "ice cream", "noun/en_singular")
        _add_form(session, "ice cream", "ice creams", "noun/en_plural")
        _add_form(session, "exist", "will exist", "verb/en_1s_future", pos_type="verb")
        _add_form(session, "quickly", "more quickly", "adverb/en_comparative", pos_type="adverb")
        _add_form(session, "cattle", "head (of cattle)", "noun/en_singular")

        assert load_lemma_phrases(session) == [
            "ice cream",
            "ice creams",
            "more quickly",
            "will exist",
        ]
        assert load_lemma_phrases(session, include_periphrastic=False) == [
            "ice cream",
            "ice creams",
        ]
    finally:
        session.close()


def test_load_lemma_phrases_is_language_scoped() -> None:
    session = _make_session()
    try:
        _add_form(session, "ice cream", "ice cream", "noun/en_singular")
        _add_form(session, "helado", "helado cremoso", "noun/es_singular", language_code="es")

        assert load_lemma_phrases(session, language_code="en") == ["ice cream"]
        assert load_lemma_phrases(session, language_code="es") == ["helado cremoso"]
    finally:
        session.close()


def test_synonyms_can_be_excluded() -> None:
    session = _make_session()
    try:
        _add_form(session, "mobile phone", "mobile phone", "noun/en_singular")
        _add_form(session, "mobile phone", "cell phone", "synonym_near")

        assert "cell phone" in load_lemma_phrases(session, include_synonyms=True)
        assert "cell phone" not in load_lemma_phrases(session, include_synonyms=False)
    finally:
        session.close()


def test_load_phrase_index_merges_extra_phrases() -> None:
    """The proper-noun whitelist's multi-word entries join the index."""
    session = _make_session()
    try:
        _add_form(session, "ice cream", "ice cream", "noun/en_singular")

        index = load_phrase_index(session, extra_phrases=["New York", "Atlantic Ocean"])
        assert index["ice cream"] == 2
        assert index["new york"] == 2
        assert index["atlantic ocean"] == 2
    finally:
        session.close()


# --- Phrase-aware tokenization -----------------------------------------------


def test_build_phrase_index_drops_single_words() -> None:
    index = build_phrase_index(["ice cream", "cream", "New York"])
    assert index == {"ice cream": 2, "new york": 2}


def test_compound_is_counted_as_one_token() -> None:
    index = build_phrase_index(["ice cream"])
    tokens = [token for token, _, _ in iter_tokens("He bought ice cream today.", index)]
    assert tokens == ["he", "bought", "ice cream", "today"]


def test_compound_does_not_inflate_its_parts() -> None:
    """The whole point: "cream" is not credited for every ice cream."""
    text = "Ice cream is cream and ice."
    index = build_phrase_index(["ice cream"])

    without = analyze_text(text)
    with_phrases = analyze_text(text, index)

    assert without.counts["cream"] == 2
    assert with_phrases.counts["cream"] == 1
    assert with_phrases.counts["ice cream"] == 1
    assert with_phrases.counts["ice"] == 1


def test_conjugation_is_left_split() -> None:
    """ "will walk" must keep "will" and "walk" as separate frequencies."""
    index = build_phrase_index(["ice cream"])
    tokens = [token for token, _, _ in iter_tokens("She will walk home.", index)]
    assert tokens == ["she", "will", "walk", "home"]


def test_plural_compound_matches_its_own_entry() -> None:
    index = build_phrase_index(["ice cream", "ice creams"])
    tokens = [token for token, _, _ in iter_tokens("Two ice creams melted.", index)]
    assert tokens == ["two", "ice creams", "melted"]


def test_longest_phrase_wins() -> None:
    index = build_phrase_index(["new york", "new york city"])
    tokens = [token for token, _, _ in iter_tokens("We saw New York City today.", index)]
    assert tokens == ["we", "saw", "new york city", "today"]


def test_phrase_takes_capitalization_from_its_first_word() -> None:
    """So a multi-word name reads as name evidence, like a single-word one."""
    index = build_phrase_index(["new york"])
    tokens = list(iter_tokens("I visited New York in April.", index))
    phrase = [entry for entry in tokens if entry[0] == "new york"][0]
    assert phrase[1] is True  # capitalized
    assert phrase[2] is False  # not sentence-initial


def test_no_index_leaves_tokenization_unchanged() -> None:
    """Passing no phrases must behave exactly as before the feature existed."""
    text = "He bought ice cream in New York."
    assert [token for token, _, _ in iter_tokens(text)] == [
        token for token, _, _ in iter_tokens(text, None)
    ]
    assert [token for token, _, _ in iter_tokens(text, {})] == [
        token for token, _, _ in iter_tokens(text)
    ]


def test_partial_phrase_match_does_not_consume_words() -> None:
    """ "ice" followed by something else is still plain "ice"."""
    index = build_phrase_index(["ice cream"])
    tokens = [token for token, _, _ in iter_tokens("The ice was cold.", index)]
    assert tokens == ["the", "ice", "was", "cold"]


def test_phrase_at_end_of_text_is_matched() -> None:
    index = build_phrase_index(["ice cream"])
    tokens = [token for token, _, _ in iter_tokens("I want ice cream", index)]
    assert tokens == ["i", "want", "ice cream"]
