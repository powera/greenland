#!/usr/bin/python3

"""English language form generation."""

import json
import logging
from typing import Callable, Dict, Optional, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.en.conjugation import expand_verb_forms
from langtools.en.inflection import (
    build_adjective_forms,
    build_adverb_forms,
    build_noun_forms,
)
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage import database as linguistic_db
from storage.crud.grammar_fact import get_grammar_fact_value
from storage.models.enums import GrammaticalForm

logger = logging.getLogger(__name__)

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("en", "adjective")].form_mapping
ADVERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("en", "adverb")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("en", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("en", "verb")].form_mapping


def query_english_verb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate English verb forms mechanically when possible, else use LLM."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "verb":
        base_forms = {"infinitive": lemma.lemma_text}
        past = get_grammar_fact_value(session, lemma.id, "en", "past")
        past_participle = get_grammar_fact_value(session, lemma.id, "en", "past_participle")
        if past:
            base_forms["past"] = past
        if past_participle:
            base_forms["past_participle"] = past_participle
        conjugation_forms = expand_verb_forms(base_forms)
        projected_forms: Dict[str, str] = {}
        for form_name in VERB_FORM_MAPPING:
            if form_name in conjugation_forms:
                projected_forms[form_name] = conjugation_forms[form_name]

        if projected_forms:
            linguistic_db.log_query(
                session,
                word=lemma.lemma_text,
                query_type="english_verb_forms",
                prompt="[mechanical langtools.en.conjugation]",
                response=json.dumps(
                    {
                        "forms": projected_forms,
                        "notes": "mechanical expansion from infinitive and grammar facts",
                        "mechanical": True,
                    }
                ),
                model=client.default_model,
            )
            return projected_forms, True

        logger.info("Falling back to LLM for English verb '%s'", lemma.lemma_text)

    return query_forms(FORM_SPECS[("en", "verb")], client, lemma_id, get_session_func)


def _query_mechanical_or_llm(
    pos_type: str,
    builder: Callable[["linguistic_db.Lemma", Session], Optional[Dict[str, str]]],
    form_mapping: Dict[str, GrammaticalForm],
    notes: str,
    client: UnifiedLLMClient,
    lemma_id: int,
    get_session_func: Callable[[], Session],
) -> Tuple[Dict[str, str], bool]:
    """Run the rule-based inflection for *pos_type*, else fall back to the LLM.

    ``builder`` receives the lemma and an open session so it can consult
    per-lemma grammar facts, and returns ``None`` when the rules are not
    confident. It may also return a partial mapping (e.g. an uncountable noun
    with no plural, or a non-gradable adjective with no comparative), which is
    intentional and is stored as-is.
    """
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == pos_type:
        inflected_forms = builder(lemma, session)
        if inflected_forms:
            projected_forms: Dict[str, str] = {
                form_name: inflected_forms[form_name]
                for form_name in form_mapping
                if form_name in inflected_forms
            }
            if projected_forms:
                linguistic_db.log_query(
                    session,
                    word=lemma.lemma_text,
                    query_type=f"english_{pos_type}_forms",
                    prompt="[mechanical langtools.en.inflection]",
                    response=json.dumps(
                        {
                            "forms": projected_forms,
                            "notes": notes,
                            "mechanical": True,
                        }
                    ),
                    model=client.default_model,
                )
                return projected_forms, True

        logger.info("Falling back to LLM for English %s '%s'", pos_type, lemma.lemma_text)

    return query_forms(FORM_SPECS[("en", pos_type)], client, lemma_id, get_session_func)


def query_english_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate English noun forms mechanically when possible, else use LLM."""

    def _build(lemma: "linguistic_db.Lemma", session: Session) -> Optional[Dict[str, str]]:
        # Countability, number type and irregular plurals are properties of
        # the sense, not the spelling ("iron" the metal vs. the appliance), so
        # they are read per lemma rather than from a surface-text table.
        countability = get_grammar_fact_value(session, lemma.id, "en", "countability")
        number_type = get_grammar_fact_value(session, lemma.id, "en", "number_type")
        irregular_plural = get_grammar_fact_value(session, lemma.id, "en", "plural")
        return build_noun_forms(
            lemma.lemma_text,
            countability=countability,
            number_type=number_type,
            irregular_plural=irregular_plural,
        )

    return _query_mechanical_or_llm(
        "noun",
        _build,
        NOUN_FORM_MAPPING,
        "mechanical pluralization; uncountable nouns have no plural",
        client,
        lemma_id,
        get_session_func,
    )


def query_english_adjective_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate English adjective forms mechanically when possible, else use LLM."""

    def _build(lemma: "linguistic_db.Lemma", session: Session) -> Optional[Dict[str, str]]:
        gradability = get_grammar_fact_value(session, lemma.id, "en", "gradability")
        comparative = get_grammar_fact_value(session, lemma.id, "en", "comparative")
        superlative = get_grammar_fact_value(session, lemma.id, "en", "superlative")
        return build_adjective_forms(
            lemma.lemma_text,
            gradability=gradability,
            comparative=comparative,
            superlative=superlative,
        )

    return _query_mechanical_or_llm(
        "adjective",
        _build,
        ADJECTIVE_FORM_MAPPING,
        "mechanical comparison; non-gradable adjectives have no comparative",
        client,
        lemma_id,
        get_session_func,
    )


def query_english_adverb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate English adverb forms mechanically when possible, else use LLM."""

    def _build(lemma: "linguistic_db.Lemma", session: Session) -> Optional[Dict[str, str]]:
        gradability = get_grammar_fact_value(session, lemma.id, "en", "gradability")
        comparative = get_grammar_fact_value(session, lemma.id, "en", "comparative")
        superlative = get_grammar_fact_value(session, lemma.id, "en", "superlative")
        return build_adverb_forms(
            lemma.lemma_text,
            gradability=gradability,
            comparative=comparative,
            superlative=superlative,
        )

    return _query_mechanical_or_llm(
        "adverb",
        _build,
        ADVERB_FORM_MAPPING,
        "mechanical comparison; non-gradable adverbs have no comparative",
        client,
        lemma_id,
        get_session_func,
    )
