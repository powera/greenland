#!/usr/bin/python3

"""Japanese language form generation.

Japanese nouns do not inflect, so they receive a single base form.
Japanese verbs genuinely conjugate; we generate the four most useful
learner forms: ます形, て形, た形, ない形.
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
    "base": GrammaticalForm.NOUN_JA_BASE,
}

VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = {
    "masu_form": GrammaticalForm.VERB_JA_MASU,
    "te_form": GrammaticalForm.VERB_JA_TE,
    "ta_form": GrammaticalForm.VERB_JA_TA,
    "nai_form": GrammaticalForm.VERB_JA_NAI,
}


def query_japanese_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Japanese noun forms (base form only)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    ja_translation = (
        session.query(linguistic_db.LemmaTranslation)
        .filter(
            linguistic_db.LemmaTranslation.lemma_id == lemma_id,
            linguistic_db.LemmaTranslation.language_code == "ja",
        )
        .first()
    )

    if not lemma or not ja_translation or lemma.pos_type.lower() != "noun":
        logger.error(f"Invalid lemma for Japanese noun forms: {lemma_id}")
        return {}, False

    noun, english_noun, definition, pos_subtype = (
        ja_translation.translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["base"]
    form_properties = {f: SchemaProperty("string", f"Japanese {f} form") for f in fields}

    schema = Schema(
        name="JapaneseNounForms",
        description="Japanese noun forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of noun forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "japanese/noun")
        prompt = util.prompt_loader.get_prompt("language_forms", "japanese/noun").format(
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
            query_type="japanese_noun_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Japanese noun forms for '{noun}': {e}")
        return {}, False


def query_japanese_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Japanese verb conjugations (masu, te, ta, nai forms)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    ja_translation = get_translation(session, lemma, "ja") if lemma else None

    if not lemma or not ja_translation or lemma.pos_type.lower() != "verb":
        logger.error(f"Invalid lemma for Japanese verb conjugations: {lemma_id}")
        return {}, False

    verb, english_verb, definition, pos_subtype = (
        ja_translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["masu_form", "te_form", "ta_form", "nai_form"]
    form_properties = {
        f: SchemaProperty("string", f"Japanese {f.replace('_', ' ')}") for f in fields
    }

    schema = Schema(
        name="JapaneseVerbConjugations",
        description="Japanese verb conjugations",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of verb forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "japanese/verb")
        prompt = util.prompt_loader.get_prompt("language_forms", "japanese/verb").format(
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
            query_type="japanese_verb_conjugations",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Japanese verb conjugations for '{verb}': {e}")
        return {}, False
