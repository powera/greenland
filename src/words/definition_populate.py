"""Native definitions for a lemma's translations: the pieces ežys's live and batch paths share.

A lemma's English definition stays on ``Lemma.definition_text``.  Every other
language's definition lives on that language's ``LemmaTranslation`` row
(``definition_text``) and defines *that language's word* for the sense, the
way a monolingual dictionary of the language would.  It is not a translation
of the English definition: the English definition and sense note are given to
the model only to pin down which sense is meant.

The live path (``agents.ezys`` without ``--batch``) and the batch job
(``workqueue.handlers.words.definitions.DEFINITIONS_JOB``) both:

1. find the languages a lemma lacks a definition for
   (:func:`missing_definition_languages`), split into request-sized groups
   (:func:`definition_groups`);
2. send the request :func:`build_definition_call` builds, written at the
   register :func:`definition_register` picks from the lemma's level; and
3. write the answer with :func:`store_definitions`.
"""

import json
import logging
from typing import Any, Dict, List, NamedTuple, Optional, Sequence

from sqlalchemy.orm import Session

from clients.types import LLMCall, Schema, SchemaProperty
from storage.crud.curriculum_level import get_curriculum_level
from storage.crud.operation_log import log_operation
from storage.crud.uncertain_llm_result import (
    get_uncertain_llm_result,
    record_uncertain_llm_result,
)
from storage.models.schema import Lemma, LemmaTranslation
from storage.models.uncertain_llm_result import REASON_LOW_CONFIDENCE, TOPIC_DEFINITION
from storage.translation_helpers import (
    get_language_name,
    set_definition,
    split_llm_language_batches,
)
from util.prompt_loader import get_context, get_prompt
from words.translation_populate import excluded_translation_languages

logger = logging.getLogger(__name__)

PROMPT_CATEGORY = "translation"
PROMPT_TYPE = "native_definitions"

#: Answers below this confidence are recorded as uncertain instead of stored.
DEFAULT_MIN_CONFIDENCE = 0.7

#: Whole CEFR steps, simplest first.
CEFR_STEPS: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1", "C2")

#: No definition is written below this register, however basic the word: a
#: definition of "water" or "cat" at A1 would be circular or babyish.
DEFINITION_REGISTER_FLOOR = "B1"


def definition_register(word_cefr: Optional[str]) -> str:
    """The CEFR register to write a definition in, given the word's own level.

    One whole step below the word, and never below
    :data:`DEFINITION_REGISTER_FLOOR`: A1-B2 words get B1 definitions, C1
    words B2, C2 words C1.  A half-step ("B2.1") counts as its whole level; a
    word with no estimated level gets the floor.

    This is the one place the policy lives, so tune it here.
    """
    floor_index = CEFR_STEPS.index(DEFINITION_REGISTER_FLOOR)
    whole = (word_cefr or "").strip().upper()[:2]
    if whole not in CEFR_STEPS:
        return DEFINITION_REGISTER_FLOOR
    return CEFR_STEPS[max(CEFR_STEPS.index(whole) - 1, floor_index)]


def lemma_cefr(session: Session, lemma: Lemma) -> Optional[str]:
    """The CEFR estimate of the lemma's curriculum level, or None if unknown.

    Uses the lemma's base ``difficulty_level``.  Per-language difficulty
    overrides are not consulted: one request covers several languages, and
    the register is a property of the concept's difficulty, not of where one
    course happens to teach it.
    """
    if lemma.difficulty_level is None:
        return None
    row = get_curriculum_level(session, lemma.difficulty_level)
    return row.cefr if row is not None else None


def _translation_rows(lemma: Lemma) -> Dict[str, LemmaTranslation]:
    return {row.language_code: row for row in lemma.translations}


def missing_definition_languages(
    session: Session,
    lemma: Lemma,
    languages: Sequence[str],
    retry_uncertain: bool = False,
    replace_existing: bool = False,
) -> List[str]:
    """The languages among *languages* to ask for a definition, in the given order.

    A language qualifies when the lemma has a non-blank translation in it --
    the definition defines that word, so there is nothing to define without
    one -- and either no definition yet or ``replace_existing``.  English is
    never asked (its definition is the lemma's own), nor is a language the
    lemma is excluded from (a -1 override).  A language a model was uncertain
    of before is left out unless ``retry_uncertain``.
    """
    rows = _translation_rows(lemma)
    candidates = [
        code
        for code in languages
        if code != "en"
        and code in rows
        and (rows[code].translation or "").strip()
        and (replace_existing or not (rows[code].definition_text or "").strip())
    ]
    excluded = set(excluded_translation_languages(session, lemma, candidates))
    candidates = [code for code in candidates if code not in excluded]
    if retry_uncertain:
        return candidates
    return [
        code
        for code in candidates
        if get_uncertain_llm_result(session, TOPIC_DEFINITION, code, lemma_id=lemma.id) is None
    ]


def definition_groups(languages: Sequence[str]) -> List[List[str]]:
    """Split languages into the groups one request each covers (at most 10)."""
    return [list(group) for group in split_llm_language_batches(list(languages))]


