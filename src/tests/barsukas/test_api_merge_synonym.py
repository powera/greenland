"""Tests for the Barsukas synonym-merge API endpoint."""

from typing import Tuple

from flask.testing import FlaskClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from storage.models import DerivativeForm, GuidTombstone, Lemma, LemmaTranslation


def _add_merge_pair(session: Session, *, synonym_pos_type: str = "adverb") -> Tuple[Lemma, Lemma]:
    """Add a pair of lemmas with three matching non-English translations."""
    main_lemma = Lemma(
        lemma_text="obviously",
        definition_text="in a clear or obvious way",
        pos_type="adverb",
        pos_subtype="manner",
        guid="R01_001",
        confidence=0.95,
        verified=True,
    )
    synonym_lemma = Lemma(
        lemma_text="evidently",
        definition_text="in a way that is plainly seen or understood",
        pos_type=synonym_pos_type,
        pos_subtype="manner",
        guid="R01_002",
        confidence=0.95,
        verified=True,
    )
    session.add_all([main_lemma, synonym_lemma])
    session.flush()
    translations = [
        LemmaTranslation(lemma_id=main_lemma.id, language_code="fr", translation="évidemment"),
        LemmaTranslation(lemma_id=synonym_lemma.id, language_code="fr", translation="Évidemment"),
        LemmaTranslation(lemma_id=main_lemma.id, language_code="es", translation="obviamente"),
        LemmaTranslation(lemma_id=synonym_lemma.id, language_code="es", translation="obviamente"),
        LemmaTranslation(lemma_id=main_lemma.id, language_code="lt", translation="akivaizdžiai"),
        LemmaTranslation(lemma_id=synonym_lemma.id, language_code="lt", translation="akivaizdžiai"),
        LemmaTranslation(lemma_id=main_lemma.id, language_code="zh", translation="显然"),
        LemmaTranslation(lemma_id=synonym_lemma.id, language_code="zh", translation="明显地"),
    ]
    session.add_all(translations)
    session.commit()
    return main_lemma, synonym_lemma


def test_merge_synonym_tombstones_adds_synonyms_and_deletes_source(
    client: FlaskClient, db_engine: Engine
) -> None:
    """A valid synonym merge tombstones and deletes the synonym lemma."""
    factory = sessionmaker(bind=db_engine)
    session = factory()
    try:
        main_lemma, synonym_lemma = _add_merge_pair(session)
        main_id = main_lemma.id
        synonym_id = synonym_lemma.id
    finally:
        session.close()

    response = client.post(
        "/api/v1/lemma/R01_001/merge-synonym/R01_002",
        json={"changed_by": "pytest", "notes": "merge evidently into obviously"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["main_guid"] == "R01_001"
    assert payload["data"]["removed_guid"] == "R01_002"
    assert {entry["language_code"] for entry in payload["data"]["matched_translations"]} == {
        "fr",
        "es",
        "lt",
    }

    verify_session = factory()
    try:
        assert verify_session.query(Lemma).filter(Lemma.id == synonym_id).first() is None
        tombstone = (
            verify_session.query(GuidTombstone).filter(GuidTombstone.guid == "R01_002").one()
        )
        assert tombstone.replacement_guid == "R01_001"
        assert tombstone.reason == "synonym_merge"
        assert tombstone.lemma_id == synonym_id

        synonym_rows = (
            verify_session.query(DerivativeForm)
            .filter(DerivativeForm.lemma_id == main_id)
            .order_by(DerivativeForm.language_code)
            .all()
        )
        synonym_by_language = {row.language_code: row.derivative_form_text for row in synonym_rows}
        assert synonym_by_language == {
            "en": "evidently",
            "es": "obviamente",
            "fr": "Évidemment",
            "lt": "akivaizdžiai",
            "zh": "明显地",
        }
    finally:
        verify_session.close()


def test_merge_synonym_rejects_part_of_speech_mismatch(
    client: FlaskClient, db_engine: Engine
) -> None:
    """The internal guard rejects merges across part-of-speech values."""
    factory = sessionmaker(bind=db_engine)
    session = factory()
    try:
        _add_merge_pair(session, synonym_pos_type="adjective")
    finally:
        session.close()

    response = client.post("/api/v1/lemma/R01_001/merge-synonym/R01_002")

    assert response.status_code == 400
    payload = response.get_json()
    assert "different part-of-speech" in payload["error"]
