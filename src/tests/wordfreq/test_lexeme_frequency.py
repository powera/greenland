"""Tests for wordfreq.lexeme_frequency rollups and sense-prominence splitting."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.lexeme import get_lexeme
from storage.models.schema import (
    SENSE_PROMINENCE_COMMON,
    SENSE_PROMINENCE_UNCOMMON,
    SENSE_PROMINENCE_VERY_COMMON,
    Base,
    DerivativeForm,
    ExternalLexemeAnnotation,
    Lemma,
    WordToken,
)
from wordfreq.lexeme_frequency import (
    get_lexeme_frequency,
    get_token_share,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_lemma(
    session: Session,
    text: str,
    guid: str,
    *,
    pos_type: str = "noun",
    sense_prominence: str = SENSE_PROMINENCE_COMMON,
) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=text,
        pos_type=pos_type,
        guid=guid,
        sense_prominence=sense_prominence,
    )
    session.add(lemma)
    session.flush()
    return lemma


def _add_token_with_freq(
    session: Session,
    token_text: str,
    corpus_name: str,
    frequency: float,
    language_code: str = "en",
) -> WordToken:
    """Insert a WordToken (if missing) and an ExternalLexemeAnnotation for ``wordfreq_<corpus_name>``."""
    token = (
        session.query(WordToken)
        .filter(WordToken.token == token_text, WordToken.language_code == language_code)
        .first()
    )
    if token is None:
        token = WordToken(token=token_text, language_code=language_code)
        session.add(token)
        session.flush()
    session.add(
        ExternalLexemeAnnotation(
            word_token_id=token.id,
            source=f"wordfreq_{corpus_name}",
            tier_name="r1-50",
            frequency=frequency,
        )
    )
    session.flush()
    return token


def _add_form(
    session: Session,
    lemma: Lemma,
    text: str,
    grammatical_form: str,
    *,
    word_token: WordToken | None = None,
    language_code: str = "en",
    is_base_form: bool = False,
) -> DerivativeForm:
    form = DerivativeForm(
        lemma_id=lemma.id,
        derivative_form_text=text,
        word_token_id=word_token.id if word_token is not None else None,
        language_code=language_code,
        grammatical_form=grammatical_form,
        is_base_form=is_base_form,
    )
    session.add(form)
    session.flush()
    return form


def test_single_sense_lemma_gets_full_token_frequency() -> None:
    """An unambiguous lemma owns 100% of its token frequency regardless of prominence."""
    session = _make_session()
    try:
        elephant = _add_lemma(
            session, "elephant", "N01_001", sense_prominence=SENSE_PROMINENCE_COMMON
        )
        token = _add_token_with_freq(session, "elephant", "testcorpus", 42.0)
        _add_form(session, elephant, "elephant", "singular", word_token=token, is_base_form=True)
        session.commit()

        lexeme = get_lexeme(session, elephant.id, "en")
        assert lexeme is not None
        rollup = get_lexeme_frequency(session, lexeme, "testcorpus")
        assert rollup.total_frequency == pytest.approx(42.0)
        assert len(rollup.form_breakdown) == 1
        assert rollup.form_breakdown[0].share == pytest.approx(1.0)
    finally:
        session.close()


def test_homograph_split_by_sense_prominence_weights() -> None:
    """bank-finance (very_common=20) vs bank-river (common=5) split 20/25 vs 5/25."""
    session = _make_session()
    try:
        bank_fin = _add_lemma(
            session, "bank", "N02_001", sense_prominence=SENSE_PROMINENCE_VERY_COMMON
        )
        bank_riv = _add_lemma(session, "bank", "N02_002", sense_prominence=SENSE_PROMINENCE_COMMON)
        token = _add_token_with_freq(session, "bank", "testcorpus", 100.0)
        _add_form(session, bank_fin, "bank", "singular", word_token=token, is_base_form=True)
        _add_form(session, bank_riv, "bank", "singular", word_token=token, is_base_form=True)
        session.commit()

        share_fin = get_token_share(session, token.id, bank_fin.id)
        share_riv = get_token_share(session, token.id, bank_riv.id)
        assert share_fin == pytest.approx(20 / 25)
        assert share_riv == pytest.approx(5 / 25)
        assert share_fin + share_riv == pytest.approx(1.0)

        lex_fin = get_lexeme(session, bank_fin.id, "en")
        lex_riv = get_lexeme(session, bank_riv.id, "en")
        assert lex_fin is not None and lex_riv is not None
        rollup_fin = get_lexeme_frequency(session, lex_fin, "testcorpus")
        rollup_riv = get_lexeme_frequency(session, lex_riv, "testcorpus")
        assert rollup_fin.total_frequency == pytest.approx(80.0)
        assert rollup_riv.total_frequency == pytest.approx(20.0)
    finally:
        session.close()


def test_three_way_split_with_uncommon() -> None:
    """very_common(20) + common(5) + uncommon(1) splits a token 20/26, 5/26, 1/26."""
    session = _make_session()
    try:
        a = _add_lemma(session, "bank", "X01", sense_prominence=SENSE_PROMINENCE_VERY_COMMON)
        b = _add_lemma(session, "bank", "X02", sense_prominence=SENSE_PROMINENCE_COMMON)
        c = _add_lemma(session, "bank", "X03", sense_prominence=SENSE_PROMINENCE_UNCOMMON)
        token = _add_token_with_freq(session, "bank", "c", 260.0)
        for lemma in (a, b, c):
            _add_form(session, lemma, "bank", "singular", word_token=token, is_base_form=True)
        session.commit()

        lex_a = get_lexeme(session, a.id, "en")
        lex_b = get_lexeme(session, b.id, "en")
        lex_c = get_lexeme(session, c.id, "en")
        assert lex_a is not None and lex_b is not None and lex_c is not None
        ra = get_lexeme_frequency(session, lex_a, "c")
        rb = get_lexeme_frequency(session, lex_b, "c")
        rc = get_lexeme_frequency(session, lex_c, "c")
        assert ra.total_frequency == pytest.approx(200.0)
        assert rb.total_frequency == pytest.approx(50.0)
        assert rc.total_frequency == pytest.approx(10.0)
    finally:
        session.close()


def test_inflections_sum_into_lexeme_total() -> None:
    """All DerivativeForms tied to one lemma roll up additively."""
    session = _make_session()
    try:
        read_v = _add_lemma(
            session, "read", "V01", pos_type="verb", sense_prominence=SENSE_PROMINENCE_VERY_COMMON
        )
        t_present = _add_token_with_freq(session, "read", "c", 100.0)
        t_reads = _add_token_with_freq(session, "reads", "c", 30.0)
        t_reading = _add_token_with_freq(session, "reading", "c", 50.0)
        _add_form(session, read_v, "read", "infinitive", word_token=t_present, is_base_form=True)
        _add_form(session, read_v, "reads", "3rd_person_singular_present", word_token=t_reads)
        _add_form(session, read_v, "reading", "gerund", word_token=t_reading)
        session.commit()

        lex = get_lexeme(session, read_v.id, "en")
        assert lex is not None
        rollup = get_lexeme_frequency(session, lex, "c")
        assert rollup.total_frequency == pytest.approx(180.0)
        assert len(rollup.form_breakdown) == 3
    finally:
        session.close()


def test_unknown_corpus_returns_zero_rollup() -> None:
    """Querying an unknown corpus name yields an empty zero-frequency rollup."""
    session = _make_session()
    try:
        elephant = _add_lemma(session, "elephant", "N01_001")
        _add_form(session, elephant, "elephant", "singular", is_base_form=True)
        session.commit()
        lexeme = get_lexeme(session, elephant.id, "en")
        assert lexeme is not None
        rollup = get_lexeme_frequency(session, lexeme, "no-such-corpus")
        assert rollup.total_frequency == 0.0
        assert rollup.form_breakdown == ()
    finally:
        session.close()


def test_form_without_token_is_skipped() -> None:
    """Multi-word forms (no word_token_id) contribute zero, no error."""
    session = _make_session()
    try:
        lemma = _add_lemma(session, "give up", "V99", pos_type="verb")
        _add_form(session, lemma, "give up", "infinitive", word_token=None, is_base_form=True)
        session.commit()

        lex = get_lexeme(session, lemma.id, "en")
        assert lex is not None
        rollup = get_lexeme_frequency(session, lex, "c")
        assert rollup.total_frequency == 0.0
        assert rollup.form_breakdown == ()
    finally:
        session.close()


def test_token_share_zero_for_unattached_token() -> None:
    session = _make_session()
    try:
        token = WordToken(token="orphan", language_code="en")
        session.add(token)
        session.flush()
        assert get_token_share(session, token.id, lemma_id=999) == 0.0
    finally:
        session.close()
