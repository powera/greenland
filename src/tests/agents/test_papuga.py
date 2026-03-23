"""Tests for Papuga pronunciation coverage and queue behavior."""

from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.papuga.agent import PapugaAgent
from agents.papuga.cli import enqueue_papuga_work
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import Base, DerivativeForm, Lemma


def _build_config() -> DataSourceConfig:
    """Create a minimal Papuga config for tests."""
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=":memory:",
        model="gpt-5-mini",
    )


def test_check_missing_pronunciations_counts_partially_missing_forms() -> None:
    """Coverage mode should include forms missing either IPA or phonetic data."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="eat",
            definition_text="to consume food",
            pos_type="verb",
            guid="V00_001",
        )
        session.add(lemma)
        session.flush()

        session.add_all(
            [
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="eat",
                    language_code="en",
                    grammatical_form="infinitive",
                    is_base_form=True,
                    ipa_pronunciation="/iːt/",
                    phonetic_pronunciation=None,
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="eats",
                    language_code="en",
                    grammatical_form="third_person_singular_present",
                    is_base_form=False,
                    ipa_pronunciation=None,
                    phonetic_pronunciation="EETS",
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="ate",
                    language_code="en",
                    grammatical_form="past_tense",
                    is_base_form=False,
                    ipa_pronunciation="/eɪt/",
                    phonetic_pronunciation="AYT",
                ),
            ]
        )
        session.commit()

        agent = PapugaAgent(config=_build_config())
        with patch.object(agent, "get_session", return_value=session):
            result = agent.check_missing_pronunciations(lemma_id=lemma.id)

        assert result["total_missing"] == 2
        assert {item["word"] for item in result["missing_forms"]} == {"eat", "eats"}
    finally:
        session.close()
        engine.dispose()


def test_enqueue_papuga_work_enqueues_once_per_lemma_language() -> None:
    """Workqueue mode should enqueue lemma-level pronunciation tasks."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="run",
            definition_text="to move quickly",
            pos_type="verb",
            guid="V00_002",
        )
        session.add(lemma)
        session.flush()

        session.add_all(
            [
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="run",
                    language_code="en",
                    grammatical_form="infinitive",
                    is_base_form=True,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="runs",
                    language_code="en",
                    grammatical_form="third_person_singular_present",
                    is_base_form=False,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
            ]
        )
        session.commit()

        captured_calls = []

        class _Result:
            created = True

        def _fake_enqueue_task(db_session: Session, **kwargs: object) -> _Result:
            captured_calls.append(kwargs)
            return _Result()

        with patch("workqueue.task_queue.enqueue_task", side_effect=_fake_enqueue_task):
            results = enqueue_papuga_work(
                session=session,
                lemmas=[lemma],
                only_english=True,
                base_forms_only=False,
                dry_run=False,
            )

        assert results["enqueued"] == 1
        assert results["skipped"] == 0
        assert len(captured_calls) == 1
        assert captured_calls[0]["target_type"] == "lemma"
        assert captured_calls[0]["target_id"] == lemma.id
        assert captured_calls[0]["payload"] == {"lang_code": "en", "lemma_id": lemma.id}
    finally:
        session.close()
        engine.dispose()
