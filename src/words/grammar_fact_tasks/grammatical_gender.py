"""
Grammatical Gender Task - Determine grammatical gender for nouns.

The LLM decides the gender, from the values in the language's GENDER_SYSTEMS
entry.  Spanish and French add "common" to masculine/feminine, for a noun with
one form that takes either gender (el/la estudiante); the definition of that
value lives in langtools.es.gender / langtools.fr.gender.

Two things happen around the LLM call:

* es-419 copies the es fact when both varieties use the same word, since the
  gender of a Spanish word does not change between varieties.  The copy is a
  row of es-419's own, not a runtime fallback to es; run es first.
* For languages with an ending rule (``langtools.<lang>.gender``), an LLM answer
  that contradicts the rule is kept but flagged in the fact's notes, so review
  can find it.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Tuple, Union

from sqlalchemy.orm import Session

from clients.types import LLMCall, Schema, SchemaProperty
from langtools.es.gender import predict_gender as predict_spanish_gender
from langtools.fr.gender import predict_gender as predict_french_gender
from storage.crud.grammar_fact import get_grammatical_gender
from storage.models.schema import Lemma
from storage.translation_helpers import get_translation
from words.grammar_fact_tasks.common import (
    NO_FACT,
    FactResult,
    FactTask,
    load_prompt,
    run_live,
)
from words.grammar_fact_tasks.systems import GENDER_SYSTEMS

if TYPE_CHECKING:
    from words.grammar_facts import GrammarFactService

logger = logging.getLogger(__name__)

# Ending-based cross-checks, per language.
_GENDER_PREDICTORS: Dict[str, Callable[[str], Optional[str]]] = {
    "es": predict_spanish_gender,
    "es-419": predict_spanish_gender,
    "fr": predict_french_gender,
}

# Storage dialect -> the variety whose fact it copies when the word is the same.
_SAME_WORD_GENDER_SOURCE: Dict[str, str] = {"es-419": "es"}

# Prefix on the notes of an LLM answer the ending rule disagrees with.
RULE_DISAGREEMENT_NOTE = "CHECK: ending rule predicts"


def _copy_from_same_word(
    lemma: Lemma, target_translation: Optional[str], language_code: str, session: Session
) -> Optional[str]:
    """Return the source variety's gender when it uses the same word, else None."""
    source_language = _SAME_WORD_GENDER_SOURCE.get(language_code)
    if source_language is None or not target_translation:
        return None
    source_translation = get_translation(session, lemma, source_language)
    if not source_translation or source_translation.strip() != target_translation.strip():
        return None
    return get_grammatical_gender(session, lemma.id, source_language)


def _with_rule_check(
    gender: Optional[str],
    explanation: Optional[str],
    target_translation: Optional[str],
    language_code: str,
) -> Optional[str]:
    """Prefix *explanation* with a review flag when the ending rule disagrees."""
    predictor = _GENDER_PREDICTORS.get(language_code)
    if predictor is None or not gender or not target_translation:
        return explanation
    predicted = predictor(target_translation)
    if predicted is None or predicted == gender:
        return explanation
    logger.warning(
        "Gender for %s '%s': LLM says %s, ending rule predicts %s",
        language_code,
        target_translation,
        gender,
        predicted,
    )
    flag = f"{RULE_DISAGREEMENT_NOTE} {predicted}."
    return f"{flag} {explanation}" if explanation else flag


def prepare_grammatical_gender(
    session: Optional[Session],
    lemma: Lemma,
    target_translation: Optional[str],
    language_code: str,
) -> Union[LLMCall, FactResult]:
    """Build the gender request, or answer from the source variety's fact."""
    if lemma.pos_type != "noun":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping gender generation")
        return NO_FACT

    if language_code not in GENDER_SYSTEMS:
        logger.error(f"Language '{language_code}' does not have a configured gender system")
        return NO_FACT

    if session is not None:
        copied_gender = _copy_from_same_word(lemma, target_translation, language_code, session)
        if copied_gender:
            source_language = _SAME_WORD_GENDER_SOURCE[language_code]
            return FactResult(copied_gender, f"Copied from {source_language} (same word)", 1.0)

    gender_config = GENDER_SYSTEMS[language_code]
    language_name = gender_config["name"]
    valid_genders = ", ".join(gender_config["genders"])
    gender_system = gender_config["description"]

    context, prompt_template = load_prompt("gender")
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        target_translation=target_translation,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
        language_name=language_name,
        language_code=language_code,
        gender_system=gender_system,
        valid_genders=valid_genders,
    )

    schema = Schema(
        name="GrammaticalGenderGeneration",
        description=f"Determine grammatical gender for {language_name} nouns",
        properties={
            "gender": SchemaProperty(
                "string",
                f"The grammatical gender: {valid_genders}",
                enum=list(gender_config["genders"]),
            ),
            "explanation": SchemaProperty(
                "string", "Brief explanation of why this gender is correct"
            ),
            "confidence": SchemaProperty(
                "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
            ),
        },
    )
    return LLMCall(prompt=prompt_text, schema=schema, context=context)


def interpret_grammatical_gender(
    data: Dict[str, Any], target_translation: Optional[str], language_code: str
) -> FactResult:
    """Read the model's answer, flagging a disagreement with the ending rule."""
    gender = data.get("gender", None)
    explanation = data.get("explanation", "")
    confidence = float(data.get("confidence", 0.5))
    explanation = _with_rule_check(gender, explanation, target_translation, language_code)
    return FactResult(gender, explanation, confidence)


TASK = FactTask(prepare_grammatical_gender, interpret_grammatical_gender)


def generate_grammatical_gender(
    agent: "GrammarFactService",
    lemma: Lemma,
    target_translation: Optional[str],
    language_code: str,
    session: Optional[Session] = None,
) -> Tuple[Optional[str], Optional[str], float]:
    """
    Generate grammatical gender for a noun using LLM.

    Args:
        agent: The GrammarFactService instance (supplies the LLM client)
        lemma: The Lemma object
        target_translation: The translation in the target language
        language_code: Target language code (e.g., 'fr', 'lt', 'de')
        session: Database session (optional; needed for the es-419 copy)

    Returns:
        Tuple of (gender, explanation, confidence)
    """
    return run_live(agent, TASK, session, lemma, target_translation, language_code, "gender")
