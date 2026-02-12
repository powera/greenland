"""Shared infrastructure for LLM-based word form generation.

Every per-language ``llm_forms.py`` delegates to :func:`query_forms`, passing
a :class:`LanguageFormSpec` that describes the language, POS, form fields,
prompt path, and schema metadata.  This removes ~150 lines of near-identical
boilerplate from each language module.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from sqlalchemy.orm import Session
from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)


@dataclass
class LanguageFormSpec:
    """Declares everything needed for one language + POS combination."""

    language_code: str  # e.g. "fi"
    language_name: str  # e.g. "Finnish"
    pos_type: str  # "noun", "verb", "adjective", "adverb"
    form_mapping: Dict[str, GrammaticalForm]
    form_fields: List[str]  # ordered field names for the JSON schema
    prompt_path: str  # e.g. "finnish/noun"
    query_type: str  # for log_query, e.g. "finnish_noun_forms"
    schema_name: str  # e.g. "FinnishNounForms"
    schema_description: str  # e.g. "Finnish noun forms"
    is_source_language: bool = False  # True only for English
    word_variable: str = ""  # prompt placeholder name; defaults to pos_type
    form_descriptions: Optional[Dict[str, str]] = None  # custom per-field descriptions
    extra_schema_properties: Optional[Dict[str, SchemaProperty]] = None

    def __post_init__(self) -> None:
        if not self.word_variable:
            self.word_variable = self.pos_type


def query_forms(
    spec: LanguageFormSpec,
    client: UnifiedLLMClient,
    lemma_id: int,
    get_session_func: Callable[[], Session],
) -> Tuple[Dict[str, str], bool]:
    """Generic form-generation function parameterised by *spec*.

    Replaces all per-language ``query_{lang}_{pos}_forms()`` functions.
    """
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if not lemma or lemma.pos_type.lower() != spec.pos_type:
        logger.error(f"Invalid lemma for {spec.language_name} {spec.pos_type} forms: {lemma_id}")
        return {}, False

    # Determine the word in the target language and the English word.
    if spec.is_source_language:
        target_word = lemma.lemma_text
        english_word = lemma.lemma_text
    else:
        translation_text = get_translation(session, lemma, spec.language_code)
        if not translation_text:
            logger.error(
                f"Invalid lemma for {spec.language_name} {spec.pos_type} forms: {lemma_id}"
            )
            return {}, False
        target_word = translation_text
        english_word = lemma.lemma_text

    definition = lemma.definition_text
    pos_subtype = lemma.pos_subtype

    # Build JSON schema properties for the form fields.
    form_properties: Dict[str, SchemaProperty] = {}
    for form_field in spec.form_fields:
        if spec.form_descriptions and form_field in spec.form_descriptions:
            desc = spec.form_descriptions[form_field]
        else:
            desc = f"{spec.language_name} {form_field.replace('_', ' ')}"
        form_properties[form_field] = SchemaProperty("string", desc)

    # Top-level schema: forms + confidence + notes, plus any extras.
    schema_properties: Dict[str, SchemaProperty] = {}
    if spec.extra_schema_properties:
        schema_properties.update(spec.extra_schema_properties)
    schema_properties["forms"] = SchemaProperty(
        "object", "Dictionary of forms", properties=form_properties
    )
    schema_properties["confidence"] = SchemaProperty("number", "Confidence 0-1")
    schema_properties["notes"] = SchemaProperty("string", "Notes")

    schema = Schema(
        name=spec.schema_name,
        description=spec.schema_description,
        properties=schema_properties,
    )

    # Build prompt kwargs.  The prompt template uses {noun}, {verb}, etc.
    # as the target-language word, plus {english_noun}, {english_verb}, etc.
    prompt_kwargs = {
        spec.word_variable: target_word,
        f"english_{spec.word_variable}": english_word,
        "definition": definition,
        "subtype_context": f" (category: {pos_subtype})" if pos_subtype else "",
    }
    # English prompts use the bare variable name (e.g. {verb}, {noun})
    # with no english_ prefix for the same word; add them for compat.
    if spec.is_source_language:
        prompt_kwargs[spec.word_variable] = target_word

    try:
        context = util.prompt_loader.get_context("language_forms", spec.prompt_path)
        prompt = util.prompt_loader.get_prompt("language_forms", spec.prompt_path).format(
            **prompt_kwargs
        )
        response = client.generate_chat(
            prompt=prompt,
            model=client.default_model,
            json_schema=schema,
            context=context,
        )
        linguistic_db.log_query(
            session,
            word=target_word,
            query_type=spec.query_type,
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(
            f"Error querying {spec.language_name} {spec.pos_type} forms "
            f"for '{target_word}': {e}"
        )
        return {}, False
