"""Workqueue handler for synonym generation tasks.

This module implements the core synonym generation logic that is shared
between the Barsukas task worker and the SernasAgent CLI.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from workqueue.tools import build_default_config, get_lemma_or_raise
import constants
import util.prompt_loader
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.crud.derivative_form import add_derivative_form
from wordfreq.storage.crud.grammar_fact import add_grammar_fact
from wordfreq.storage.crud.word_token import add_word_token
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import get_supported_languages, get_translation
from wordfreq.tools.text_utils import is_numeral
from wordfreq.translation.client import LinguisticClient

logger = logging.getLogger(__name__)


def query_synonyms_from_llm(
    client: LinguisticClient,
    word: str,
    language_code: str,
    pos_type: str,
    definition: str,
    english_word: str,
) -> Dict[str, Any]:
    """
    Query LLM for synonyms and alternative forms.

    Args:
        client: LinguisticClient instance
        word: The word to find synonyms for
        language_code: Language code
        pos_type: Part of speech
        definition: English definition
        english_word: Original English lemma (for context)

    Returns:
        Dictionary with synonyms, abbreviations, expanded_forms, alternate_spellings, and success flag
    """
    # Get language name
    language_names = get_supported_languages()
    if language_code == "en":
        language_name = "English"
    else:
        language_name = language_names.get(language_code, language_code)

    # Load prompt templates from files
    context = util.prompt_loader.get_context("synonyms", "word")
    prompt_template = util.prompt_loader.get_prompt("synonyms", "word")

    # Add language-specific notes (Chinese is already covered in context.txt)
    language_note = ""
    if language_code == "ko":
        language_note = "- For Korean, provide words in Hangul (e.g., 거리, 길 for 'street')"

    # Build prompt with variables
    prompt_body = prompt_template.replace("{{language_name}}", language_name)
    prompt_body = prompt_body.replace("{{word}}", word)
    prompt_body = prompt_body.replace("{{pos_type}}", pos_type)
    prompt_body = prompt_body.replace("{{english_word}}", english_word)
    prompt_body = prompt_body.replace("{{definition}}", definition or "")
    prompt_body = prompt_body.replace("{{language_note}}", language_note)

    # Combine context and prompt
    prompt = f"{context}\n\n{prompt_body}"

    try:
        # Query the LLM using generate_chat with JSON schema
        json_schema = {
            "type": "object",
            "properties": {
                "abbreviations": {"type": "array", "items": {"type": "string"}},
                "expanded_forms": {"type": "array", "items": {"type": "string"}},
                "alternate_spellings": {"type": "array", "items": {"type": "string"}},
                "synonyms": {"type": "array", "items": {"type": "string"}},
                "explanation": {"type": "string"},
            },
            "required": ["abbreviations", "expanded_forms", "alternate_spellings", "synonyms"],
        }

        response = client.client.generate_chat(
            prompt=prompt, model=client.model, json_schema=json_schema
        )

        if not response.structured_data:
            return {"success": False, "error": "Empty response from LLM"}

        # Use structured data from response
        result = response.structured_data

        return {
            "success": True,
            "synonyms": result.get("synonyms", []),
            "abbreviations": result.get("abbreviations", []),
            "expanded_forms": result.get("expanded_forms", []),
            "alternate_spellings": result.get("alternate_spellings", []),
            "explanation": result.get("explanation", ""),
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        return {"success": False, "error": f"Invalid JSON response: {e}"}
    except Exception as e:
        logger.error(f"Error querying LLM: {e}")
        return {"success": False, "error": str(e)}


def store_synonym_forms(
    session: Session,
    lemma: Lemma,
    language_code: str,
    synonyms: List[str],
    abbreviations: List[str],
    expanded_forms: List[str],
    alternate_spellings: List[str],
) -> Dict[str, int]:
    """
    Store synonym and alternative forms in the database.

    Args:
        session: Database session
        lemma: Lemma to associate forms with
        language_code: Language code
        synonyms: List of synonym strings
        abbreviations: List of abbreviation strings
        expanded_forms: List of expanded form strings
        alternate_spellings: List of alternate spelling strings

    Returns:
        Dictionary with counts of stored forms by type
    """
    stored_counts = {
        "synonyms": 0,
        "abbreviations": 0,
        "expanded_forms": 0,
        "alternate_spellings": 0,
    }

    for synonym in synonyms:
        try:
            word_token = add_word_token(session, synonym, language_code)
            add_derivative_form(
                session=session,
                lemma=lemma,
                derivative_form_text=synonym,
                language_code=language_code,
                grammatical_form="synonym",
                word_token=word_token,
                verified=False,
            )
            stored_counts["synonyms"] += 1
        except Exception as e:
            logger.warning(f"Failed to store synonym '{synonym}': {e}")

    for abbr in abbreviations:
        try:
            word_token = add_word_token(session, abbr, language_code)
            add_derivative_form(
                session=session,
                lemma=lemma,
                derivative_form_text=abbr,
                language_code=language_code,
                grammatical_form="abbreviation",
                word_token=word_token,
                verified=False,
            )
            stored_counts["abbreviations"] += 1
        except Exception as e:
            logger.warning(f"Failed to store abbreviation '{abbr}': {e}")

    for exp_form in expanded_forms:
        try:
            word_token = add_word_token(session, exp_form, language_code)
            add_derivative_form(
                session=session,
                lemma=lemma,
                derivative_form_text=exp_form,
                language_code=language_code,
                grammatical_form="expanded_form",
                word_token=word_token,
                verified=False,
            )
            stored_counts["expanded_forms"] += 1
        except Exception as e:
            logger.warning(f"Failed to store expanded form '{exp_form}': {e}")

    for alt_spelling in alternate_spellings:
        try:
            word_token = add_word_token(session, alt_spelling, language_code)
            add_derivative_form(
                session=session,
                lemma=lemma,
                derivative_form_text=alt_spelling,
                language_code=language_code,
                grammatical_form="alternate_spelling",
                word_token=word_token,
                verified=False,
            )
            stored_counts["alternate_spellings"] += 1
        except Exception as e:
            logger.warning(f"Failed to store alternate spelling '{alt_spelling}': {e}")

    return stored_counts


def record_synonym_grammar_facts(
    session: Session,
    lemma_id: int,
    language_code: str,
    stored_counts: Dict[str, int],
) -> None:
    """
    Record grammar facts to track what ŠERNAS found (or didn't find).

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code
        stored_counts: Dictionary with counts of stored forms by type
    """
    add_grammar_fact(
        session,
        lemma_id,
        language_code,
        "has_synonyms",
        "true" if stored_counts["synonyms"] > 0 else "false",
        verified=True,
    )
    add_grammar_fact(
        session,
        lemma_id,
        language_code,
        "has_abbreviations",
        "true" if stored_counts["abbreviations"] > 0 else "false",
        verified=True,
    )
    add_grammar_fact(
        session,
        lemma_id,
        language_code,
        "has_expanded_forms",
        "true" if stored_counts["expanded_forms"] > 0 else "false",
        verified=True,
    )
    add_grammar_fact(
        session,
        lemma_id,
        language_code,
        "has_alternate_spellings",
        "true" if stored_counts["alternate_spellings"] > 0 else "false",
        verified=True,
    )


def generate_synonyms_for_lemma(
    session: Session,
    lemma: Lemma,
    language_code: str = "en",
    config: Optional[DataSourceConfig] = None,
    client: Optional[LinguisticClient] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Generate synonyms and alternative forms for a single lemma.

    This is the core synonym generation logic shared by both the workqueue
    handler and the SernasAgent.

    Args:
        session: Database session
        lemma: Lemma to generate synonyms for
        language_code: Language code (default: "en")
        config: DataSourceConfig (uses default if not provided)
        client: LinguisticClient (creates one if not provided)
        dry_run: If True, only show what would be generated without saving

    Returns:
        Dictionary with generation results including stored counts
    """
    if config is None:
        config = build_default_config()

    # Get the word to find synonyms for
    if language_code == "en":
        word = lemma.lemma_text
    else:
        word = get_translation(session, lemma, language_code)

    if not word or not word.strip():
        return {
            "error": f"No translation found for language {language_code}",
            "lemma_id": lemma.id,
            "language_code": language_code,
        }

    logger.info(f"Generating synonyms for '{word}' ({language_code})")

    # Create client if not provided
    if client is None:
        client = LinguisticClient(config=config)

    # Query LLM for synonyms
    result = query_synonyms_from_llm(
        client=client,
        word=word,
        language_code=language_code,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text,
        english_word=lemma.lemma_text,
    )

    if not result["success"]:
        return {
            "error": result.get("error", "Failed to generate synonyms"),
            "lemma_id": lemma.id,
            "language_code": language_code,
        }

    # Extract results and filter out numerals
    synonyms = [s for s in result.get("synonyms", []) if not is_numeral(s)]
    abbreviations = [a for a in result.get("abbreviations", []) if not is_numeral(a)]
    expanded_forms = [e for e in result.get("expanded_forms", []) if not is_numeral(e)]
    alternate_spellings = [a for a in result.get("alternate_spellings", []) if not is_numeral(a)]

    if dry_run:
        return {
            "dry_run": True,
            "lemma_id": lemma.id,
            "language_code": language_code,
            "word": word,
            "synonyms": synonyms,
            "abbreviations": abbreviations,
            "expanded_forms": expanded_forms,
            "alternate_spellings": alternate_spellings,
            "total_count": len(synonyms)
            + len(abbreviations)
            + len(expanded_forms)
            + len(alternate_spellings),
        }

    # Store the forms in the database
    stored_counts = store_synonym_forms(
        session=session,
        lemma=lemma,
        language_code=language_code,
        synonyms=synonyms,
        abbreviations=abbreviations,
        expanded_forms=expanded_forms,
        alternate_spellings=alternate_spellings,
    )

    # Record grammar facts
    record_synonym_grammar_facts(session, lemma.id, language_code, stored_counts)

    logger.info(
        f"Stored {stored_counts['synonyms']} synonyms, {stored_counts['abbreviations']} abbreviations, "
        f"{stored_counts['expanded_forms']} expanded forms, and {stored_counts['alternate_spellings']} alternate spellings"
    )

    return {
        "success": True,
        "lemma_id": lemma.id,
        "language_code": language_code,
        "word": word,
        "synonyms": synonyms,
        "abbreviations": abbreviations,
        "expanded_forms": expanded_forms,
        "alternate_spellings": alternate_spellings,
        "stored_synonyms": stored_counts["synonyms"],
        "stored_abbreviations": stored_counts["abbreviations"],
        "stored_expanded": stored_counts["expanded_forms"],
        "stored_spellings": stored_counts["alternate_spellings"],
    }


def handle_generate_synonyms(session: Session, payload: Dict) -> str:
    """
    Handle synonym generation task (workqueue entry point).

    Payload schema:
        lemma_id: int - ID of the lemma to generate synonyms for
        lang_code: str - Language code (default: "en")

    Returns:
        str: Result message describing what was generated
    """
    lemma_id = payload["lemma_id"]
    lang_code = payload.get("lang_code", "en")

    lemma = get_lemma_or_raise(session, lemma_id)

    if lang_code != "en":
        translation = get_translation(session, lemma, lang_code)
        if not translation or not translation.strip():
            raise ValueError(f"No {lang_code} translation found for this lemma")

    result = generate_synonyms_for_lemma(session, lemma, lang_code)

    if "error" in result:
        raise RuntimeError(result["error"])

    synonyms_count = result.get("stored_synonyms", 0)
    alternatives_count = (
        result.get("stored_abbreviations", 0)
        + result.get("stored_expanded", 0)
        + result.get("stored_spellings", 0)
    )

    session.commit()
    return f"Stored {synonyms_count} synonym(s) and {alternatives_count} alternative form(s)"
