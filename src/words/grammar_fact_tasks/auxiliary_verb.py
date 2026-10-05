"""
Auxiliary Verb Task - Determine auxiliary verb for compound tenses.

French is decided by rule (langtools.fr.auxiliary) wherever the rule is
certain, and every verb gets an explicit value, avoir included.  Only the verbs
whose auxiliary depends on the sense (sortir, passer, monter, ...) reach the
LLM, which answers for the sense in the lemma's definition.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Union

from sqlalchemy.orm import Session

from clients.types import LLMCall, Schema, SchemaProperty
from langtools.fr.auxiliary import pc_auxiliary
from storage.models.schema import Lemma
from words.grammar_fact_tasks.common import (
    NO_FACT,
    FactResult,
    FactTask,
    interpret_field,
    load_prompt,
    run_live,
)
from words.grammar_fact_tasks.systems import AUXILIARY_SYSTEMS

if TYPE_CHECKING:
    from words.grammar_facts import GrammarFactService

logger = logging.getLogger(__name__)


def prepare_auxiliary_verb(
    session: Optional[Session],
    lemma: Lemma,
    target_translation: Optional[str],
    language_code: str,
) -> Union[LLMCall, FactResult]:
    """Build the auxiliary request; French verbs the rule covers need no model."""
    if lemma.pos_type != "verb":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a verb, skipping auxiliary")
        return NO_FACT

    if language_code not in AUXILIARY_SYSTEMS:
        logger.error(f"Language '{language_code}' does not have auxiliary verb configuration")
        return NO_FACT

    if language_code == "fr" and target_translation:
        rule_auxiliary = pc_auxiliary(target_translation)
        if rule_auxiliary:
            return FactResult(rule_auxiliary, "rule: langtools.fr.auxiliary", 1.0)

    aux_config = AUXILIARY_SYSTEMS[language_code]
    language_name = aux_config["name"]
    valid_auxiliaries = ", ".join(aux_config["auxiliaries"])

    context, prompt_template = load_prompt("auxiliary")
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        target_translation=target_translation,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
        language_name=language_name,
        language_code=language_code,
        valid_auxiliaries=valid_auxiliaries,
    )
    schema = Schema(
        name="AuxiliaryVerbClassification",
        description=f"Classify auxiliary verb for {language_name} compound tenses",
        properties={
            "auxiliary_verb": SchemaProperty(
                "string",
                f"The auxiliary verb: {valid_auxiliaries}",
                enum=list(aux_config["auxiliaries"]),
            ),
            "explanation": SchemaProperty("string", "Brief explanation if notable"),
            "confidence": SchemaProperty(
                "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
            ),
        },
    )
    return LLMCall(prompt=prompt_text, schema=schema, context=context)


interpret_auxiliary_verb = interpret_field("auxiliary_verb")

TASK = FactTask(prepare_auxiliary_verb, interpret_auxiliary_verb)


def generate_auxiliary_verb(
    agent: "GrammarFactService",
    lemma: Lemma,
    target_translation: Optional[str],
    language_code: str,
    session: Optional[Session] = None,
) -> Tuple[Optional[str], Optional[str], float]:
    """Generate auxiliary verb classification for compound tenses (fr, de, it, nl).

    Returns:
        Tuple of (auxiliary, explanation, confidence)
    """
    return run_live(agent, TASK, session, lemma, target_translation, language_code, "auxiliary")
