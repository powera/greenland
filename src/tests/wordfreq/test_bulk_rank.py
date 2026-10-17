"""Parity and query-growth checks for bulk lemma ranking."""

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from storage.models.schema import Base, DerivativeForm, ExternalLexemeAnnotation, Lemma, WordToken
from storage.models.variant_form import VARIANT_KIND_ARCHAIC, VariantForm
from wordfreq.frequency import combined_rank
from wordfreq.frequency.corpus import CorpusConfig
from wordfreq.lexeme_frequency import get_bulk_lexeme_token_shares, get_token_share


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    combined_rank.clear_zipf_exponent_cache()
    with Session(engine) as connection:
        yield connection
    combined_rank.clear_zipf_exponent_cache()
    engine.dispose()


def add_lemma(session: Session, name: str, prominence: str = "common") -> Lemma:
    lemma = Lemma(
        lemma_text=name,
        definition_text=name,
        pos_type="noun",
        guid=name,
        sense_prominence=prominence,
    )
    session.add(lemma)
    session.flush()
    return lemma


def add_form(
    session: Session,
    lemma: Lemma,
    token: WordToken | None,
    language: str = "en",
    slot: str = "singular",
) -> None:
    session.add(
        DerivativeForm(
            lemma_id=lemma.id,
            word_token_id=token.id if token else None,
            derivative_form_text=lemma.lemma_text,
            language_code=language,
            grammatical_form=slot,
        )
    )
    session.flush()


def add_variant(session: Session, lemma: Lemma, token: WordToken, kind: str) -> None:
    session.add(
        VariantForm(
            lemma_id=lemma.id,
            word_token_id=token.id,
            variant_form_text=token.token,
            variant_key=token.token,
            language_code="en",
            variant_kind=kind,
            grammatical_form="singular",
        )
    )
    session.flush()


def config() -> CorpusConfig:
    return CorpusConfig(
        name="cooking",
        description="test",
        file_path="x",
        max_words=1000,
        corpus_weight=1.0,
        max_unknown_rank=7,
    )


def test_bulk_shares_and_ranks_match_single_lemma_queries(session: Session) -> None:
    token = WordToken(token="shared", language_code="en")
    session.add(token)
    session.flush()
    main = add_lemma(session, "main")
    rare = add_lemma(session, "rare", "rare")
    archaic = add_lemma(session, "archaic")
    variant_only = add_lemma(session, "variant_only")
    foreign = add_lemma(session, "foreign")
    unlinked = add_lemma(session, "unlinked")
    add_form(session, main, token)
    add_form(session, main, token, slot="plural")
    add_variant(session, main, token, VARIANT_KIND_ARCHAIC)
    add_form(session, rare, token)
    add_form(session, archaic, None)
    add_variant(session, archaic, token, VARIANT_KIND_ARCHAIC)
    add_variant(session, variant_only, token, "spelling")
    add_form(session, foreign, token, language="fr")
    add_form(session, unlinked, None)
    for position, rank in enumerate((3, 3, 11, 0, -1, None)):
        session.add(
            ExternalLexemeAnnotation(
                word_token_id=token.id,
                source="wordfreq_cooking",
                tier_name="test",
                pos_hint=str(position),
                ordinal_rank=rank,
                frequency=10.0,
            )
        )
    session.commit()
    owners = (main, rare, archaic)
    shares = get_bulk_lexeme_token_shares(session)
    assert set(shares) == {owner.id for owner in owners}
    for owner in owners:
        assert shares[owner.id][token.id] == pytest.approx(
            get_token_share(session, token.id, owner.id)
        )
    assert shares[main.id][token.id] > shares[rare.id][token.id] > shares[archaic.id][token.id]
    lemma_ids = [owner.id for owner in (main, rare, archaic, variant_only, foreign, unlinked)]
    with patch.object(combined_rank, "get_enabled_corpus_configs", return_value=[config()]):
        combined_rank._ZIPF_EXPONENT_CACHE["cooking"] = 1.4
        expected = {}
        for lemma_id in lemma_ids:
            rank = combined_rank.get_lemma_corpus_rank(session, lemma_id, "cooking", 1.4)
            if rank is not None:
                expected[lemma_id] = rank
        actual = combined_rank._build_corpus_rank_table(session, "cooking", lemma_ids, shares)
        assert actual == expected
        assert actual[rare.id] == 7  # The corpus-specific unknown-rank ceiling.
        assert set(actual) == {owner.id for owner in owners}


def query_count(session: Session) -> int:
    count = 0

    def observe(
        connection: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        nonlocal count
        if statement.lstrip().upper().startswith("SELECT"):
            count += 1

    engine = session.get_bind()
    combined_rank.clear_zipf_exponent_cache()
    event.listen(engine, "before_cursor_execute", observe)
    try:
        with patch.object(combined_rank, "get_enabled_corpus_configs", return_value=[config()]):
            result = combined_rank.calculate_lemma_combined_ranks(session, dry_run=True)
        assert result["success"]
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    return count


def test_select_count_does_not_grow_with_lemmas_or_forms(session: Session) -> None:
    def populate(start: int, stop: int) -> None:
        for index in range(start, stop):
            lemma = add_lemma(session, f"word{index}")
            token = WordToken(token=f"word{index}", language_code="en")
            session.add(token)
            session.flush()
            add_form(session, lemma, token)
            add_form(session, lemma, token, slot="plural")
            session.add(
                ExternalLexemeAnnotation(
                    word_token_id=token.id,
                    source="wordfreq_cooking",
                    tier_name="test",
                    ordinal_rank=index + 1,
                    frequency=1000.0 / (index + 1),
                )
            )
        session.commit()

    populate(0, 1)
    small = query_count(session)
    populate(1, 101)
    large = query_count(session)
    assert large == small
    assert large <= 15
    assert session.query(Lemma).filter(Lemma.frequency_rank.isnot(None)).count() == 0
