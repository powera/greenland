"""Tests for wordfreq.frequency.combined_rank — weighted harmonic mean over
lexeme rollups + Cambridge YLE + CEFR tier signals."""

from __future__ import annotations

from typing import Iterator, Optional
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


@pytest.fixture(autouse=True)
def _isolate_zipf_exponent_cache() -> Iterator[None]:
    """Keep one test's fitted exponent out of the next one's database.

    The cache is keyed by corpus name alone, which is right in production (a
    process reads one database) but wrong here, where every test builds a
    fresh in-memory database that reuses the name "cooking".
    """
    combined_rank.clear_zipf_exponent_cache()
    yield
    combined_rank.clear_zipf_exponent_cache()


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
    ordinal_rank: Optional[int] = None,
) -> WordToken:
    """Add a token annotated for one corpus.

    Scoring reads ``ordinal_rank`` -- the corpus's own rank for that surface
    form. Leaving it None models a token the corpus scored but did not rank,
    which contributes nothing to the lemma's corpus rank.
    """
    token = WordToken(token=token_text, language_code="en")
    session.add(token)
    session.flush()
    session.add(
        ExternalLexemeAnnotation(
            word_token_id=token.id,
            source=f"wordfreq_{corpus_name}",
            tier_name="r1-50",
            frequency=frequency,
            ordinal_rank=ordinal_rank,
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


def test_spread_out_paradigm_beats_one_common_form() -> None:
    """Which lemma wins is decided by combining its forms, not by its best one.

    ``spread`` is never the most common word in the corpus, but three moderately
    common forms make it a more common *lexeme* than ``peak``, whose single good
    form is followed by two rare ones. Asserting the comparison this way round
    means the test fails if the combination is dropped for ``min()`` or for the
    best form alone -- both of which would rank ``peak`` first.
    """
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
            spread = _add_lemma(session, "spread", "N01")
            peak = _add_lemma(session, "peak", "N02")
            for text, rank in (("spread", 1200), ("spreads", 1400), ("spreading", 1600)):
                token = _add_token_with_freq(session, text, "cooking", 1.0, ordinal_rank=rank)
                _add_form(session, spread, text, word_token=token)
            for text, rank in (("peak", 1100), ("peaks", 9000), ("peaking", 9500)):
                token = _add_token_with_freq(session, text, "cooking", 1.0, ordinal_rank=rank)
                _add_form(session, peak, text, word_token=token)
            session.commit()

            result = _patched_run(session)

        assert result["success"] is True
        session.expire_all()
        spread_row = session.query(Lemma).filter_by(guid="N01").one()
        peak_row = session.query(Lemma).filter_by(guid="N02").one()

        # peak owns the single best-ranked form (1100 vs 1200), so anything
        # that looked only at the best form would put it ahead instead.
        assert spread_row.frequency_rank is not None
        assert peak_row.frequency_rank is not None
        assert spread_row.frequency_rank < peak_row.frequency_rank
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
            t_cat = _add_token_with_freq(session, "cat", "cooking", 999.0, ordinal_rank=1)
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


# --- Token ranks -------------------------------------------------------------
#
# calculate_token_combined_ranks writes a dense ordinal, so these assert on the
# ordering (rank 1, 2, 3...) rather than on a score, which is the property the
# callers rely on.


def _corpus_configs(*names: str) -> list[CorpusConfig]:
    return [
        CorpusConfig(
            name=name,
            description="t",
            file_path="x",
            max_words=1000,
            corpus_weight=1.0,
            max_unknown_rank=5000,
        )
        for name in names
    ]


def _annotate(
    session: Session,
    token: WordToken,
    corpus_name: str,
    ordinal_rank: Optional[int],
    frequency: float = 100.0,
) -> None:
    session.add(
        ExternalLexemeAnnotation(
            word_token_id=token.id,
            source=f"wordfreq_{corpus_name}",
            tier_name="r1-50",
            frequency=frequency,
            ordinal_rank=ordinal_rank,
        )
    )
    session.flush()


def _add_bare_token(session: Session, text: str, language_code: str = "en") -> WordToken:
    token = WordToken(token=text, language_code=language_code)
    session.add(token)
    session.flush()
    return token


def test_token_ranks_are_dense_ordinals_ordered_by_corpus_rank() -> None:
    """The written rank is a position 1..N, not the underlying score."""
    session = _make_session()
    try:
        with patch.object(
            combined_rank, "get_enabled_corpus_configs", return_value=_corpus_configs("cooking")
        ):
            common = _add_bare_token(session, "salt")
            middling = _add_bare_token(session, "paprika")
            rare = _add_bare_token(session, "asafoetida")
            _annotate(session, common, "cooking", 3)
            _annotate(session, middling, "cooking", 40)
            _annotate(session, rare, "cooking", 900)
            session.commit()

            result = combined_rank.calculate_token_combined_ranks(session)

        assert result["success"] is True
        assert result["tokens_scored"] == 3
        session.expire_all()
        assert common.frequency_rank == 1
        assert middling.frequency_rank == 2
        assert rare.frequency_rank == 3
    finally:
        session.close()


def test_token_absent_from_a_corpus_takes_the_unknown_floor() -> None:
    """A word common in one corpus still loses to one common in both."""
    session = _make_session()
    try:
        with patch.object(
            combined_rank,
            "get_enabled_corpus_configs",
            return_value=_corpus_configs("cooking", "science"),
        ):
            both = _add_bare_token(session, "water")
            _annotate(session, both, "cooking", 10)
            _annotate(session, both, "science", 10)

            one_only = _add_bare_token(session, "saute")
            _annotate(session, one_only, "cooking", 5)
            session.commit()

            combined_rank.calculate_token_combined_ranks(session)

        session.expire_all()
        # "saute" ranks better in cooking, but is absent from science and takes
        # that corpus's floor, so the word both corpora attest wins.
        assert both.frequency_rank == 1
        assert one_only.frequency_rank == 2
    finally:
        session.close()


def test_token_ranks_ignore_tier_annotations() -> None:
    """Tier sources are not corpora and must not contribute to a token rank."""
    session = _make_session()
    try:
        with patch.object(
            combined_rank, "get_enabled_corpus_configs", return_value=_corpus_configs("cooking")
        ):
            tiered = _add_bare_token(session, "apple")
            session.add(
                ExternalLexemeAnnotation(
                    word_token_id=tiered.id,
                    source="cambridge_yle",
                    tier_name="starters",
                    frequency=None,
                    ordinal_rank=None,
                )
            )
            corpus_word = _add_bare_token(session, "zucchini")
            _annotate(session, corpus_word, "cooking", 700)
            session.flush()
            session.commit()

            result = combined_rank.calculate_token_combined_ranks(session)

        assert result["corpora_used"] == ["cooking"]
        session.expire_all()
        # The YLE row gives "apple" no corpus evidence at all, so it falls to
        # the unknown floor and lands behind a genuinely-ranked corpus word.
        assert corpus_word.frequency_rank == 1
        assert tiered.frequency_rank == 2
    finally:
        session.close()


def test_token_ranks_are_language_scoped() -> None:
    """Ranking English leaves another language's tokens untouched."""
    session = _make_session()
    try:
        with patch.object(
            combined_rank, "get_enabled_corpus_configs", return_value=_corpus_configs("cooking")
        ):
            english = _add_bare_token(session, "salt")
            _annotate(session, english, "cooking", 3)
            lithuanian = _add_bare_token(session, "druska", language_code="lt")
            session.commit()

            result = combined_rank.calculate_token_combined_ranks(session)

        assert result["tokens_scored"] == 1
        session.expire_all()
        assert english.frequency_rank == 1
        assert lithuanian.frequency_rank is None
    finally:
        session.close()


def test_token_rank_dry_run_writes_nothing() -> None:
    session = _make_session()
    try:
        with patch.object(
            combined_rank, "get_enabled_corpus_configs", return_value=_corpus_configs("cooking")
        ):
            token = _add_bare_token(session, "salt")
            _annotate(session, token, "cooking", 3)
            session.commit()

            result = combined_rank.calculate_token_combined_ranks(session, dry_run=True)

        assert result["dry_run"] is True
        assert result["tokens_updated"] == 1
        session.expire_all()
        assert token.frequency_rank is None
    finally:
        session.close()


def test_token_ranks_are_stable_across_reruns() -> None:
    """A rerun over unchanged data updates nothing (ties break on token text)."""
    session = _make_session()
    try:
        with patch.object(
            combined_rank, "get_enabled_corpus_configs", return_value=_corpus_configs("cooking")
        ):
            for text in ("alpha", "beta", "gamma", "delta"):
                _add_bare_token(session, text)
            ranked = _add_bare_token(session, "salt")
            _annotate(session, ranked, "cooking", 3)
            session.commit()

            first = combined_rank.calculate_token_combined_ranks(session)
            second = combined_rank.calculate_token_combined_ranks(session)

        assert first["tokens_updated"] == 5
        assert second["tokens_updated"] == 0
    finally:
        session.close()
