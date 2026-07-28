"""Which languages ``translate_sentence`` sends to Phase 3.

English is the anchor language for candidate lookup and pending-import
staging, so a sentence with no English SentenceWord rows must get them. An
earlier version gated that on ``source_language != "en"`` — mirroring the
Phase-1 "don't retranslate the source into itself" rule into Phase 3, where it
does not apply, since Phase 3 needs only text and an English-source sentence
already has it. The effect was that English-source sentences never received
English words at all. These tests pin the language set instead of the LLM
output, so no live call is involved.
"""

from typing import Any, Dict, List, Sequence
from unittest.mock import patch

from sqlalchemy.orm import Session

from sentences.translation import translate_sentence
from storage.models.schema import SentenceWord
from tests.sentences.candidate_lookup_fixture import (
    add_test_sentence,
    build_test_engine,
    seed_test_database,
)


def _run_and_capture_decompose_languages(
    session: Session,
    sentence_id: int,
    target_languages: List[str],
    *,
    source_language: str = "en",
) -> Sequence[str]:
    """Run translate_sentence with both LLM phases stubbed; return Phase-3 langs."""
    captured: Dict[str, Sequence[str]] = {}

    def fake_translate(**kwargs: Any) -> Dict[str, str]:
        return {lang: f"[{lang}]" for lang in kwargs["target_languages"]}

    def fake_decompose(**kwargs: Any) -> Any:
        captured["languages"] = list(kwargs["decompose_languages"])
        return kwargs["result"]

    with (
        patch("sentences.translate_and_decompose.translate_sentence_text", fake_translate),
        patch(
            "sentences.translate_and_decompose.decompose_with_existing_translations", fake_decompose
        ),
    ):
        translate_sentence(
            sentence_id,
            target_languages,
            session,
            source_language=source_language,
        )

    return captured["languages"]


def test_english_source_sentence_still_decomposes_english() -> None:
    """The regression: an en-source sentence must not be denied English words."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "The child found a green ball."})

        languages = _run_and_capture_decompose_languages(
            session, sentence.id, ["es", "fr", "zh", "lt"]
        )

        assert "en" in languages
        for target in ("es", "fr", "zh", "lt"):
            assert target in languages


def test_non_english_source_sentence_also_decomposes_english() -> None:
    """The behavior that already worked must keep working."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence = add_test_sentence(
            session, {"en": "The child found a green ball.", "lt": "Vaikas rado žalią kamuolį."}
        )

        languages = _run_and_capture_decompose_languages(
            session, sentence.id, ["es", "fr"], source_language="lt"
        )

        assert "en" in languages


def test_english_not_re_decomposed_when_it_already_has_words() -> None:
    """include_english is about missing rows; existing English words are left alone."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "The child found a green ball."})
        session.add(
            SentenceWord(
                sentence_id=sentence.id,
                language_code="en",
                position=0,
                part_of_speech="noun",
                english_text="child",
                target_language_text="child",
            )
        )
        session.commit()

        languages = _run_and_capture_decompose_languages(session, sentence.id, ["es", "fr"])

        assert "en" not in languages
