#!/usr/bin/python3

"""Synonym generation library.

This module is the canonical entry point for synonym/alternative-form
generation. It owns prompt construction, the LLM call, normalization,
storage, and processing-metadata bookkeeping. Both the workqueue handler
(``workqueue.handlers.words.synonyms``) and the ŠERNAS agent
(``agents.sernas.agent``) delegate here.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from clients.unified_client import UnifiedLLMClient
from langtools.directions import get_language_direction_note
from storage.backend.config import DataSourceConfig
from storage.crud.derivative_form import add_derivative_form
from storage.crud.grammar_fact import add_grammar_fact, get_grammar_fact_value
from storage.crud.operation_log import log_operation
from storage.crud.variant_form import add_variant_form
from storage.crud.word_token import add_word_token
from storage.models.schema import SYNONYM_GRAMMATICAL_FORMS, DerivativeForm, Lemma
from storage.models.variant_form import VARIANT_KIND_SPELLING
from storage.translation_helpers import get_supported_languages, get_translation
from wordfreq.tools.text_utils import is_numeral

import util.prompt_loader

logger = logging.getLogger(__name__)


# Maps LLM JSON keys to the ``grammatical_form`` value stored on
# ``DerivativeForm`` rows. The ordering here is also the canonical
# preference order when deduplicating across categories.
#
# ``alternate_spellings`` is deliberately not in this map. A spelling variant
# is the same lexeme as the lemma and carries its own paradigm, so it is
# stored in ``variant_forms`` by ``store_spelling_variants`` instead.
SYNONYM_FORM_MAP: Dict[str, str] = {
    "synonyms": "synonym",
    "near_synonyms": "synonym_near",
    "regional_variants": "synonym_regional",
    "register_variants": "synonym_register",
    "synecdoche_variants": "synonym_synecdoche",
    "related_learner_equivalents": "synonym_related",
}

assert set(SYNONYM_FORM_MAP.values()) == set(
    SYNONYM_GRAMMATICAL_FORMS
), "SYNONYM_FORM_MAP values must match storage.models.schema.SYNONYM_GRAMMATICAL_FORMS"


SYNONYMS_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "abbreviations": {"type": "array", "items": {"type": "string"}},
        "expanded_forms": {"type": "array", "items": {"type": "string"}},
        "synonyms": {"type": "array", "items": {"type": "string"}},
        "near_synonyms": {"type": "array", "items": {"type": "string"}},
        "regional_variants": {"type": "array", "items": {"type": "string"}},
        "register_variants": {"type": "array", "items": {"type": "string"}},
        "synecdoche_variants": {"type": "array", "items": {"type": "string"}},
        "related_learner_equivalents": {"type": "array", "items": {"type": "string"}},
        "alternate_spellings": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
    },
    "required": [
        "abbreviations",
        "expanded_forms",
        "synonyms",
        "near_synonyms",
        "regional_variants",
        "register_variants",
        "synecdoche_variants",
        "related_learner_equivalents",
        "alternate_spellings",
    ],
}


def build_synonyms_prompt(
    language_code: str,
    word: str,
    config: Optional[DataSourceConfig] = None,
    *,
    pos_type: str = "noun",
    english_word: Optional[str] = None,
    definition: str = "",
) -> str:
    """Build the shared synonym-generation prompt for a word."""
    _ = config  # reserved for future prompt variations

    normalized_language = language_code.lower()
    language_names = get_supported_languages()
    language_name = (
        "English"
        if normalized_language == "en"
        else language_names.get(normalized_language, normalized_language)
    )

    context = util.prompt_loader.get_context("synonyms", "word")
    prompt_template = util.prompt_loader.get_prompt("synonyms", "word")

    prompt_body = prompt_template.replace("{{language_name}}", language_name)
    prompt_body = prompt_body.replace("{{word}}", word)
    prompt_body = prompt_body.replace("{{pos_type}}", pos_type)
    prompt_body = prompt_body.replace("{{english_word}}", english_word or word)
    prompt_body = prompt_body.replace("{{definition}}", definition)
    prompt_body = prompt_body.replace(
        "{{language_note}}", get_language_direction_note(normalized_language)
    )

    return f"{context}\n\n{prompt_body}"


def query_synonyms(
    language_code: str,
    word: str,
    *,
    client: UnifiedLLMClient,
    model: str,
    config: Optional[DataSourceConfig] = None,
    pos_type: str = "noun",
    english_word: Optional[str] = None,
    definition: str = "",
    json_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the shared synonym prompt against an LLM and return structured data."""
    prompt = build_synonyms_prompt(
        language_code,
        word,
        config=config,
        pos_type=pos_type,
        english_word=english_word,
        definition=definition,
    )

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=json_schema or SYNONYMS_JSON_SCHEMA,
        )
    except Exception as error:
        logger.error("Error querying synonyms for '%s' (%s): %s", word, language_code, error)
        return {"success": False, "error": str(error)}

    if not response.structured_data:
        return {"success": False, "error": "Empty response from LLM"}

    result = response.structured_data
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError as error:
            return {"success": False, "error": f"Invalid JSON response: {error}"}

    if not isinstance(result, dict):
        return {"success": False, "error": "Structured response is not an object"}

    merged: Dict[str, Any] = {"success": True}
    merged.update(result)
    return merged


