#!/usr/bin/python3

"""Chinese language form generation.

Chinese is an isolating language with no inflectional morphology, but verbs
combine with aspect particles in patterns that are essential for learners.
We store the bare verb plus three common aspect patterns:

* perfective (了): completed action  — 买了 "bought"
* experiential (过): have done before — 买过 "have bought before"
* progressive (在): in progress       — 在买 "is buying"

Nouns have only a single base form.
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
    "base": GrammaticalForm.NOUN_ZH_BASE,
}

VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = {
    "base": GrammaticalForm.VERB_ZH_BASE,
    "perfective": GrammaticalForm.VERB_ZH_PERFECTIVE,
    "experiential": GrammaticalForm.VERB_ZH_EXPERIENTIAL,
    "progressive": GrammaticalForm.VERB_ZH_PROGRESSIVE,
}


def query_chinese_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Chinese noun forms (base form only)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    zh_translation = (
        session.query(linguistic_db.LemmaTranslation)
        .filter(
            linguistic_db.LemmaTranslation.lemma_id == lemma_id,
            linguistic_db.LemmaTranslation.language_code == "zh",
        )
        .first()
    )

    if not lemma or not zh_translation or lemma.pos_type.lower() != "noun":
        logger.error(f"Invalid lemma for Chinese noun forms: {lemma_id}")
        return {}, False

    noun, english_noun, definition, pos_subtype = (
        zh_translation.translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["base"]
    form_properties = {f: SchemaProperty("string", f"Chinese {f} form") for f in fields}

    schema = Schema(
        name="ChineseNounForms",
        description="Chinese noun forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of noun forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "chinese/noun")
        prompt = util.prompt_loader.get_prompt("language_forms", "chinese/noun").format(
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
            query_type="chinese_noun_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Chinese noun forms for '{noun}': {e}")
        return {}, False


def query_chinese_verb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Chinese verb forms (base + aspect patterns)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    zh_translation = get_translation(session, lemma, "zh") if lemma else None

    if not lemma or not zh_translation or lemma.pos_type.lower() != "verb":
        logger.error(f"Invalid lemma for Chinese verb forms: {lemma_id}")
        return {}, False

    verb, english_verb, definition, pos_subtype = (
        zh_translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["base", "perfective", "experiential", "progressive"]
    form_descriptions = {
        "base": "bare verb (e.g. 买)",
        "perfective": "verb + 了 — completed action (e.g. 买了)",
        "experiential": "verb + 过 — have done before (e.g. 买过)",
        "progressive": "在 + verb — in progress (e.g. 在买)",
    }
    form_properties = {f: SchemaProperty("string", form_descriptions[f]) for f in fields}

    schema = Schema(
        name="ChineseVerbForms",
        description="Chinese verb forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of verb forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "chinese/verb")
        prompt = util.prompt_loader.get_prompt("language_forms", "chinese/verb").format(
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
            query_type="chinese_verb_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Chinese verb forms for '{verb}': {e}")
        return {}, False
