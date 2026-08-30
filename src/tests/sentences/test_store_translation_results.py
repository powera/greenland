"""Tests for storing decomposition output as SentenceWord rows.

``store_translation_results`` consumes the Phase-3 word shape directly
(``surface_form`` / ``english_gloss`` / ``lemma_guid``). It previously took a
legacy ``word`` / ``english`` / ``guid`` shape and relied on adapters at each
call site; a caller that forgot to adapt got rows with empty text columns and
no error. These tests pin the field mapping so that failure cannot return.
"""

import json
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from langtools.ud_relations import ROOT_HEAD_POSITION
from sentences.translation import store_translation_results
from storage.crud.operation_log import (
    SENTENCE_TRANSLATION_UPDATE,
    SENTENCE_WORD_CREATE,
)
from storage.models.operation_log import OperationLog
from storage.models.schema import Lemma, SentenceWord
from tests.sentences.candidate_lookup_fixture import (
    add_test_sentence,
    build_test_engine,
    seed_test_database,
)


def _phase3_word(
    *,
    position: int,
    surface_form: str,
    english_gloss: str,
    lemma_guid: str = "NONE",
    part_of_speech: str = "noun",
    grammatical_form: str = "noun/lt_nominative_singular",
) -> Dict[str, Any]:
    return {
        "position": position,
        "surface_form": surface_form,
        "english_gloss": english_gloss,
        "lemma_guid": lemma_guid,
        "lemma": surface_form,
        "part_of_speech": part_of_speech,
        "grammatical_form": grammatical_form,
    }


def _stored_words(session: Session, sentence_id: int) -> List[SentenceWord]:
    return (
        session.query(SentenceWord)
        .filter_by(sentence_id=sentence_id, language_code="lt")
        .order_by(SentenceWord.position)
        .all()
    )


def test_store_translation_results_populates_text_columns_from_phase3() -> None:
    """Phase-3 field names must reach english_text/target_language_text/declined_form."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "I read a book", "lt": "Skaitau knygą"})

        store_translation_results(
            sentence.id,
            {
                "lt": "Skaitau knygą",
                "words_lt": [
                    _phase3_word(position=0, surface_form="Skaitau", english_gloss="I read"),
                    _phase3_word(position=1, surface_form="knygą", english_gloss="book"),
                ],
            },
            session,
        )

        words = _stored_words(session, sentence.id)
        assert len(words) == 2

        first = words[0]
        assert first.target_language_text == "Skaitau"
        assert first.declined_form == "Skaitau"
        assert first.english_text == "I read"
        assert first.part_of_speech == "noun"
        assert first.grammatical_form == "noun/lt_nominative_singular"

        assert words[1].target_language_text == "knygą"
        assert words[1].english_text == "book"


def test_store_translation_results_resolves_real_lemma_guid() -> None:
    """A real GUID links the row to its Lemma; synthetic SYN ids never do."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "a dog", "lt": "šuo"})

        lemma = session.query(Lemma).filter(Lemma.guid.isnot(None)).first()
        assert lemma is not None and lemma.guid is not None

        store_translation_results(
            sentence.id,
            {
                "lt": "šuo",
                "words_lt": [
                    _phase3_word(
                        position=0,
                        surface_form="šuo",
                        english_gloss="dog",
                        lemma_guid=lemma.guid,
                    ),
                    _phase3_word(
                        position=1,
                        surface_form="kažkas",
                        english_gloss="something",
                        lemma_guid="SYN001",
                    ),
                ],
            },
            session,
        )

        words = _stored_words(session, sentence.id)
        assert words[0].lemma_id == lemma.id
        assert words[1].lemma_id is None