def normalize_generated_forms(forms: List[str], original_word: str) -> List[str]:
    """Trim, dedupe, and filter LLM-generated form lists.

    Drops empty strings, pure numerals, the original word itself, and
    case-insensitive duplicates.
    """
    normalized: List[str] = []
    seen: set[str] = set()
    original_normalized = original_word.strip().casefold()

    for raw_form in forms:
        clean_form = (raw_form or "").strip()
        if not clean_form or is_numeral(clean_form):
            continue
        if clean_form.casefold() == original_normalized:
            continue
        dedup_key = clean_form.casefold()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        normalized.append(clean_form)

    return normalized


def query_synonyms_from_llm(
    config: DataSourceConfig,
    word: str,
    language_code: str,
    pos_type: str,
    definition: str,
    english_word: str,
) -> Dict[str, Any]:
    """Query an LLM for all synonym/alternative-form categories for ``word``.

    Returns a dict with ``success`` and one entry per category in
    ``SYNONYM_FORM_MAP`` plus ``abbreviations``, ``expanded_forms``, and
    ``explanation``. On failure, returns ``{"success": False, "error": ...}``.
    """
    # Lazy-imported to avoid a circular import via wordfreq -> langtools -> words.
    from wordfreq.translation.client import LinguisticClient

    client = LinguisticClient(config=config)
    result = query_synonyms(
        language_code,
        word,
        client=client.client,
        model=client.model,
        pos_type=pos_type,
        english_word=english_word,
        definition=definition or "",
    )
    if not result.get("success"):
        return result

    payload: Dict[str, Any] = {
        "success": True,
        "abbreviations": result.get("abbreviations", []),
        "expanded_forms": result.get("expanded_forms", []),
        "explanation": result.get("explanation", ""),
    }
    for group_name in SYNONYM_FORM_MAP:
        payload[group_name] = result.get(group_name, [])
    return payload


