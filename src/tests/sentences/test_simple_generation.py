"""Tests for simple (A1) sentence selection and storage."""

from typing import Any, Dict, Iterator, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from sentences import simple_generation
from sentences.simple_generation import (
    SIMPLE_SENTENCE_COLLECTION,
    SimpleCandidate,
    SimpleSentenceGenerator,
    evaluate_candidate,
    select_candidates,
    simple_sentence_counts,
)
from storage.models.schema import Base, Lemma, Sentence, SentenceWordHint


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def _lemma(session: Session, guid: str, text: str, pos_type: str, level: int) -> Lemma:
    lemma = Lemma(
        guid=guid,
        lemma_text=text,
        definition_text=f"definition of {text}",
        pos_type=pos_type,
        difficulty_level=level,
    )
    session.add(lemma)
    session.flush()
    return lemma


def _words(*pairs: str) -> List[Dict[str, str]]:
    return [
        {"word": word, "lemma": word, "part_of_speech": pos}
        for word, pos in (pair.split(":") for pair in pairs)
    ]


@pytest.fixture()
def vocabulary(session: Session) -> Dict[str, Lemma]:
    return {
        "shirt": _lemma(session, "N09_001", "shirt", "noun", 1),
        "wear": _lemma(session, "V01_031", "wear", "verb", 5),
        "green": _lemma(session, "A02_005", "green", "adjective", 3),
        "silk": _lemma(session, "N14_030", "silk", "noun", 120),
        "coat_garment": _lemma(session, "N09_004", "coat", "noun", 27),
        "coat_layer": _lemma(session, "N22_038", "coat", "noun", 276),
    }


def test_candidate_levelled_by_shared_rule(session: Session, vocabulary: Dict[str, Lemma]) -> None:
    candidate = evaluate_candidate(
        session,
        vocabulary["shirt"],
        {
            "en": "She wears a green shirt.",
            "words_used": _words("wear:verb", "green:adjective", "shirt:noun", "she:other"),
        },
    )

    assert candidate.reject_reason is None
    assert candidate.level == 3


def test_one_hard_word_is_understood_from_context(
    session: Session, vocabulary: Dict[str, Lemma]
) -> None:
    candidate = evaluate_candidate(
        session,
        vocabulary["shirt"],
        {
            "en": "I wear a silk shirt.",
            "words_used": _words("wear:verb", "silk:noun", "shirt:noun"),
        },
    )

    assert candidate.reject_reason is None
    assert candidate.level == 5


def test_rejects_unknown_word_banned_phrase_and_missing_target(
    session: Session, vocabulary: Dict[str, Lemma]
) -> None:
    target = vocabulary["shirt"]
    unknown = evaluate_candidate(
        session,
        target,
        {"en": "He irons his shirt.", "words_used": _words("iron:verb", "shirt:noun")},
    )
    friend = evaluate_candidate(
        session,
        target,
        {"en": "My friend wears a shirt.", "words_used": _words("wear:verb", "shirt:noun")},
    )
    missing = evaluate_candidate(
        session, target, {"en": "She wears green.", "words_used": _words("wear:verb", "green:noun")}
    )

    assert unknown.reject_reason == "unknown word 'iron'"
    assert friend.reject_reason == "uses 'my friend'"
    assert missing.reject_reason is not None


def test_ambiguous_word_takes_easiest_sense(session: Session, vocabulary: Dict[str, Lemma]) -> None:
    candidate = evaluate_candidate(
        session,
        vocabulary["shirt"],
        {"en": "He wears a coat and shirt.", "words_used": _words("coat:noun", "shirt:noun")},
    )

    assert vocabulary["coat_garment"] in candidate.lemmas
    assert candidate.level == 27


def _candidate(text: str, level: int, reject_reason: Optional[str] = None) -> SimpleCandidate:
    return SimpleCandidate(text=text, level=level, reject_reason=reject_reason)


def test_selection_prefers_easy_varied_sentences_without_repeated_filler() -> None:
    candidates = [
        _candidate("She wears a shirt today.", 1),
        _candidate("She buys a red shirt.", 2),
        _candidate("We wash the shirt yesterday.", 3),
        _candidate("They like the blue shirt.", 4),
        _candidate("I need a clean shirt.", 1, reject_reason="level 40"),
    ]

    chosen = select_candidates(candidates, existing_texts=["He lost his shirt today."], needed=2)

    assert [candidate.text for candidate in chosen] == [
        "She buys a red shirt.",
        "They like the blue shirt.",
    ]


def test_generate_and_store_fills_to_two(
    session: Session, vocabulary: Dict[str, Lemma], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(simple_generation, "build_prompt_vocabulary_section", lambda **_: "")
    generator = SimpleSentenceGenerator.__new__(SimpleSentenceGenerator)
    generator.dry_run = False
    prompts: List[Dict[str, Any]] = []

    def fake_call(**kwargs: Any) -> Dict[str, Any]:
        prompts.append(kwargs)
        return {
            "sentences": [
                {
                    "en": "She wears a green shirt.",
                    "words_used": _words("wear:verb", "green:adjective", "shirt:noun"),
                },
                {"en": "My friend has a shirt.", "words_used": _words("shirt:noun")},
                {"en": "I wear my shirt.", "words_used": _words("wear:verb", "shirt:noun")},
            ]
        }

    monkeypatch.setattr(generator, "_call_llm_for_sentences", fake_call)
    target = vocabulary["shirt"]

    result = generator.generate_and_store(session, target)

    assert result["storage"] == {"stored": 2}
    assert prompts[0]["prompt_name"] == "simple"
    assert simple_sentence_counts(session) == {"N09_001": 2}
    stored = session.query(Sentence).filter_by(sentence_collection=SIMPLE_SENTENCE_COLLECTION).all()
    assert sorted(sentence.minimum_level or 0 for sentence in stored) == [3, 5]
    assert session.query(SentenceWordHint).filter_by(lemma_id=target.id).count() == 2

    # A full word is not sent to the model again.
    assert generator.generate_and_store(session, target)["skipped"] is True
    assert len(prompts) == 1
