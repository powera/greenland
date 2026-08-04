"""``translate_sentence`` must hand a dialog line its surrounding turns.

Translation runs one call per sentence. Without context, an elliptical reply
("They are.") reaches the model with nothing to resolve it against, and every
language produced a stranded copula. These tests pin that the context actually
arrives at the Phase-1 call, and that a standalone sentence is unaffected --
they assert on the prompt the pipeline built, so no live call is involved.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import patch

from sqlalchemy.orm import Session

from sentences.translation import translate_sentence
from storage.crud.conversation import add_conversation, add_conversation_sentence
from tests.sentences.candidate_lookup_fixture import (
    add_test_sentence,
    build_test_engine,
    seed_test_database,
)


def _capture_phase1_context(session: Session, sentence_id: int) -> Optional[str]:
    """Run translate_sentence with both LLM phases stubbed; return the context."""
    captured: Dict[str, Optional[str]] = {"conversation_context": None}

    def fake_translate(**kwargs: Any) -> Dict[str, str]:
        captured["conversation_context"] = kwargs.get("conversation_context")
        return {lang: f"[{lang}]" for lang in kwargs["target_languages"]}

    def fake_decompose(**kwargs: Any) -> Any:
        return kwargs["result"]

    with (
        patch("sentences.translate_and_decompose.translate_sentence_text", fake_translate),
        patch(
            "sentences.translate_and_decompose.decompose_with_existing_translations", fake_decompose
        ),
    ):
        translate_sentence(sentence_id, ["lt", "fr"], session, source_language="en")

    return captured["conversation_context"]


def _store_dialog(session: Session, lines: List[str], speakers: List[str]) -> List[int]:
    """Store a dialog as one Sentence per line; return the sentence ids."""
    conversation = add_conversation(session, title="At the playground")
    conversation.scene_prompt = "two children meeting at a playground"

    sentence_ids: List[int] = []
    for position, (speaker, text) in enumerate(zip(speakers, lines)):
        sentence = add_test_sentence(session, {"en": text})
        add_conversation_sentence(
            session,
            conversation=conversation,
            sentence=sentence,
            position=position,
            speaker=speaker,
            turn_index=position,
        )
        sentence_ids.append(sentence.id)
    session.flush()
    return sentence_ids


def test_dialog_line_receives_its_antecedent() -> None:
    """The reason for the whole change: "They are." must see "They look happy."."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence_ids = _store_dialog(
            session,
            ["They look happy.", "They are.", "Ben is usually shy."],
            ["Ben", "Maria", "Ben"],
        )

        context = _capture_phase1_context(session, sentence_ids[1])

        assert context is not None
        assert "They look happy." in context
        assert "Speaker of this line: Maria" in context
        assert "two children meeting at a playground" in context


def test_standalone_sentence_gets_no_context() -> None:
    """A non-dialog sentence keeps the ordinary prompt, with no empty scaffolding."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "The child found a green ball."})

        assert _capture_phase1_context(session, sentence.id) is None
