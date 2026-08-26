"""Tests for the WordToken read facade."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import (
    SENSE_PROMINENCE_COMMON,
    SENSE_PROMINENCE_RARE,
    SENSE_PROMINENCE_VERY_COMMON,
    Base,
    DerivativeForm,
    ExternalLexemeAnnotation,
    Lemma,
    WordToken,
)
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm
from storage.word_token_view import (
    ATTACHMENT_DERIVATIVE,
    ATTACHMENT_VARIANT,
    corpus_name_for_source,
    get_word_token_view,
    get_word_token_view_by_text,
    search_word_tokens,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_token(
    session: Session,
    token: str,
    language_code: str = "en",
    frequency_rank: Optional[int] = None,
) -> WordToken:
    row = WordToken(token=token, language_code=language_code, frequency_rank=frequency_rank)
    session.add(row)
    session.flush()
    return row


def _add_lemma(
    session: Session,
    text: str,
    guid: str,
    sense_prominence: str = SENSE_PROMINENCE_COMMON,
    disambiguation: Optional[str] = None,
) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=f"definition of {text}",
        pos_type="noun",
        guid=guid,
        sense_prominence=sense_prominence,
        disambiguation=disambiguation,
    )
    session.add(lemma)
    session.flush()
    return lemma


def _add_form(
    session: Session,
    lemma: Lemma,
    token: WordToken,
    text: str,
    grammatical_form: str = "noun/en_singular",
    is_base_form: bool = True,
) -> DerivativeForm:
    form = DerivativeForm(
        lemma_id=lemma.id,
        derivative_form_text=text,
        language_code=token.language_code,
        grammatical_form=grammatical_form,
        is_base_form=is_base_form,
        word_token_id=token.id,
    )
    session.add(form)
    session.flush()
    return form


def _add_annotation(
    session: Session,
    token: WordToken,
    source: str,
    tier_name: str = "tier",
    ordinal_rank: Optional[int] = None,
    frequency: Optional[float] = None,
) -> ExternalLexemeAnnotation:
    row = ExternalLexemeAnnotation(
        word_token_id=token.id,
        source=source,
        tier_name=tier_name,
        ordinal_rank=ordinal_rank,
        frequency=frequency,
    )
    session.add(row)
    session.flush()
    return row


def test_corpus_name_for_source_inverts_the_wordfreq_prefix() -> None:
    """A wordfreq source yields its corpus; a tier source yields None."""
    assert corpus_name_for_source("wordfreq_cooking") == "cooking"
    assert corpus_name_for_source("cefr") is None


def test_missing_token_returns_none() -> None:
    session = _make_session()
    try:
        assert get_word_token_view(session, 9999) is None
        assert get_word_token_view_by_text(session, "nonexistent", "en") is None
    finally:
        session.close()


def test_single_sense_token_takes_the_whole_frequency_share() -> None:
    session = _make_session()
    try:
        token = _add_token(session, "will")
        lemma = _add_lemma(session, "will", "N01_001")
        _add_form(session, lemma, token, "will")

        view = get_word_token_view_by_text(session, "will", "en")
        assert view is not None
        assert not view.is_homograph
        assert view.lemma_ids == [lemma.id]
        assert len(view.attachments) == 1
        assert view.attachments[0].share == 1.0
        assert view.attachments[0].attachment_kind == ATTACHMENT_DERIVATIVE
    finally:
        session.close()


def test_homograph_splits_share_by_sense_prominence() -> None:
    """Three senses of "top" divide the string's frequency by their weights."""
    session = _make_session()
    try:
        token = _add_token(session, "top")
        prominent = _add_lemma(session, "top", "N01_001", SENSE_PROMINENCE_VERY_COMMON)
        middling = _add_lemma(session, "top", "N01_002", SENSE_PROMINENCE_COMMON)
        rare = _add_lemma(session, "top", "N01_003", SENSE_PROMINENCE_RARE)
        for lemma in (prominent, middling, rare):
            _add_form(session, lemma, token, "top")

        view = get_word_token_view(session, token.id)
        assert view is not None
        assert view.is_homograph
        assert len(view.lemma_ids) == 3

        shares = {a.lemma_id: a.share for a in view.attachments}
        assert shares[prominent.id] is not None
        # Weights are 20 / 5 / 0.15, summing to 25.15.
        assert shares[prominent.id] == 20.0 / 25.15
        assert shares[middling.id] == 5.0 / 25.15
        assert shares[rare.id] == 0.15 / 25.15
        assert sum(s for s in shares.values() if s is not None) == 1.0
    finally:
        session.close()


def test_variant_spelling_is_reported_as_an_attachment() -> None:
    """A lemma reaching a token only by an alternate spelling still claims it."""
    session = _make_session()
    try:
        token = _add_token(session, "grey")
        lemma = _add_lemma(session, "gray", "A01_001")
        variant = VariantForm(
            lemma_id=lemma.id,
            language_code="en",
            variant_kind=VARIANT_KIND_SPELLING,
            variant_key="grey",
            grammatical_form="adjective/en_positive",
            variant_form_text="grey",
            word_token_id=token.id,
            is_base_form=True,
        )
        session.add(variant)
        session.flush()

        view = get_word_token_view(session, token.id)
        assert view is not None
        assert len(view.attachments) == 1
        attachment = view.attachments[0]
        assert attachment.attachment_kind == ATTACHMENT_VARIANT
        assert attachment.lemma_id == lemma.id
        # The variant's own grammatical slot survives, rather than being
        # overwritten by the variant kind, which has its own field.
        assert attachment.grammatical_form == "adjective/en_positive"
        assert attachment.variant_kind == VARIANT_KIND_SPELLING
        assert attachment.variant_key == "grey"
        assert attachment.is_base_form
        # Sole claimant, so it takes the whole frequency rather than none of it.
        assert attachment.share == 1.0
    finally:
        session.close()