def store_synonym_forms(
    session: Session,
    lemma: Lemma,
    language_code: str,
    synonym_groups: Dict[str, List[str]],
    abbreviations: List[str],
    expanded_forms: List[str],
) -> Dict[str, int]:
    """Persist synonym/abbreviation/expanded-form rows.

    Returns a dict with counts under ``synonyms``, ``abbreviations``, and
    ``expanded_forms``. Individual insert failures are logged and skipped
    so a single bad form doesn't abort the batch.
    """
    stored_counts = {
        "synonyms": 0,
        "abbreviations": 0,
        "expanded_forms": 0,
    }

    for group_name, forms in synonym_groups.items():
        grammatical_form = SYNONYM_FORM_MAP[group_name]
        for synonym in forms:
            existing_owner = (
                session.query(DerivativeForm)
                .filter(
                    DerivativeForm.derivative_form_text == synonym,
                    DerivativeForm.language_code == language_code,
                    DerivativeForm.grammatical_form.in_(tuple(SYNONYM_GRAMMATICAL_FORMS)),
                    DerivativeForm.lemma_id != lemma.id,
                )
                .first()
            )
            if existing_owner is not None:
                logger.warning(
                    "Skipping synonym '%s' (%s) for lemma %s: already attached to lemma %s as '%s'",
                    synonym,
                    grammatical_form,
                    lemma.id,
                    existing_owner.lemma_id,
                    existing_owner.grammatical_form,
                )
                continue
            try:
                word_token = add_word_token(session, synonym, language_code)
                add_derivative_form(
                    session=session,
                    lemma=lemma,
                    derivative_form_text=synonym,
                    language_code=language_code,
                    grammatical_form=grammatical_form,
                    word_token=word_token,
                    verified=False,
                )
                stored_counts["synonyms"] += 1
            except Exception as error:
                logger.warning(
                    "Failed to store synonym '%s' (%s): %s", synonym, grammatical_form, error
                )

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
        except Exception as error:
            logger.warning("Failed to store abbreviation '%s': %s", abbr, error)

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
        except Exception as error:
            logger.warning("Failed to store expanded form '%s': %s", exp_form, error)

    return stored_counts


# The paradigm slot that holds a variant's own base form, per POS. Keys are the
# form keys produced by the langtools.en builders. English only: variants in
# other languages are stored as a bare base form (see store_spelling_variants).
_EN_BASE_FORM_KEY: Dict[str, str] = {
    "noun": "singular",
    "adjective": "positive",
    "adverb": "positive",
    "verb": "infinitive",
}


def _variant_form_mapping(language_code: str, pos_type: str) -> Dict[str, str]:
    """Map builder form keys to ``grammatical_form`` values, or ``{}``."""
    # Lazy-imported for the same reason as LinguisticClient below: the
    # langtools package imports back into words.
    from langtools.form_registry import FORM_SPECS

    try:
        spec = FORM_SPECS[(language_code, pos_type.lower())]
    except KeyError:
        return {}
    return {
        form_key: getattr(grammatical_form, "value", str(grammatical_form))
        for form_key, grammatical_form in spec.form_mapping.items()
    }


def _variant_base_grammatical_form(language_code: str, pos_type: str) -> Optional[str]:
    """The ``grammatical_form`` naming a variant's base form, or ``None``."""
    normalized_pos = pos_type.lower()
    base_form_key = _EN_BASE_FORM_KEY.get(normalized_pos)
    if base_form_key is None:
        return None
    return _variant_form_mapping(language_code, normalized_pos).get(base_form_key)


