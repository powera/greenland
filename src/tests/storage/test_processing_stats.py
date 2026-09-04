"""Token coverage counts distinct tokens, and counts both ways of claiming one.

``tokens_with_derivative_forms`` answers "how many measured tokens does some
lemma account for?" -- the coverage question behind the missing-word work
queue.  Two things it must get right:

* A token is claimed through a ``DerivativeForm`` *or* a ``VariantForm``.
  Counting only the former reports the British spelling of a word as
  uncovered vocabulary, even though its lemma is right there.
* A token is counted once however many forms attach to it.  Joining the two
  tables and counting rows made a token with five inflections read as five
  covered tokens, which pushed ``percent_complete`` above 100.
"""

from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from storage.models import Base, DerivativeForm, Lemma, WordToken
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm
from storage.queries.stats import get_processing_stats


@pytest.fixture()
def session(tmp_path: object) -> Generator[Session, None, None]:
    import storage.models  # noqa: F401

    engine: Engine = create_engine(f"sqlite:///{tmp_path}/processing_stats.sqlite")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db_session = factory()
    yield db_session
    db_session.close()
    engine.dispose()


def _add_token(db_session: Session, text: str) -> WordToken:
    token = WordToken(token=text, language_code="en")
    db_session.add(token)
    db_session.flush()
    return token


def _add_lemma(db_session: Session, lemma_text: str) -> Lemma:
    lemma = Lemma(
        lemma_text=lemma_text,
        definition_text=f"Definition of {lemma_text}.",
        pos_type="adjective",
    )
    db_session.add(lemma)
    db_session.flush()
    return lemma


def test_a_token_with_many_forms_counts_once(session: Session) -> None:
    lemma = _add_lemma(session, "gray")
    token = _add_token(session, "gray")
    for grammatical_form in ("adjective/en_positive", "adjective/en_comparative"):
        session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text="gray",
                word_token_id=token.id,
                language_code="en",
                grammatical_form=grammatical_form,
            )
        )
    session.flush()

    stats = get_processing_stats(session)

    assert stats["total_word_tokens"] == 1
    assert stats["tokens_with_derivative_forms"] == 1
    assert stats["percent_complete"] == 100.0


def test_a_token_claimed_only_by_a_variant_is_covered(session: Session) -> None:
    """ "grey" reaches its lemma through variant_forms alone."""
    lemma = _add_lemma(session, "gray")
    variant_token = _add_token(session, "grey")
    session.add(
        VariantForm(
            lemma_id=lemma.id,
            language_code="en",
            variant_kind=VARIANT_KIND_SPELLING,
            variant_key="grey",
            grammatical_form="adjective/en_positive",
            variant_form_text="grey",
            word_token_id=variant_token.id,
            is_base_form=True,
        )
    )
    session.flush()

    stats = get_processing_stats(session)

    assert stats["tokens_with_derivative_forms"] == 1


def test_unclaimed_tokens_are_not_counted(session: Session) -> None:
    lemma = _add_lemma(session, "gray")
    claimed = _add_token(session, "gray")
    _add_token(session, "unclaimed")
    session.add(
        DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text="gray",
            word_token_id=claimed.id,
            language_code="en",
            grammatical_form="adjective/en_positive",
        )
    )
    session.flush()

    stats = get_processing_stats(session)

    assert stats["total_word_tokens"] == 2
    assert stats["tokens_with_derivative_forms"] == 1
    assert stats["percent_complete"] == 50.0


def test_one_lemma_reaching_a_token_both_ways_counts_once(session: Session) -> None:
    """A form and a variant on the same token is still one covered token."""
    lemma = _add_lemma(session, "gray")
    token = _add_token(session, "gray")
    session.add(
        DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text="gray",
            word_token_id=token.id,
            language_code="en",
            grammatical_form="adjective/en_positive",
        )
    )
    session.add(
        VariantForm(
            lemma_id=lemma.id,
            language_code="en",
            variant_kind=VARIANT_KIND_SPELLING,
            variant_key="gray",
            grammatical_form="adjective/en_positive",
            variant_form_text="gray",
            word_token_id=token.id,
            is_base_form=True,
        )
    )
    session.flush()

    stats = get_processing_stats(session)

    assert stats["tokens_with_derivative_forms"] == 1
    assert stats["percent_complete"] == 100.0
