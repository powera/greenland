"""Tests for wordfreq.frequency.combined_rank — weighted harmonic mean over
lexeme rollups + Cambridge YLE + CEFR tier signals."""

from __future__ import annotations

from typing import Optional
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import (
    Base,
    Corpus,
    DerivativeForm,
    ExternalLexemeAnnotation,
    Lemma,
    LemmaTier,
    WordToken,
)
from wordfreq.frequency import combined_rank
from wordfreq.frequency.corpus import CorpusConfig


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_lemma(session: Session, text: str, guid: str) -> Lemma:
    lemma = Lemma(lemma_text=text, definition_text=text, pos_type="noun", guid=guid)
    session.add(lemma)
    session.flush()
    return lemma


def _add_token_with_freq(
    session: Session,
    token_text: str,
    corpus_name: str,
    frequency: float,
) -> WordToken:
    token = WordToken(token=token_text, language_code="en")
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
    *,
    word_token: Optional[WordToken] = None,
) -> DerivativeForm:
    form = DerivativeForm(
        lemma_id=lemma.id,
        derivative_form_text=text,
        word_token_id=word_token.id if word_token else None,
        language_code="en",
        grammatical_form="singular",
        is_base_form=True,
    )
    session.add(form)
    session.flush()
    return form


def _patched_run(session: Session) -> dict:
    """Run calculate_lemma_combined_ranks against an in-memory session."""
    return combined_rank.calculate_lemma_combined_ranks(session)


# `get_enabled_corpus_configs` is bound at import time inside combined_rank, so
# the existing patch.object(combined_rank, "get_enabled_corpus_configs", ...)
# calls in tests still work.


def test_combined_rank_uses_only_wordfreq_when_only_corpus_signal() -> None:
    """A lemma with only one wordfreq corpus contribution gets that corpus' rank."""
    session = _make_session()
    try:
        # Configure one enabled corpus, weight 1.0
        with patch.object(
            combined_rank,
            "get_enabled_corpus_configs",
            return_value=[
                CorpusConfig(
                    name="cooking",
                    description="t",
                    file_path="x",
                    max_words=10,
                    corpus_weight=1.0,
                )
            ],
        ):
            common = _add_lemma(session, "salt", "N01")
            rare = _add_lemma(session, "saffron", "N02")
            t_common = _add_token_with_freq(session, "salt", "cooking", 100.0)
            t_rare = _add_token_with_freq(session, "saffron", "cooking", 1.0)
            _add_form(session, common, "salt", word_token=t_common)
            _add_form(session, rare, "saffron", word_token=t_rare)
            session.commit()

            result = _patched_run(session)

        assert result["success"] is True
        # Both lemmas are absent from every tier source, so each also picks up
        # the YLE/CEFR/Basic English unknown floors. That compresses the
        # absolute values, but salt (corpus rank 1) still beats saffron (rank 2).
        session.expire_all()
        salt = session.query(Lemma).filter_by(guid="N01").one()
        saffron = session.query(Lemma).filter_by(guid="N02").one()
        assert salt.frequency_rank == 4
        assert saffron.frequency_rank == 8
        assert salt.frequency_rank < saffron.frequency_rank
        assert "wordfreq_cooking" in result["sources_used"]
    finally:
        session.close()


def test_cefr_only_lemma_gets_cefr_synthetic_rank() -> None:
    """A lemma with no wordfreq data but a CEFR tier is ranked from the synthetic rank."""
    session = _make_session()
    try:
        with patch.object(combined_rank, "get_enabled_corpus_configs", return_value=[]):
            lemma = _add_lemma(session, "obfuscate", "V01")
            _add_form(session, lemma, "obfuscate", word_token=None)
            session.add(LemmaTier(lemma_id=lemma.id, source="cefr", tier_name="C1"))
            session.commit()

            result = _patched_run(session)

        assert result["success"] is True
        session.expire_all()
        scored = session.query(Lemma).filter_by(guid="V01").one()
        # CEFR C1 (12000) plus the YLE (7500) and Basic English (7500) unknown
        # floors: 3 / (1/7500 + 1/12000 + 1/7500) = 8571.
        assert scored.frequency_rank == 8571
        assert "cefr" in result["sources_used"]
    finally:
        session.close()


