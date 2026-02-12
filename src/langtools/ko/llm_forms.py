#!/usr/bin/python3

"""Korean language form generation.

Korean nouns do not inflect, so they receive a single base form.
Korean verbs genuinely conjugate; we generate the three 해요체
(polite informal) tense forms which are most practical for learners.
"""

import json
import logging
from typing import Callable, Dict, Tuple

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from sqlalchemy.orm import Session
from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

# Form mappings
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = {
    "base": GrammaticalForm.NOUN_KO_BASE,
}

VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = {
    "polite_present": GrammaticalForm.VERB_KO_POLITE_PRESENT,
    "polite_past": GrammaticalForm.VERB_KO_POLITE_PAST,
    "polite_future": GrammaticalForm.VERB_KO_POLITE_FUTURE,
}


def query_korean_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Korean noun forms (base form only)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    ko_translation = (
        session.query(linguistic_db.LemmaTranslation)
        .filter(
            linguistic_db.LemmaTranslation.lemma_id == lemma_id,
            linguistic_db.LemmaTranslation.language_code == "ko",
        )
        .first()
    )

    if not lemma or not ko_translation or lemma.pos_type.lower() != "noun":
        logger.error(f"Invalid lemma for Korean noun forms: {lemma_id}")
        return {}, False

    noun, english_noun, definition, pos_subtype = (
        ko_translation.translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["base"]
    form_properties = {f: SchemaProperty("string", f"Korean {f} form") for f in fields}

    schema = Schema(
        name="KoreanNounForms",
        description="Korean noun forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of noun forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "korean/noun")
        prompt = util.prompt_loader.get_prompt("language_forms", "korean/noun").format(
            noun=noun,
            english_noun=english_noun,
            definition=definition,
            subtype_context=f" (category: {pos_subtype})" if pos_subtype else "",
        )
        response = client.generate_chat(
            prompt=prompt,
            model=client.default_model,
            json_schema=schema,
            context=context,
        )
        linguistic_db.log_query(
            session,
            word=noun,
            query_type="korean_noun_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Korean noun forms for '{noun}': {e}")
        return {}, False


def query_korean_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Korean verb conjugations (해요체 polite forms)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    ko_translation = get_translation(session, lemma, "ko") if lemma else None

    if not lemma or not ko_translation or lemma.pos_type.lower() != "verb":
        logger.error(f"Invalid lemma for Korean verb conjugations: {lemma_id}")
        return {}, False

    verb, english_verb, definition, pos_subtype = (
        ko_translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["polite_present", "polite_past", "polite_future"]
    form_properties = {f: SchemaProperty("string", f"Korean {f.replace('_', ' ')}") for f in fields}

    schema = Schema(
        name="KoreanVerbConjugations",
        description="Korean verb conjugations",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of verb forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "korean/verb")
        prompt = util.prompt_loader.get_prompt("language_forms", "korean/verb").format(
            verb=verb,
            english_verb=english_verb,
            definition=definition,
            subtype_context=f" (category: {pos_subtype})" if pos_subtype else "",
        )
        response = client.generate_chat(
            prompt=prompt,
            model=client.default_model,
            json_schema=schema,
            context=context,
        )
        linguistic_db.log_query(
            session,
            word=verb,
            query_type="korean_verb_conjugations",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Korean verb conjugations for '{verb}': {e}")
        return {}, False
