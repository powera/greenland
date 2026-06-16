"""Tests for pending import synonym review routes."""

from flask.testing import FlaskClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from agents.dramblys.synonym_screening import has_active_strong_synonym_candidate
from storage.models import DerivativeForm, Lemma, PendingImport, PendingImportSynonymCandidate


def _add_pending_with_candidate(session: Session) -> tuple[PendingImport, Lemma]:
    lemma = Lemma(
        lemma_text="fast",
        definition_text="moving or able to move quickly",
        pos_type="adverb",
        pos_subtype="manner",
        guid="R88_001",
        confidence=0.95,
        verified=True,
    )
    pending = PendingImport(
        english_word="speedily",
        definition="quickly; with speed",
        disambiguation_translation="greitai",
        disambiguation_language="lt",
        pos_type="adverb",
        pos_subtype="manner",
        source="pytest",
    )
    session.add_all([lemma, pending])
    session.flush()
    candidate = PendingImportSynonymCandidate(
        pending_import_id=pending.id,
        lemma_id=lemma.id,
        candidate_text="fast",
        same_pos=True,
        llm_synonym_category="near",
        llm_synonym_score=0.9,
        matched_translation_count=3,
        matched_translation_languages='["lt", "fr", "es"]',
        candidate_translations='{"lt": "greitai"}',
        explanation="Close synonym for this sense.",
        is_strong=True,
        status="active",
    )
    session.add(candidate)
    session.commit()
    return pending, lemma


def test_detail_disables_approval_when_strong_candidate_exists(
    client: FlaskClient, db_engine: Engine
) -> None:
    factory = sessionmaker(bind=db_engine)
    session = factory()
    try:
        pending, _lemma = _add_pending_with_candidate(session)
        pending_id = pending.id
    finally:
        session.close()

    response = client.get(f"/pending-imports/{pending_id}/detail")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Strong synonym candidates exist" in html
    assert "Resolve synonym candidates first" in html
    assert "Use As Synonym" in html


def test_use_synonym_adds_form_and_removes_pending(client: FlaskClient, db_engine: Engine) -> None:
    factory = sessionmaker(bind=db_engine)
    session = factory()
    try:
        pending, lemma = _add_pending_with_candidate(session)
        pending_id = pending.id
        lemma_id = lemma.id
        candidate_id = pending.synonym_candidates[0].id
    finally:
        session.close()

    response = client.post(f"/pending-imports/{pending_id}/use-synonym/{candidate_id}")

    assert response.status_code == 302
    verify_session = factory()
    try:
        assert (
            verify_session.query(PendingImport).filter(PendingImport.id == pending_id).first()
            is None
        )
        synonym_form = (
            verify_session.query(DerivativeForm)
            .filter(
                DerivativeForm.lemma_id == lemma_id,
                DerivativeForm.language_code == "en",
                DerivativeForm.derivative_form_text == "speedily",
                DerivativeForm.grammatical_form == "synonym",
            )
            .one()
        )
        assert synonym_form.is_base_form is False
    finally:
        verify_session.close()


def test_create_anyway_ignores_candidates(client: FlaskClient, db_engine: Engine) -> None:
    factory = sessionmaker(bind=db_engine)
    session = factory()
    try:
        pending, _lemma = _add_pending_with_candidate(session)
        pending_id = pending.id
    finally:
        session.close()

    response = client.post(f"/pending-imports/{pending_id}/create-anyway")

    assert response.status_code == 302
    verify_session = factory()
    try:
        assert has_active_strong_synonym_candidate(verify_session, pending_id) is False
        pending_after = (
            verify_session.query(PendingImport).filter(PendingImport.id == pending_id).one()
        )
        assert pending_after.synonym_candidates[0].status == "ignored"
    finally:
        verify_session.close()
