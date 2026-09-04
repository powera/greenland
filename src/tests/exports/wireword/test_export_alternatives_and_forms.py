"""What the WireWord export offers as answers, and as grammatical-form cards.

A variant is the same lemma written another way -- "grey" for "gray", "ad" for
"advertisement" -- so a learner who types one has not made a mistake.  All of
them reach the app through ``variant_forms``; ``derivative_forms`` holds
inflections, and an inflection of a variant ("greyer") is not an answer to the
headword.

The kind filter is the part worth pinning down: every kind defined today is an
acceptable answer, so the export would behave identically without it.  It is
there so that adding a kind which is *not* an answer does not silently become
one, and this test fails if the filter is dropped.

The degree-form tests cover the other direction: a Lithuanian comparative is a
card, and takes its English label from the single ``adjective/en_comparative``
slot rather than matching Lithuanian's case/number/gender slot-for-slot.
"""

from typing import Generator, List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from exports.wireword.export_wireword import (
    DEGREE_FORM_MIN_LEVEL,
    GENERIC_FORM_MIN_LEVEL,
    WirewordExporter,
    _minimum_level_for_form,
)
from storage.models import Base, Lemma
from storage.models.variant_form import (
    VARIANT_KIND_ABBREVIATION,
    VARIANT_KIND_SPELLING,
    VariantForm,
)

# A kind that is not in ACCEPTED_ANSWER_VARIANT_KINDS. Nothing writes this
# today; it stands in for a future kind that is not an acceptable answer.
UNACCEPTED_KIND = "pronunciation_respelling"


@pytest.fixture()
def db_engine(tmp_path: object) -> Generator[Engine, None, None]:
    import storage.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path}/variant_alternatives.sqlite")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(db_engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=db_engine)
    db_session = factory()
    yield db_session
    db_session.close()


def _add_lemma(db_session: Session, lemma_text: str) -> Lemma:
    lemma = Lemma(
        lemma_text=lemma_text,
        definition_text=f"Definition of {lemma_text}.",
        pos_type="adjective",
        guid=f"A02_{lemma_text}",
    )
    db_session.add(lemma)
    db_session.flush()
    return lemma


def _add_variant(
    db_session: Session,
    lemma: Lemma,
    variant_key: str,
    grammatical_form: str,
    text: str,
    *,
    kind: str = VARIANT_KIND_SPELLING,
    is_base_form: bool = False,
) -> None:
    db_session.add(
        VariantForm(
            lemma_id=lemma.id,
            language_code="en",
            variant_kind=kind,
            variant_key=variant_key,
            grammatical_form=grammatical_form,
            variant_form_text=text,
            is_base_form=is_base_form,
        )
    )
    db_session.flush()


def _fetch(db_session: Session, lemma_ids: List[int]) -> dict:
    exporter = WirewordExporter(language="lt")
    return exporter._bulk_fetch_variant_base_forms(db_session, lemma_ids)


def test_spelling_variant_base_form_is_an_alternative(session: Session) -> None:
    lemma = _add_lemma(session, "gray")
    _add_variant(session, lemma, "grey", "adjective/en_positive", "grey", is_base_form=True)

    assert _fetch(session, [lemma.id]) == {lemma.id: {"en": ["grey"]}}


def test_inflections_of_a_variant_are_not_alternatives(session: Session) -> None:
    """ "grey" answers "gray"; "greyer" does not."""
    lemma = _add_lemma(session, "gray")
    _add_variant(session, lemma, "grey", "adjective/en_positive", "grey", is_base_form=True)
    _add_variant(session, lemma, "grey", "adjective/en_comparative", "greyer")
    _add_variant(session, lemma, "grey", "adjective/en_superlative", "greyest")

    assert _fetch(session, [lemma.id]) == {lemma.id: {"en": ["grey"]}}


def test_abbreviations_reach_the_export_as_alternatives(session: Session) -> None:
    """Abbreviations are variants now, so they arrive by the same path."""
    lemma = _add_lemma(session, "advertisement")
    _add_variant(
        session,
        lemma,
        "ad",
        "noun/en_singular",
        "ad",
        kind=VARIANT_KIND_ABBREVIATION,
        is_base_form=True,
    )

    assert _fetch(session, [lemma.id]) == {lemma.id: {"en": ["ad"]}}


def test_a_kind_outside_the_accepted_set_is_not_an_alternative(session: Session) -> None:
    """The filter's whole purpose: a non-answer kind stays out of the app."""
    lemma = _add_lemma(session, "gray")
    _add_variant(
        session,
        lemma,
        "GRAY",
        "adjective/en_positive",
        "greigh",
        kind=UNACCEPTED_KIND,
        is_base_form=True,
    )

    assert _fetch(session, [lemma.id]) == {}


def test_lemma_without_variants_is_absent(session: Session) -> None:
    lemma = _add_lemma(session, "blue")

    assert _fetch(session, [lemma.id]) == {}


def test_lithuanian_degree_forms_take_their_english_label_from_the_en_slot() -> None:
    """Eight Lithuanian comparatives all mean "redder".

    Lithuanian carries case, number and gender on a comparative where English
    has one form, so the mapping collapses rather than matching slot-for-slot
    the way verbs do.
    """
    exporter = WirewordExporter(language="lt")
    english_forms = {
        7: {
            "adjective/en_comparative": "grayer",
            "adjective/en_superlative": "grayest",
        }
    }

    for slot in (
        "adjective/lt_comparative_nominative_singular_m",
        "adjective/lt_comparative_accusative_plural_f",
    ):
        assert exporter._get_english_translation_from_prefetched(english_forms, 7, slot) == "grayer"

    assert (
        exporter._get_english_translation_from_prefetched(
            english_forms, 7, "adjective/lt_superlative_nominative_plural_m"
        )
        == "grayest"
    )


def test_unmapped_languages_still_fall_back_to_a_generated_label() -> None:
    exporter = WirewordExporter(language="fr")

    assert (
        exporter._get_english_translation_from_prefetched(
            {7: {"adjective/en_comparative": "grayer"}}, 7, "adjective/fr_comparative"
        )
        is None
    )


def test_degree_cards_sit_above_the_generic_form_floor() -> None:
    """Comparison is a later concept than a plain declension."""
    assert _minimum_level_for_form("adjective/lt_comparative_nominative_singular_m") == (
        DEGREE_FORM_MIN_LEVEL
    )
    assert _minimum_level_for_form("adjective/lt_superlative_accusative_plural_f") == (
        DEGREE_FORM_MIN_LEVEL
    )
    assert _minimum_level_for_form("noun/lt_genitive_singular") == GENERIC_FORM_MIN_LEVEL
    assert _minimum_level_for_form("verb/lt_1s_present") == GENERIC_FORM_MIN_LEVEL