def test_one_lemma_reaching_a_token_two_ways_gets_one_share() -> None:
    """A derivative form and a variant of the same lemma are one claimant."""
    session = _make_session()
    try:
        token = _add_token(session, "grey")
        lemma = _add_lemma(session, "gray", "A01_001")
        _add_form(session, lemma, token, "grey", grammatical_form="adj/en_base")
        session.add(
            VariantForm(
                lemma_id=lemma.id,
                language_code="en",
                variant_kind=VARIANT_KIND_SPELLING,
                variant_key="grey",
                grammatical_form="adj/en_base",
                variant_form_text="grey",
                word_token_id=token.id,
            )
        )
        session.flush()

        view = get_word_token_view(session, token.id)
        assert view is not None
        assert len(view.attachments) == 2
        assert view.lemma_ids == [lemma.id]
        assert {a.share for a in view.attachments} == {1.0}
    finally:
        session.close()


def test_corpus_and_tier_stats_are_separated() -> None:
    session = _make_session()
    try:
        token = _add_token(session, "sugar")
        _add_annotation(
            session, token, "wordfreq_cooking", "cooking", ordinal_rank=26, frequency=4941.6
        )
        _add_annotation(
            session, token, "wordfreq_19th_books", "19th_books", ordinal_rank=2623, frequency=31.7
        )
        _add_annotation(session, token, "cefr", "A1")

        view = get_word_token_view(session, token.id)
        assert view is not None
        assert [s.corpus_name for s in view.wordfreq_stats] == ["cooking", "19th_books"]
        assert [s.source for s in view.tier_stats] == ["cefr"]
        # Best rank first among the corpora.
        assert view.wordfreq_stats[0].ordinal_rank == 26
    finally:
        session.close()


def test_token_with_no_lemma_still_reports_its_corpora() -> None:
    """An unattached token is a real row: the corpora measured it, nobody claims it."""
    session = _make_session()
    try:
        token = _add_token(session, "ice cream")
        _add_annotation(session, token, "cefr", "A1")

        view = get_word_token_view(session, token.id)
        assert view is not None
        assert view.attachments == []
        assert view.lemma_ids == []
        assert not view.is_homograph
        assert len(view.tier_stats) == 1
    finally:
        session.close()


def test_multiword_tokens_are_flagged() -> None:
    session = _make_session()
    try:
        multi = _add_token(session, "ice cream")
        single = _add_token(session, "ice")

        multi_view = get_word_token_view(session, multi.id)
        single_view = get_word_token_view(session, single.id)
        assert multi_view is not None and single_view is not None
        assert multi_view.is_multiword
        assert not single_view.is_multiword
    finally:
        session.close()


def test_base_form_attachment_sorts_first() -> None:
    """The dictionary headword leads, not an arbitrary inflection."""
    session = _make_session()
    try:
        token = _add_token(session, "top")
        lemma = _add_lemma(session, "top", "N01_001")
        _add_form(session, lemma, token, "top", "noun/en_plural", is_base_form=False)
        _add_form(session, lemma, token, "top", "noun/en_singular", is_base_form=True)

        view = get_word_token_view(session, token.id)
        assert view is not None
        assert view.attachments[0].is_base_form
    finally:
        session.close()


def test_shares_can_be_skipped() -> None:
    """include_shares=False leaves shares unset rather than guessing them."""
    session = _make_session()
    try:
        token = _add_token(session, "will")
        lemma = _add_lemma(session, "will", "N01_001")
        _add_form(session, lemma, token, "will")

        view = get_word_token_view(session, token.id, include_shares=False)
        assert view is not None
        assert view.attachments[0].share is None
    finally:
        session.close()


def test_search_puts_the_exact_match_first() -> None:
    session = _make_session()
    try:
        _add_token(session, "topic", frequency_rank=500)
        _add_token(session, "stopped", frequency_rank=200)
        _add_token(session, "top", frequency_rank=900)

        results = search_word_tokens(session, "top", "en")
        assert [row.token for row in results][:2] == ["top", "topic"]
        # "stopped" contains the needle but does not start with it, so it sorts
        # last despite the better rank.
        assert results[-1].token == "stopped"
    finally:
        session.close()


def test_search_is_language_scoped_and_empty_query_returns_nothing() -> None:
    session = _make_session()
    try:
        _add_token(session, "top", language_code="en")
        _add_token(session, "top", language_code="lt")

        assert [row.language_code for row in search_word_tokens(session, "top", "en")] == ["en"]
        assert search_word_tokens(session, "   ", "en") == []
    finally:
        session.close()


def test_display_text_includes_the_disambiguation() -> None:
    session = _make_session()
    try:
        token = _add_token(session, "top")
        lemma = _add_lemma(session, "top", "N01_001", disambiguation="spinning toy")
        _add_form(session, lemma, token, "top")

        view = get_word_token_view(session, token.id)
        assert view is not None
        assert view.attachments[0].display_text == "top (spinning toy)"
    finally:
        session.close()
