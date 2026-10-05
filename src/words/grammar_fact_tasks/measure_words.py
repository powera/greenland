"""
Measure Words Task - Generate Chinese measure words/classifiers for nouns.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Union

from sqlalchemy.orm import Session

from clients.types import LLMCall, Schema, SchemaProperty
from storage.models.schema import Lemma
from words.grammar_fact_tasks.common import (
    NO_FACT,
    FactResult,
    FactTask,
    interpret_field,
    load_prompt,
    run_live,
)

if TYPE_CHECKING:
    from words.grammar_facts import GrammarFactService

logger = logging.getLogger(__name__)


def prepare_measure_words(
    session: Optional[Session],
    lemma: Lemma,
    chinese_translation: Optional[str],
    language_code: str,
) -> Union[LLMCall, FactResult]:
    """Build the Chinese measure-word request."""
    if lemma.pos_type != "noun":
        logger.warning(
            f"Lemma '{lemma.lemma_text}' is not a noun, skipping measure word generation"
        )
        return NO_FACT

    context, prompt_template = load_prompt("measure_words")
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        chinese_translation=chinese_translation,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
    )
    schema = Schema(
        name="MeasureWordGeneration",
        description="Generate Chinese measure words/classifiers for nouns",
        properties={
            "primary_measure_word": SchemaProperty(
                "string", "The primary/most common measure word"
            ),
            "alternative_measure_words": SchemaProperty(
                "array",
                "List of alternative measure words that can also be used",
                items={"type": "string"},
            ),
            "explanation": SchemaProperty(
                "string", "Brief explanation of why this measure word is appropriate"
            ),
            "confidence": SchemaProperty(
                "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
            ),
        },
    )
    return LLMCall(prompt=prompt_text, schema=schema, context=context)


def interpret_measure_words(
    data: Dict[str, Any], chinese_translation: Optional[str], language_code: str
) -> FactResult:
    """The primary measure word is the value; alternatives are only logged."""
    measure_word = data.get("primary_measure_word", None)
    alternatives = data.get("alternative_measure_words", [])
    if alternatives:
        logger.info(f"Measure word {measure_word} (alt: {', '.join(alternatives)})")
    return FactResult(measure_word, data.get("explanation", ""), float(data.get("confidence", 0.5)))


TASK = FactTask(prepare_measure_words, interpret_measure_words)


def generate_measure_words(
    agent: "GrammarFactService",
    lemma: Lemma,
    chinese_translation: Optional[str],
    session: Optional[Session] = None,
) -> Tuple[Optional[str], Optional[str], float]:
    """Generate Chinese measure word(s) for a noun using LLM.

    Returns:
        Tuple of (measure_word, explanation, confidence)
    """
    return run_live(agent, TASK, session, lemma, chinese_translation, "zh", "measure word")