def test_basic_english_only_lemma_gets_synthetic_rank() -> None:
    """A lemma whose only positive signal is Basic English 'basic'."""
    session = _make_session()
    try:
        with patch.object(combined_rank, "get_enabled_corpus_configs", return_value=[]):
            lemma = _add_lemma(session, "animal", "N50")
            _add_form(session, lemma, "animal", word_token=None)
            session.add(LemmaTier(lemma_id=lemma.id, source="basic_english", tier_name="basic"))
            session.commit()

            result = _patched_run(session)

        assert result["success"] is True
        session.expire_all()
        scored = session.query(Lemma).filter_by(guid="N50").one()
        # Basic English 'basic' (600) plus the YLE (7500) and CEFR (25000)
        # unknown floors: 3 / (1/7500 + 1/25000 + 1/600) = 1630.
        assert scored.frequency_rank == 1630
        assert "basic_english" in result["sources_used"]
    finally:
        session.close()


def test_yle_plus_wordfreq_harmonic_mean() -> None:
    """A lemma with YLE starters + one wordfreq corpus rank 1, plus the CEFR and
    Basic English unknown floors it is absent from."""
    session = _make_session()
    try:
        with patch.object(
            combined_rank,
            "get_enabled_corpus_configs",
            return_value=[
                CorpusConfig(
                    name="cooking",
                    description="t",
                    file_path="x",
                    max_words=10,
                    corpus_weight=1.0,
                )
            ],
        ):
            cat = _add_lemma(session, "cat", "N01")
            t_cat = _add_token_with_freq(session, "cat", "cooking", 999.0)
            _add_form(session, cat, "cat", word_token=t_cat)
            session.add(LemmaTier(lemma_id=cat.id, source="cambridge_yle", tier_name="starters"))
            session.commit()

            result = _patched_run(session)

        assert result["success"] is True
        session.expire_all()
        scored = session.query(Lemma).filter_by(guid="N01").one()
        # wordfreq rank 1, YLE starters (325), CEFR unknown (25000), Basic
        # English unknown (7500): 4 / (1/1 + 1/325 + 1/25000 + 1/7500) = 4.
        assert scored.frequency_rank == 4
        assert "cambridge_yle" in result["sources_used"]
        assert "wordfreq_cooking" in result["sources_used"]
    finally:
        session.close()


def test_lemma_with_no_signal_gets_all_unknown_floors() -> None:
    """A lemma with no wordfreq rollup and no tier rows still gets a rank.

    The tier floors are applied unconditionally, so "absent everywhere" is
    itself a signal: the lemma lands at the harmonic mean of the three
    unknown ranks rather than being skipped.
    """
    session = _make_session()
    try:
        with patch.object(combined_rank, "get_enabled_corpus_configs", return_value=[]):
            lemma = _add_lemma(session, "ghost", "N99")
            _add_form(session, lemma, "ghost", word_token=None)
            session.commit()

            result = _patched_run(session)

        assert result["success"] is True
        assert result["lemmas_skipped"] == 0
        session.expire_all()
        ghost = session.query(Lemma).filter_by(guid="N99").one()
        # 3 / (1/7500 + 1/25000 + 1/7500) = 9783
        assert ghost.frequency_rank == 9783
    finally:
        session.close()


def test_corpus_weight_zero_excludes_corpus() -> None:
    """A corpus with weight 0 in the DB is excluded entirely."""
    session = _make_session()
    try:
        # Persist a Corpus row with weight 0
        session.add(Corpus(name="cooking", description="t", corpus_weight=0.0, enabled=True))
        session.commit()
        with patch.object(
            combined_rank,
            "get_enabled_corpus_configs",
            return_value=[
                CorpusConfig(
                    name="cooking",
                    description="t",
                    file_path="x",
                    max_words=10,
                    corpus_weight=1.0,
                )
            ],
        ):
            lemma = _add_lemma(session, "salt", "N01")
            t = _add_token_with_freq(session, "salt", "cooking", 100.0)
            _add_form(session, lemma, "salt", word_token=t)
            session.commit()

            result = _patched_run(session)

        # The zero-weight corpus contributes nothing, so despite having a
        # corpus hit the lemma is ranked purely from the tier unknown floors.
        assert "wordfreq_cooking" not in result["sources_used"]
        session.expire_all()
        scored = session.query(Lemma).filter_by(guid="N01").one()
        # 3 / (1/7500 + 1/25000 + 1/7500) = 9783, same as a lemma with no signal.
        assert scored.frequency_rank == 9783
    finally:
        session.close()
