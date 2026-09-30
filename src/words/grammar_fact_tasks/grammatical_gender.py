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
from typing import Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from sqlalchemy.orm import Session

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from langtools.es.gender import predict_gender as predict_spanish_gender
from langtools.fr.gender import predict_gender as predict_french_gender
from storage.crud.grammar_fact import get_grammatical_gender
from storage.models.schema import Lemma
from storage.translation_helpers import get_translation

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
        agent: The LapeAgent instance
        lemma: The Lemma object
        target_translation: The translation in the target language
        language_code: Target language code (e.g., 'fr', 'lt', 'de')
        session: Database session (optional)

    Returns:
        Tuple of (gender, explanation, confidence)
    """
    if lemma.pos_type != "noun":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping gender generation")
        return None, None, 0.0

    if language_code not in agent.GENDER_SYSTEMS:
        logger.error(f"Language '{language_code}' does not have a configured gender system")
        return None, None, 0.0

    if session is not None:
        copied_gender = _copy_from_same_word(lemma, target_translation, language_code, session)
        if copied_gender:
            source_language = _SAME_WORD_GENDER_SOURCE[language_code]
            return copied_gender, f"Copied from {source_language} (same word)", 1.0

    gender_config = agent.GENDER_SYSTEMS[language_code]
    language_name = gender_config["name"]
    valid_genders = ", ".join(gender_config["genders"])
    gender_system = gender_config["description"]

    # Load prompts
    try:
        context = util.prompt_loader.get_context("grammar", "gender")
        prompt_template = util.prompt_loader.get_prompt("grammar", "gender")
    except Exception as e:
        logger.error(f"Failed to load grammatical_gender prompts: {e}")
        return None, None, 0.0

    # Format prompt
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

    # Define JSON schema for response
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

    # Query LLM
    try:
        client = agent.get_llm_client()
        response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

        # Extract structured data
        if response.structured_data:
            result = response.structured_data
        else:
            logger.error(f"No structured data received for '{lemma.lemma_text}'")
            return None, None, 0.0

        gender = result.get("gender", None)
        explanation = result.get("explanation", "")
        confidence = float(result.get("confidence", 0.5))

        logger.info(
            f"Generated gender for '{lemma.lemma_text}' ({target_translation}): "
            f"{gender} (confidence: {confidence:.2f})"
        )

        explanation = _with_rule_check(gender, explanation, target_translation, language_code)
        return gender, explanation, confidence

    except Exception as e:
        logger.error(f"Failed to generate gender for '{lemma.lemma_text}': {e}")
        return None, None, 0.0