def store_spelling_variants(
    session: Session,
    lemma: Lemma,
    language_code: str,
    alternate_spellings: List[str],
    variant_kind: str = VARIANT_KIND_SPELLING,
) -> int:
    """Persist alternate spellings as ``variant_forms`` rows.

    A spelling variant is the same lexeme as the lemma, so it does not belong
    in ``derivative_forms`` alongside synonyms; see
    ``storage.models.variant_form``. Callers only ever supply the variant's
    base form ("grey"), which is expanded into a full paradigm by the
    mechanical rules where they are confident. When they are not -- irregular
    words, unusual spellings -- only the base form is stored, and the remaining
    slots are left for a human to fill in via Barsukas.

    Only English is expanded mechanically; other languages store the base form
    alone, since the paradigm builders here are English-specific.

    Used both by the synonym generator (for the LLM's ``alternate_spellings``)
    and by the Barsukas "Add Variant" form.

    Args:
        session: Database session
        lemma: The lemma these are variants of
        language_code: Language of the variants (e.g. "en")
        alternate_spellings: Base forms of the variants (e.g. ``["grey"]``)
        variant_kind: Kind of variant; defaults to "spelling"

    Returns:
        Number of variant paradigms stored (not rows).
    """
    if not alternate_spellings:
        return 0

    stored_variants = 0
    for spelling in alternate_spellings:
        variant_key = spelling.strip()
        if not variant_key:
            continue

        paradigm: Dict[str, str] = {}
        if language_code == "en":
            # Lazy-imported to avoid a circular import via langtools -> words.
            from langtools.en.variants import build_variant_paradigm

            paradigm = (
                build_variant_paradigm(
                    lemma_text=lemma.lemma_text,
                    variant_text=variant_key,
                    pos_type=lemma.pos_type,
                    countability=get_grammar_fact_value(session, lemma.id, "en", "countability"),
                    number_type=get_grammar_fact_value(session, lemma.id, "en", "number_type"),
                    irregular_plural=get_grammar_fact_value(session, lemma.id, "en", "plural"),
                    gradability=get_grammar_fact_value(session, lemma.id, "en", "gradability"),
                    comparative=get_grammar_fact_value(session, lemma.id, "en", "comparative"),
                    superlative=get_grammar_fact_value(session, lemma.id, "en", "superlative"),
                    past=get_grammar_fact_value(session, lemma.id, "en", "past"),
                    past_participle=get_grammar_fact_value(
                        session, lemma.id, "en", "past_participle"
                    ),
                )
                or {}
            )

        form_mapping = _variant_form_mapping(language_code, lemma.pos_type)
        base_grammatical_form = _variant_base_grammatical_form(language_code, lemma.pos_type)

        # Fall back to the bare base form when the rules declined to expand, so
        # duplicate detection still recognizes the spelling.
        rows: List[Tuple[str, str, bool]] = []
        if paradigm and form_mapping:
            for form_key, form_text in paradigm.items():
                grammatical_form = form_mapping.get(form_key)
                if grammatical_form is None:
                    continue
                rows.append(
                    (
                        str(grammatical_form),
                        form_text,
                        str(grammatical_form) == base_grammatical_form,
                    )
                )
        elif base_grammatical_form:
            rows.append((base_grammatical_form, variant_key, True))

        if not rows:
            logger.warning(
                "Skipping spelling variant '%s' for lemma %s: no grammatical form for %s/%s",
                variant_key,
                lemma.id,
                language_code,
                lemma.pos_type,
            )
            continue

        try:
            for grammatical_form, form_text, is_base_form in rows:
                add_variant_form(
                    session=session,
                    lemma=lemma,
                    variant_form_text=form_text,
                    language_code=language_code,
                    variant_key=variant_key,
                    grammatical_form=grammatical_form,
                    variant_kind=variant_kind,
                    is_base_form=is_base_form,
                    verified=False,
                )
            stored_variants += 1
        except Exception as error:
            logger.warning("Failed to store spelling variant '%s': %s", variant_key, error)

    return stored_variants


def record_synonym_processing_metadata(
    session: Session,
    lemma_id: int,
    language_code: str,
    stored_counts: Dict[str, int],
) -> None:
    """Mark the lemma/language as processed and record summary grammar facts."""
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
    log_operation(
        session,
        operation_type="synonym_scan",
        source=f"sernas-agent:{language_code}",
        lemma_id=lemma_id,
        details={
            "stored_synonyms": stored_counts["synonyms"],
            "stored_abbreviations": stored_counts["abbreviations"],
            "stored_expanded_forms": stored_counts["expanded_forms"],
            "stored_spelling_variants": stored_counts.get("spelling_variants", 0),
        },
    )