def test_store_translation_results_normalizes_blank_fields() -> None:
    """Whitespace is stripped and an empty grammatical_form becomes NULL."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "a book", "lt": "knyga"})

        word = _phase3_word(position=0, surface_form="  knyga  ", english_gloss="  book  ")
        word["grammatical_form"] = "   "

        store_translation_results(sentence.id, {"lt": "knyga", "words_lt": [word]}, session)

        stored = _stored_words(session, sentence.id)[0]
        assert stored.target_language_text == "knyga"
        assert stored.english_text == "book"
        assert stored.grammatical_form is None


def test_store_translation_results_stores_phase4_ud_fields() -> None:
    """Phase-4 keys reach ud_relation/ud_head_position, and -1 survives as root."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "I read a book", "lt": "Skaitau knygą"})

        verb = _phase3_word(position=0, surface_form="Skaitau", english_gloss="I read")
        verb["ud_relation"] = "root"
        verb["ud_head_position"] = ROOT_HEAD_POSITION

        obj = _phase3_word(position=1, surface_form="knygą", english_gloss="book")
        obj["ud_relation"] = "obj"
        obj["ud_head_position"] = 0

        store_translation_results(
            sentence.id,
            {"lt": "Skaitau knygą", "words_lt": [verb, obj]},
            session,
        )

        words = _stored_words(session, sentence.id)
        assert words[0].ud_relation == "root"
        assert words[0].ud_head_position == ROOT_HEAD_POSITION
        assert words[1].ud_relation == "obj"
        assert words[1].ud_head_position == 0


def test_store_translation_results_leaves_ud_fields_null_without_phase4() -> None:
    """Phase 4 is optional; a Phase-3-only payload must not invent UD values."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "a book", "lt": "knyga"})

        store_translation_results(
            sentence.id,
            {
                "lt": "knyga",
                "words_lt": [_phase3_word(position=0, surface_form="knyga", english_gloss="book")],
            },
            session,
        )

        stored = _stored_words(session, sentence.id)[0]
        assert stored.ud_relation is None
        assert stored.ud_head_position is None


def test_store_translation_results_replaces_prior_words_for_language() -> None:
    """Re-running decomposition must not accumulate duplicate rows."""
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "a book", "lt": "knyga"})

        payload: Dict[str, Any] = {
            "lt": "knyga",
            "words_lt": [_phase3_word(position=0, surface_form="knyga", english_gloss="book")],
        }
        store_translation_results(sentence.id, payload, session)
        store_translation_results(sentence.id, payload, session)

        assert len(_stored_words(session, sentence.id)) == 1


def test_store_translation_results_logs_nothing_by_default() -> None:
    """Logging is opt-in: no source means no operation log entries.

    This is what keeps the change from silently making every existing caller
    start writing to the log.
    """
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "a book", "lt": "knyga"})

        store_translation_results(
            sentence.id,
            {
                "lt": "knyga",
                "words_lt": [_phase3_word(position=0, surface_form="knyga", english_gloss="book")],
            },
            session,
        )

        assert session.query(OperationLog).count() == 0


def test_store_translation_results_logs_translations_and_word_batch() -> None:
    """With a source, one entry per language plus one batch entry per language.

    This function writes its rows by hand rather than through
    storage.crud.sentence_translation, so the CRUD-level logging never fires
    here and these entries are the only record of the write.
    """
    engine = build_test_engine()
    with Session(engine) as session:
        seed_test_database(session)
        sentence = add_test_sentence(session, {"en": "a book", "lt": "knyga"})

        store_translation_results(
            sentence.id,
            {
                "lt": "knyga",
                "words_lt": [
                    _phase3_word(position=0, surface_form="knyga", english_gloss="book"),
                    _phase3_word(position=1, surface_form="nauja", english_gloss="new"),
                ],
            },
            session,
            source="test-suite",
        )

        entries = session.query(OperationLog).order_by(OperationLog.id).all()
        by_type = {entry.operation_type: entry for entry in entries}

        translation_entry = by_type[SENTENCE_TRANSLATION_UPDATE]
        assert translation_entry.entity_guid == sentence.guid
        assert json.loads(translation_entry.fact)["languages"] == ["lt"]

        word_entry = by_type[SENTENCE_WORD_CREATE]
        assert word_entry.entity_guid == sentence.guid
        word_fact = json.loads(word_entry.fact)
        assert word_fact["count"] == 2
        assert word_fact["language_code"] == "lt"
