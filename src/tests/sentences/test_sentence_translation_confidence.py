"""Sentence translations gated on the model's per-language confidence.

Phase 1 asks each language for ``{translation, confidence}``; an answer below
the floor is recorded in uncertain_llm_results (keyed on the sentence) rather
than stored, later runs leave that language out, and any stored translation
clears the record.  The LLM phases are stubbed.
"""

from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import patch

from sqlalchemy.orm import Session

from sentences.translate_and_decompose import (
    Phase1Answer,
    interpret_phase1,
    interpret_phase1_confidences,
)
from sentences.translation import translate_sentence
from sentences.translation_coverage import find_sentences_needing_translations
from storage.crud.sentence_translation import (
    get_sentence_translation,
    set_sentence_translation,
    uncertain_sentence_languages,
    update_sentence_translation,
)
from storage.crud.uncertain_llm_result import get_uncertain_llm_result
from storage.models.schema import Lemma, Sentence, SentenceWord
from storage.models.uncertain_llm_result import TOPIC_TRANSLATION
from tests.sentences.candidate_lookup_fixture import (
    add_test_sentence,
    build_test_engine,
    seed_test_database,
)

_MODEL = "gpt-6-luna"


def _sentence(session: Session, translations: Dict[str, str]) -> Sentence:
    seed_test_database(session)
    return add_test_sentence(session, translations)


def _run(
    session: Session,
    sentence_id: int,
    target_languages: List[str],
    confidences: Dict[str, float],
    *,
    retry_uncertain: bool = False,
) -> Dict[str, Sequence[str]]:
    """Run translate_sentence with both LLM phases stubbed; return what each phase saw."""
    captured: Dict[str, Sequence[str]] = {}

    def fake_translate(**kwargs: Any) -> Phase1Answer:
        captured["phase1"] = list(kwargs["target_languages"])
        return Phase1Answer(
            {lang: f"[{lang}]" for lang in kwargs["target_languages"]},
            {lang: confidences.get(lang, 0.95) for lang in kwargs["target_languages"]},
        )

    def fake_decompose(**kwargs: Any) -> Any:
        captured["phase3"] = sorted(kwargs["translations"])
        return kwargs["result"]

    with (
        patch("sentences.translate_and_decompose.translate_sentence_text_rated", fake_translate),
        patch(
            "sentences.translate_and_decompose.decompose_with_existing_translations", fake_decompose
        ),
    ):
        translate_sentence(
            sentence_id,
            target_languages,
            session,
            model=_MODEL,
            retry_uncertain=retry_uncertain,
        )
    return captured


def _text(session: Session, sentence_id: int, language_code: str) -> Optional[str]:
    row = get_sentence_translation(session, sentence_id, language_code)
    return row.translation_text if row is not None else None


def test_phase1_reads_rated_and_bare_answers() -> None:
    data = {"lt": {"translation": " Labas ", "confidence": 0.4}, "fr": "Bonjour", "zh": ""}

    assert interpret_phase1(data, ["lt", "fr", "zh"]) == {"lt": "Labas", "fr": "Bonjour"}
    # A bare string predates the confidence field: left out, so stored ungated.
    assert interpret_phase1_confidences(data, ["lt", "fr", "zh"]) == {"lt": 0.4}


def test_set_sentence_translation_gates_and_keeps_existing_text() -> None:
    engine = build_test_engine()
    with Session(engine) as session:
        sentence = _sentence(session, {"en": "The child found a ball.", "lt": "Vaikas rado."})

        result = set_sentence_translation(
            session, sentence.id, "lt", "Vaikas surado kamuolį.", confidence=0.3, model=_MODEL
        )

        assert result is None
        assert _text(session, sentence.id, "lt") == "Vaikas rado."
        row = get_uncertain_llm_result(session, TOPIC_TRANSLATION, "lt", sentence_id=sentence.id)
        assert row is not None
        assert row.note == f"{_MODEL} leaned Vaikas surado kamuolį. (0.30)"

        set_sentence_translation(session, sentence.id, "lt", "Vaikas rado kamuolį.", confidence=0.9)

        assert _text(session, sentence.id, "lt") == "Vaikas rado kamuolį."
        assert uncertain_sentence_languages(session, sentence.id, ["lt"]) == []


def test_hand_edit_clears_the_uncertain_record() -> None:
    engine = build_test_engine()
    with Session(engine) as session:
        sentence = _sentence(session, {"en": "The child found a ball.", "lt": "Vaikas rado."})
        set_sentence_translation(session, sentence.id, "lt", "?", confidence=0.1)
        translation = get_sentence_translation(session, sentence.id, "lt")
        assert translation is not None

        update_sentence_translation(session, translation, translation_text="Vaikas rado kamuolį.")

        assert uncertain_sentence_languages(session, sentence.id, ["lt"]) == []


def test_uncertain_language_is_not_stored_decomposed_or_asked_again() -> None:
    engine = build_test_engine()
    with Session(engine) as session:
        sentence = _sentence(session, {"en": "The child found a green ball."})

        first = _run(session, sentence.id, ["lt", "fr"], {"lt": 0.4})

        assert _text(session, sentence.id, "lt") is None
        assert _text(session, sentence.id, "fr") == "[fr]"
        assert "lt" not in first["phase3"]
        assert (
            session.query(SentenceWord)
            .filter_by(sentence_id=sentence.id, language_code="lt")
            .count()
            == 0
        )
        assert uncertain_sentence_languages(session, sentence.id, ["lt", "fr"]) == ["lt"]

        skipped = _run(session, sentence.id, ["lt", "fr"], {})
        retried = _run(session, sentence.id, ["lt", "fr"], {}, retry_uncertain=True)

        assert "lt" not in skipped["phase1"]
        assert "lt" in retried["phase1"]
        assert _text(session, sentence.id, "lt") == "[lt]"
        assert uncertain_sentence_languages(session, sentence.id, ["lt"]) == []


def test_zvirblis_selection_counts_uncertain_languages_as_done() -> None:
    engine = build_test_engine()
    with Session(engine) as session:
        sentence = _sentence(
            session, {"en": "The child found a green ball.", "fr": "L'enfant a trouvé."}
        )
        lemma = session.query(Lemma).first()
        assert lemma is not None
        session.add(
            SentenceWord(
                sentence_id=sentence.id,
                lemma_id=lemma.id,
                language_code="en",
                position=0,
                part_of_speech="noun",
            )
        )
        set_sentence_translation(session, sentence.id, "lt", "?", confidence=0.1)

        skipped = find_sentences_needing_translations(
            session, lemma_id=lemma.id, target_languages=["fr", "lt"]
        )
        retried = find_sentences_needing_translations(
            session, lemma_id=lemma.id, target_languages=["fr", "lt"], retry_uncertain=True
        )

        assert sentence.id not in skipped
        assert sentence.id in retried
