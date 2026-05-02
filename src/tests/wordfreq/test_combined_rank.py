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

    class _DummyConfig:
        pass

    with patch.object(combined_rank, "create_session", return_value=session):
        with patch.object(session, "close"):
            return combined_rank.calculate_lemma_combined_ranks(_DummyConfig())  # type: ignore[arg-type]


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
        # salt is more frequent -> rank 1, saffron rank 2
        session.expire_all()
        salt = session.query(Lemma).filter_by(guid="N01").one()
        saffron = session.query(Lemma).filter_by(guid="N02").one()
        assert salt.frequency_rank == 1
        assert saffron.frequency_rank == 2
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
        # Single source (CEFR C1), harmonic mean = 12000
        assert scored.frequency_rank == combined_rank.CEFR_TIER_RANKS["C1"]
        assert "cefr" in result["sources_used"]
    finally:
        session.close()


def test_yle_plus_wordfreq_harmonic_mean() -> None:
    """A lemma with YLE starters (rank 200, w=1.0) + one wordfreq corpus rank 1
    (w=1.0) gets harmonic mean = 2 / (1/200 + 1/1) = 2 / 1.005 ≈ 1.99 -> 2."""
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
        # 2.0 / (1.0/1 + 1.0/200) = 2.0 / 1.005 ≈ 1.99 -> int(round(...)) = 2
        assert scored.frequency_rank == 2
        assert "cambridge_yle" in result["sources_used"]
        assert "wordfreq_cooking" in result["sources_used"]
    finally:
        session.close()


def test_lemma_with_no_signal_is_skipped() -> None:
    """Lemmas with no wordfreq rollup and no tier rows keep their existing rank (or NULL)."""
    session = _make_session()
    try:
        with patch.object(combined_rank, "get_enabled_corpus_configs", return_value=[]):
            lemma = _add_lemma(session, "ghost", "N99")
            _add_form(session, lemma, "ghost", word_token=None)
            session.commit()

            result = _patched_run(session)

        assert result["success"] is True
        assert result["lemmas_skipped"] >= 1
        session.expire_all()
        ghost = session.query(Lemma).filter_by(guid="N99").one()
        assert ghost.frequency_rank is None
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

        # No sources contributed
        assert "wordfreq_cooking" not in result["sources_used"]
        session.expire_all()
        scored = session.query(Lemma).filter_by(guid="N01").one()
        assert scored.frequency_rank is None
    finally:
        session.close()
