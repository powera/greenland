"""Genys' ``--tags`` wiring, from the CLI flag through to the created lemma.

Tags applied to a corpus run travel a long way with no visible error if a link
breaks: the CLI flag has to reach ``process_document``, the agent has to write
the tags onto each ``PendingImport``, and approval has to carry them onto the
lemma the import becomes. A break anywhere leaves an untagged database that
looks exactly like a run nobody tagged, so each hop is pinned below.

No live LLM call is made.
"""

from typing import Any, Dict, List
from unittest.mock import patch

from sqlalchemy.orm import Session

from agents.genys.agent import GenysAgent
from sentences.translate_and_decompose import DecomposedLanguage, TranslateAndDecomposeResult
from storage.backend.config import DataSourceConfig
from storage.crud.lemma_tags import read_pending_import_tags, read_tags
from storage.models.imports import PendingImport
from storage.models.schema import Lemma
from tests.sentences.candidate_lookup_fixture import build_test_engine, seed_test_database


def _agent() -> GenysAgent:
    return GenysAgent(config=DataSourceConfig(debug=False))


def _unknown_words() -> List[Dict[str, Any]]:
    """A Phase-3 word list of words absent from the seeded database."""
    return [
        {
            "position": 0,
            "surface_form": "probate",
            "english_gloss": "probate",
            "part_of_speech": "noun",
            "grammatical_form": "noun/en_singular",
            "lemma_guid": "NONE",
            "lemma": "probate",
        },
        {
            "position": 1,
            "surface_form": "codicil",
            "english_gloss": "codicil",
            "part_of_speech": "noun",
            "grammatical_form": "noun/en_singular",
            "lemma_guid": "NONE",
            "lemma": "codicil",
        },
    ]


def _run_with_tags(session: Session, tags: Any) -> List[PendingImport]:
    """Run one sentence through genys with ``tags`` and return the staged rows."""
    pipeline_result = TranslateAndDecomposeResult(
        source_sentence="Probate codicil.",
        source_language="en",
        translations={"en": "Probate codicil."},
        decompositions={
            "en": DecomposedLanguage(
                language_code="en",
                translation="Probate codicil.",
                words=_unknown_words(),
            )
        },
    )

    agent = _agent()
    with (
        patch.object(agent, "get_session", return_value=session),
        patch.object(agent, "get_llm_client", return_value=object()),
        patch("agents.genys.agent.translate_and_decompose", return_value=pipeline_result),
        patch.object(GenysAgent, "split_sentences", return_value=["Probate codicil."]),
        patch("pathlib.Path.read_text", return_value="Probate codicil."),
    ):
        kwargs: Dict[str, Any] = {
            "input_path": "iowa_633.txt",
            "document_language": "en",
            "throttle_seconds": 0,
        }
        if tags is not None:
            kwargs["tags"] = tags
        agent.process_document(**kwargs)

    return session.query(PendingImport).order_by(PendingImport.english_word).all()


def test_tags_are_written_to_every_staged_import() -> None:
    """The whole point of the flag: staged words carry the corpus tag."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        staged = _run_with_tags(session, ["legal"])

        assert staged, "expected the unknown words to be staged"
        for pending in staged:
            assert read_pending_import_tags(pending) == ["legal"]


def test_tags_are_normalized_before_staging() -> None:
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        staged = _run_with_tags(session, ["Legal", " LEGAL ", "archaic"])

        assert read_pending_import_tags(staged[0]) == ["archaic", "legal"]


def test_no_tags_leaves_the_column_null() -> None:
    """An untagged run must not write "[]" -- NULL is the no-tags encoding."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        staged = _run_with_tags(session, None)

        assert staged, "expected the unknown words to be staged"
        for pending in staged:
            assert pending.tags is None
            assert read_pending_import_tags(pending) == []


def test_approval_carries_tags_onto_the_lemma() -> None:
    """Tags must survive the pending-import -> lemma hop.

    ``approve_pending_import`` deletes the pending row, so the tags have to be
    read before that and applied after the lemma exists.
    """
    from words.pending_imports import approval as staging

    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)

        pending = PendingImport(
            english_word="probate",
            definition="the judicial process of validating a will",
            disambiguation_translation="probate",
            disambiguation_language="en",
            pos_type="noun",
            pos_subtype="process_event",
            tags='["legal"]',
            source="genys/iowa_633.txt",
        )
        session.add(pending)
        session.commit()
        pending_id = pending.id

        # process_word() is the LLM-backed lemma creation; stand in for it by
        # inserting the lemma the real path would have produced.
        def fake_process_word(*args: Any, **kwargs: Any) -> bool:
            session.add(
                Lemma(
                    lemma_text="probate",
                    definition_text="the judicial process of validating a will",
                    pos_type="noun",
                    pos_subtype="process_event",
                )
            )
            session.flush()
            return True

        with (
            patch("wordfreq.translation.word_processing.process_word", fake_process_word),
            patch.object(staging, "LinguisticClient"),
            patch.object(staging, "has_active_strong_synonym_candidate", return_value=False),
        ):
            result = staging.approve_pending_import(
                session=session,
                pending_import_id=pending_id,
                data_source_config=DataSourceConfig(debug=False),
            )

        assert result.get("success"), result
        lemma = session.query(Lemma).filter(Lemma.lemma_text == "probate").one()
        assert read_tags(lemma) == ["legal"]
