"""Genys' opt-in Phase-4 (Universal Dependencies) wiring.

Two things can silently break here and neither shows up as an error: the CLI
flag failing to reach the pipeline (Phase 4 never runs), and the storage path
failing to pass the annotations to ``add_sentence_word`` (Phase 4 runs, is paid
for, and the results are dropped on the floor). Both are pinned below without
any live LLM call.
"""

from typing import Any, Dict, List
from unittest.mock import patch

from sqlalchemy.orm import Session

from agents.genys.agent import GenysAgent
from langtools.ud_relations import ROOT_HEAD_POSITION
from storage.backend.config import DataSourceConfig
from storage.models.schema import Sentence, SentenceWord
from tests.sentences.candidate_lookup_fixture import build_test_engine, seed_test_database


def _annotated_words() -> List[Dict[str, Any]]:
    """A Phase-3 word list carrying Phase-4 annotations, as genys would see it."""
    return [
        {
            "position": 0,
            "surface_form": "dogs",
            "english_gloss": "dogs",
            "part_of_speech": "noun",
            "grammatical_form": "noun/en_plural",
            "lemma_guid": "NONE",
            "lemma": "dog",
            "ud_relation": "nsubj",
            "ud_head_position": 1,
        },
        {
            "position": 1,
            "surface_form": "bark",
            "english_gloss": "bark",
            "part_of_speech": "verb",
            "grammatical_form": "verb/en_present",
            "lemma_guid": "NONE",
            "lemma": "bark",
            "ud_relation": "root",
            "ud_head_position": ROOT_HEAD_POSITION,
        },
    ]


def _agent() -> GenysAgent:
    return GenysAgent(config=DataSourceConfig(debug=False))


def test_annotate_dependencies_flag_reaches_the_pipeline() -> None:
    """The CLI flag must be forwarded, or Phase 4 silently never runs."""
    captured: Dict[str, Any] = {}

    def fake_pipeline(**kwargs: Any) -> Any:
        captured["annotate_dependencies"] = kwargs.get("annotate_dependencies")
        raise RuntimeError("stop after capturing")

    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        agent = _agent()

        with (
            patch.object(agent, "get_session", return_value=session),
            patch.object(agent, "get_llm_client", return_value=object()),
            patch("agents.genys.agent.translate_and_decompose", fake_pipeline),
            patch.object(GenysAgent, "split_sentences", return_value=["Dogs bark."]),
            patch("pathlib.Path.read_text", return_value="Dogs bark."),
        ):
            try:
                agent.process_document(
                    input_path="doc.txt",
                    document_language="en",
                    annotate_dependencies=True,
                )
            except RuntimeError:
                pass

    assert captured["annotate_dependencies"] is True


def test_estimated_calls_accounts_for_the_extra_phase() -> None:
    """Phase 4 is a third call per sentence; the estimate drives the cost prompt."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        agent = _agent()

        def estimate(annotate: bool, sentence_count: int) -> int:
            sentences = ["Dogs bark.", "Cats sleep."][:sentence_count]
            with (
                patch.object(agent, "get_session", return_value=session),
                patch.object(agent, "get_llm_client", return_value=object()),
                patch.object(GenysAgent, "split_sentences", return_value=sentences),
                patch("pathlib.Path.read_text", return_value=" ".join(sentences)),
            ):
                stats = agent.process_document(
                    input_path="doc.txt",
                    document_language="en",
                    annotate_dependencies=annotate,
                )
            return int(stats["estimated_llm_calls"])

        # sentence_count=0 returns before any LLM call, so the estimate — which
        # is computed up front — is readable without stubbing the pipeline.
        assert estimate(False, 0) == 0
        assert estimate(True, 0) == 0

        # Two sentences: 2 phases each, or 3 with dependency annotation.
        assert estimate(False, 2) == 4
        assert estimate(True, 2) == 6


def _store_and_read_words(
    session: Session, english_words: List[Dict[str, Any]]
) -> List[SentenceWord]:
    GenysAgent._store_sentence(
        session,
        source_name="doc.txt",
        document_language="en",
        sentence_text="Dogs bark.",
        translations={},
        english_words=english_words,
    )
    session.commit()
    sentence = session.query(Sentence).order_by(Sentence.id.desc()).first()
    assert sentence is not None
    return (
        session.query(SentenceWord)
        .filter_by(sentence_id=sentence.id, language_code="en")
        .order_by(SentenceWord.position)
        .all()
    )


def test_ud_annotations_are_persisted_to_sentence_words() -> None:
    """Phase-4 output must reach the DB, not be computed and dropped."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)

        words = _store_and_read_words(session, _annotated_words())

        assert [w.ud_relation for w in words] == ["nsubj", "root"]
        assert [w.ud_head_position for w in words] == [1, ROOT_HEAD_POSITION]


def test_unannotated_words_store_null_ud_fields() -> None:
    """Without Phase 4 the columns stay NULL rather than picking up junk."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)

        plain_words = [
            {key: value for key, value in word.items() if not key.startswith("ud_")}
            for word in _annotated_words()
        ]
        words = _store_and_read_words(session, plain_words)

        assert all(w.ud_relation is None for w in words)
        assert all(w.ud_head_position is None for w in words)