def generate_synonyms_for_lemma(
    session: Session,
    lemma: Lemma,
    language_code: str = "en",
    config: Optional[DataSourceConfig] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Generate and (unless ``dry_run``) store synonyms for one lemma/language.

    This is the orchestrating function used by both the workqueue handler
    and the ŠERNAS agent. It does NOT commit the session — callers commit.
    """
    if language_code == "en":
        word: Optional[str] = lemma.lemma_text
    else:
        word = get_translation(session, lemma, language_code)

    if not word or not word.strip():
        return {
            "error": f"No translation found for language {language_code}",
            "lemma_id": lemma.id,
            "language_code": language_code,
        }

    logger.info("Generating synonyms for '%s' (%s)", word, language_code)

    if config is None:
        # Lazy import to avoid pulling workqueue at module load.
        from workqueue.tools import build_default_config

        config = build_default_config()

    result = query_synonyms_from_llm(
        config=config,
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

    synonym_groups: Dict[str, List[str]] = {
        group_name: normalize_generated_forms(result.get(group_name, []), word)
        for group_name in SYNONYM_FORM_MAP
    }

    # Flatten across categories for the return value, preserving SYNONYM_FORM_MAP order.
    synonyms: List[str] = []
    synonym_seen: set[str] = set()
    for group_name in SYNONYM_FORM_MAP:
        for synonym in synonym_groups[group_name]:
            dedup_key = synonym.casefold()
            if dedup_key not in synonym_seen:
                synonym_seen.add(dedup_key)
                synonyms.append(synonym)

    abbreviations = normalize_generated_forms(result.get("abbreviations", []), word)
    expanded_forms = normalize_generated_forms(result.get("expanded_forms", []), word)
    # Alternate spellings are stored in variant_forms rather than as synonyms,
    # so they are normalized separately from SYNONYM_FORM_MAP's categories.
    alternate_spellings = normalize_generated_forms(result.get("alternate_spellings", []), word)

    if dry_run:
        return {
            "dry_run": True,
            "lemma_id": lemma.id,
            "language_code": language_code,
            "word": word,
            "synonyms": synonyms,
            "abbreviations": abbreviations,
            "expanded_forms": expanded_forms,
            "synecdoche_variants": synonym_groups.get("synecdoche_variants", []),
            "alternate_spellings": alternate_spellings,
            "total_count": len(synonyms) + len(abbreviations) + len(expanded_forms),
        }

    stored_counts = store_synonym_forms(
        session=session,
        lemma=lemma,
        language_code=language_code,
        synonym_groups=synonym_groups,
        abbreviations=abbreviations,
        expanded_forms=expanded_forms,
    )
    stored_counts["spelling_variants"] = store_spelling_variants(
        session=session,
        lemma=lemma,
        language_code=language_code,
        alternate_spellings=alternate_spellings,
    )

    record_synonym_processing_metadata(session, lemma.id, language_code, stored_counts)

    logger.info(
        "Stored %d synonym variants, %d abbreviations, %d expanded forms, "
        "and %d spelling variants",
        stored_counts["synonyms"],
        stored_counts["abbreviations"],
        stored_counts["expanded_forms"],
        stored_counts["spelling_variants"],
    )

    return {
        "success": True,
        "lemma_id": lemma.id,
        "language_code": language_code,
        "word": word,
        "synonyms": synonyms,
        "abbreviations": abbreviations,
        "expanded_forms": expanded_forms,
        "synecdoche_variants": synonym_groups.get("synecdoche_variants", []),
        "alternate_spellings": alternate_spellings,
        "stored_synonyms": stored_counts["synonyms"],
        "stored_abbreviations": stored_counts["abbreviations"],
        "stored_expanded": stored_counts["expanded_forms"],
        "stored_expanded_forms": stored_counts["expanded_forms"],
        "stored_spelling_variants": stored_counts["spelling_variants"],
    }


__all__ = [
    "SYNONYM_FORM_MAP",
    "SYNONYMS_JSON_SCHEMA",
    "build_synonyms_prompt",
    "query_synonyms",
    "normalize_generated_forms",
    "query_synonyms_from_llm",
    "store_synonym_forms",
    "store_spelling_variants",
    "record_synonym_processing_metadata",
    "generate_synonyms_for_lemma",
]