def definition_source(lemma: Lemma, languages: Sequence[str]) -> Dict[str, Any]:
    """The sense, as the model sees it: English anchor plus each language's word."""
    rows = _translation_rows(lemma)
    source: Dict[str, Any] = {
        "english_word": lemma.lemma_text,
        "part_of_speech": lemma.pos_type,
        "english_definition": lemma.definition_text or "",
        "words": {code: rows[code].translation for code in languages if code in rows},
    }
    if lemma.pos_subtype:
        source["category"] = lemma.pos_subtype
    if lemma.disambiguation:
        source["english_sense_note"] = lemma.disambiguation
    sense_notes = {
        code: rows[code].disambiguation
        for code in languages
        if code in rows and rows[code].disambiguation
    }
    if sense_notes:
        source["sense_notes"] = sense_notes
    return source


def build_definition_call(
    session: Session, lemma: Lemma, languages: Sequence[str], register: Optional[str] = None
) -> LLMCall:
    """The definition request for *languages* (at most 10).

    The context is static, so it caches across lemmas; the lemma, register
    and languages go in the prompt.

    Raises:
        ValueError: If *languages* is empty.
    """
    if not languages:
        raise ValueError("No languages to ask for")
    if register is None:
        register = definition_register(lemma_cefr(session, lemma))
    properties: Dict[str, SchemaProperty] = {
        code: SchemaProperty(
            "object",
            f"{get_language_name(code)} definition of the {code} word",
            properties={
                "definition": SchemaProperty("string"),
                "confidence": SchemaProperty("number"),
            },
        )
        for code in languages
    }
    requested = {code: get_language_name(code) for code in languages}
    prompt = get_prompt(PROMPT_CATEGORY, PROMPT_TYPE).format(
        source=json.dumps(definition_source(lemma, languages), ensure_ascii=False, indent=1),
        register=register,
        languages=json.dumps(requested, ensure_ascii=False),
    )
    return LLMCall(
        prompt=prompt,
        schema=Schema(
            "NativeDefinitions",
            "One native definition per requested language",
            properties,
            max_schema_tokens=2048,
        ),
        context=get_context(PROMPT_CATEGORY, PROMPT_TYPE),
        max_tokens=256 + 200 * len(languages),
    )


class DefinitionOutcome(NamedTuple):
    """What :func:`store_definitions` did with each asked language."""

    written: List[str]
    #: The answer left these blank.
    blank: List[str]
    #: Below the confidence floor: recorded in uncertain_llm_results instead.
    uncertain: List[str]
    #: Left alone: a definition arrived meanwhile, or the translation is gone.
    skipped: List[str]


def _confidence(answer: Dict[str, Any]) -> float:
    try:
        return float(answer.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def store_definitions(
    session: Session,
    lemma: Lemma,
    data: Dict[str, Any],
    languages: Sequence[str],
    *,
    model: Optional[str],
    source: str,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    replace_existing: bool = False,
) -> DefinitionOutcome:
    """Write a definition answer (keyed by language code) for *languages*; the caller commits.

    The one writer for generated definitions, live or batched.  A language
    whose translation has been removed since it was asked, or which gained a
    definition meanwhile (unless ``replace_existing``), is left alone.  An
    answer below *min_confidence* writes nothing and is recorded as uncertain,
    so a regenerated language keeps its old definition.
    """
    outcome = DefinitionOutcome([], [], [], [])
    rows = _translation_rows(lemma)
    for code in languages:
        answer = data.get(code) or {}
        if not isinstance(answer, dict):
            answer = {}
        text = (answer.get("definition") or "").strip()
        row = rows.get(code)
        if row is None or not (row.translation or "").strip():
            outcome.skipped.append(code)
            continue
        if not text:
            outcome.blank.append(code)
            continue
        if not replace_existing and (row.definition_text or "").strip():
            outcome.skipped.append(code)
            continue
        confidence = _confidence(answer)
        if confidence < min_confidence:
            record_uncertain_llm_result(
                session,
                TOPIC_DEFINITION,
                code,
                REASON_LOW_CONFIDENCE,
                note=f"{model or 'unknown model'} ({confidence:.2f}): {text}",
                lemma_id=lemma.id,
            )
            outcome.uncertain.append(code)
            continue
        set_definition(session, lemma, code, text)
        outcome.written.append(code)

    if outcome.written:
        log_operation(
            session,
            operation_type="definitions_populated",
            source=source,
            entity_type="lemma",
            entity_id=lemma.id,
            lemma_id=lemma.id,
            entity_guid=lemma.guid,
            details={
                "languages": outcome.written,
                "uncertain": outcome.uncertain,
                "model": model,
                "replace_existing": replace_existing,
            },
        )
    return outcome


def describe_outcome(outcome: DefinitionOutcome) -> str:
    """One line for a run report."""
    parts = []
    if outcome.written:
        parts.append(f"written: {', '.join(outcome.written)}")
    if outcome.uncertain:
        parts.append(f"uncertain: {', '.join(outcome.uncertain)}")
    if outcome.blank:
        parts.append(f"blank: {', '.join(outcome.blank)}")
    if outcome.skipped:
        parts.append(f"skipped: {', '.join(outcome.skipped)}")
    return "; ".join(parts) or "nothing to write"
