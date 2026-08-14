"""Synonym screening for pending word imports."""

import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from sqlalchemy import func
from sqlalchemy.orm import Session

from clients.types import Schema, SchemaProperty
from storage.models.imports import PendingImport, PendingImportSynonymCandidate
from storage.models.schema import Lemma
from storage.translation_helpers import (
    LANG_CODE_TO_LLM_FIELD,
    convert_llm_response_to_lang_codes,
    get_translation,
)

logger = logging.getLogger(__name__)

DEFAULT_SYNONYM_SCREEN_LANGUAGES: Tuple[str, ...] = (
    "lt",
    "zh",
    "fr",
    "es",
    "de",
    "it",
    "nl",
    "pt",
    "sv",
    "uk",
    "bn",
    "kn",
)

STRONG_SYNONYM_CATEGORIES: frozenset[str] = frozenset({"strong", "near"})
STRONG_TRANSLATION_MATCH_THRESHOLD = 3
ACTIVE_STATUS = "active"
IGNORED_STATUS = "ignored"
ACCEPTED_STATUS = "accepted"


def normalize_translation(value: str) -> str:
    """Normalize text for conservative exact translation comparisons."""
    return " ".join(value.split()).casefold()


def _translation_schema_properties(language_codes: Sequence[str]) -> Dict[str, SchemaProperty]:
    properties: Dict[str, SchemaProperty] = {}
    for language_code in language_codes:
        field_name = LANG_CODE_TO_LLM_FIELD.get(language_code)
        if field_name is None:
            continue
        properties[field_name] = SchemaProperty(
            "string",
            f"Translation for this exact sense in language code {language_code}",
        )
    return properties


def build_synonym_screening_schema(language_codes: Sequence[str]) -> Schema:
    """Build the structured-response schema for synonym screening."""
    properties: Dict[str, SchemaProperty] = {
        "candidate_synonyms": SchemaProperty(
            type="array",
            description="Existing English lemmas that may be synonyms of the pending word",
            array_items_schema=Schema(
                name="CandidateSynonym",
                description="One candidate existing English synonym lemma",
                properties={
                    "lemma": SchemaProperty("string", "English lemma text for the candidate"),
                    "synonymy": SchemaProperty(
                        "string",
                        "How synonymous the candidate is",
                        enum=["strong", "near", "related", "not_synonym"],
                    ),
                    "score": SchemaProperty(
                        "number",
                        "Synonymy score from 0 to 1, where 1 means fully interchangeable",
                    ),
                    "explanation": SchemaProperty(
                        "string",
                        "Brief reason for the synonymy judgment",
                    ),
                },
            ),
        )
    }
    properties.update(_translation_schema_properties(language_codes))
    return Schema(
        name="PendingImportSynonymScreen",
        description="Candidate synonyms and translations for a pending import",
        properties=properties,
    )


def build_synonym_screening_prompt(
    pending_import: PendingImport, language_codes: Sequence[str]
) -> str:
    language_list = ", ".join(language_codes)
    context_sentence = ""
    if pending_import.example_sentence:
        context_sentence = f"\nExample sentence: {pending_import.example_sentence}"
    pos_line = pending_import.pos_type or "unknown"
    subtype_line = pending_import.pos_subtype or "unknown"
    return (
        "Analyze this pending English vocabulary import before a new lemma is created.\n"
        "First suggest existing English lemmas that could already cover this concept as "
        "synonyms. Then translate the pending word's exact intended sense into the requested "
        "languages.\n\n"
        f"Pending word: {pending_import.english_word}\n"
        f"Definition: {pending_import.definition}\n"
        f"Part of speech: {pos_line}\n"
        f"POS subtype: {subtype_line}"
        f"{context_sentence}\n\n"
        "Return candidate English lemma texts, not inflected forms. Prefer likely existing "
        "database headwords such as 'fast' for 'speedily'. Use synonymy 'strong' only when "
        "the words are usually interchangeable for this sense; use 'near' for close synonyms.\n"
        f"Translation language codes: {language_list}"
    )


def query_synonym_screening_llm(
    llm_client: Any,
    pending_import: PendingImport,
    *,
    model: str,
    language_codes: Sequence[str] = DEFAULT_SYNONYM_SCREEN_LANGUAGES,
) -> Dict[str, Any]:
    """Ask an LLM for candidate synonyms and sense translations."""
    schema = build_synonym_screening_schema(language_codes)
    prompt = build_synonym_screening_prompt(pending_import, language_codes)
    response = llm_client.generate_chat(prompt=prompt, model=model, json_schema=schema)
    structured_data = getattr(response, "structured_data", None)
    if not isinstance(structured_data, dict):
        raise ValueError("LLM returned no structured synonym screening data")
    return structured_data


def extract_candidate_translations(
    llm_response: Dict[str, Any], language_codes: Sequence[str]
) -> Dict[str, str]:
    """Extract supported language-code translations from an LLM response."""
    raw_translations: Dict[str, str] = {}
    for field_name, response_value in llm_response.items():
        if not isinstance(response_value, str):
            continue
        raw_translations[field_name] = response_value
    translations = convert_llm_response_to_lang_codes(raw_translations)
    return {
        language_code: translation.strip()
        for language_code, translation in translations.items()
        if language_code in language_codes and translation.strip()
    }


def _resolve_candidate_lemma(
    session: Session, candidate_text: str, pending_pos_type: Optional[str]
) -> Optional[Lemma]:
    normalized_text = candidate_text.strip().casefold()
    if not normalized_text:
        return None
    query = session.query(Lemma).filter(func.lower(Lemma.lemma_text) == normalized_text)
    all_matches = query.order_by(Lemma.id).all()
    if not all_matches:
        return None
    if pending_pos_type:
        for candidate_lemma in all_matches:
            if candidate_lemma.pos_type == pending_pos_type:
                return cast(Lemma, candidate_lemma)
    return cast(Lemma, all_matches[0])


def find_matching_translation_languages(
    session: Session,
    lemma: Lemma,
    pending_translations: Dict[str, str],
    language_codes: Sequence[str] = DEFAULT_SYNONYM_SCREEN_LANGUAGES,
) -> List[str]:
    """Return languages where pending and existing lemma translations match exactly."""
    matched_languages: List[str] = []
    for language_code in language_codes:
        pending_translation = pending_translations.get(language_code)
        if not pending_translation:
            continue
        existing_translation = get_translation(session, lemma, language_code)
        if not existing_translation:
            continue
        if normalize_translation(existing_translation) == normalize_translation(
            pending_translation
        ):
            matched_languages.append(language_code)
    return matched_languages


def _candidate_is_strong(
    *,
    same_pos: bool,
    synonym_category: str,
    matched_translation_count: int,
) -> bool:
    return (
        same_pos
        and synonym_category.casefold() in STRONG_SYNONYM_CATEGORIES
        and matched_translation_count >= STRONG_TRANSLATION_MATCH_THRESHOLD
    )


def clear_synonym_candidates(session: Session, pending_import_id: int) -> None:
    """Delete existing synonym-screen rows for a pending import before refreshing."""
    session.query(PendingImportSynonymCandidate).filter(
        PendingImportSynonymCandidate.pending_import_id == pending_import_id
    ).delete(synchronize_session=False)


def store_synonym_screening_candidates(
    session: Session,
    pending_import: PendingImport,
    llm_response: Dict[str, Any],
    *,
    language_codes: Sequence[str] = DEFAULT_SYNONYM_SCREEN_LANGUAGES,
) -> List[PendingImportSynonymCandidate]:
    """Persist synonym candidates from a structured LLM response."""
    pending_translations = extract_candidate_translations(llm_response, language_codes)
    clear_synonym_candidates(session, pending_import.id)

    raw_candidates = llm_response.get("candidate_synonyms", [])
    if not isinstance(raw_candidates, list):
        raw_candidates = []

    stored_candidates: List[PendingImportSynonymCandidate] = []
    seen_texts: set[str] = set()
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            continue
        candidate_text_value = raw_candidate.get("lemma")
        if not isinstance(candidate_text_value, str):
            continue
        candidate_text = candidate_text_value.strip()
        normalized_candidate_text = candidate_text.casefold()
        if not candidate_text or normalized_candidate_text in seen_texts:
            continue
        seen_texts.add(normalized_candidate_text)

        resolved_lemma = _resolve_candidate_lemma(session, candidate_text, pending_import.pos_type)
        same_pos = bool(
            resolved_lemma is not None
            and pending_import.pos_type is not None
            and resolved_lemma.pos_type == pending_import.pos_type
        )
        matched_languages: List[str] = []
        if resolved_lemma is not None:
            matched_languages = find_matching_translation_languages(
                session,
                resolved_lemma,
                pending_translations,
                language_codes,
            )

        synonym_category_value = raw_candidate.get("synonymy", "related")
        synonym_category = (
            synonym_category_value if isinstance(synonym_category_value, str) else "related"
        )
        score_value = raw_candidate.get("score")
        synonym_score = float(score_value) if isinstance(score_value, (int, float)) else None
        explanation_value = raw_candidate.get("explanation")
        explanation = explanation_value if isinstance(explanation_value, str) else None
        is_strong = _candidate_is_strong(
            same_pos=same_pos,
            synonym_category=synonym_category,
            matched_translation_count=len(matched_languages),
        )

        candidate = PendingImportSynonymCandidate(
            pending_import_id=pending_import.id,
            lemma_id=resolved_lemma.id if resolved_lemma is not None else None,
            candidate_text=candidate_text,
            same_pos=same_pos,
            llm_synonym_category=synonym_category,
            llm_synonym_score=synonym_score,
            matched_translation_count=len(matched_languages),
            matched_translation_languages=json.dumps(matched_languages, ensure_ascii=False),
            candidate_translations=json.dumps(pending_translations, ensure_ascii=False),
            explanation=explanation,
            is_strong=is_strong,
            status=ACTIVE_STATUS,
        )
        session.add(candidate)
        stored_candidates.append(candidate)

    session.flush()
    return stored_candidates


def run_synonym_screening(
    session: Session,
    pending_import: PendingImport,
    llm_client: Any,
    *,
    model: str,
    language_codes: Sequence[str] = DEFAULT_SYNONYM_SCREEN_LANGUAGES,
) -> List[PendingImportSynonymCandidate]:
    """Run the LLM synonym screen and persist candidate rows."""
    try:
        llm_response = query_synonym_screening_llm(
            llm_client,
            pending_import,
            model=model,
            language_codes=language_codes,
        )
        return store_synonym_screening_candidates(
            session,
            pending_import,
            llm_response,
            language_codes=language_codes,
        )
    except Exception as exc:
        logger.warning(
            "Synonym screening failed for pending import %s (%s): %s",
            pending_import.id,
            pending_import.english_word,
            exc,
        )
        return []


def has_active_strong_synonym_candidate(session: Session, pending_import_id: int) -> bool:
    """Return whether a pending import has a blocking synonym candidate."""
    candidate_count = (
        session.query(PendingImportSynonymCandidate)
        .filter(
            PendingImportSynonymCandidate.pending_import_id == pending_import_id,
            PendingImportSynonymCandidate.status == ACTIVE_STATUS,
            PendingImportSynonymCandidate.is_strong.is_(True),
        )
        .count()
    )
    return int(candidate_count) > 0


def ignore_synonym_candidates(session: Session, pending_import_id: int) -> int:
    """Mark active candidates ignored so normal approval can continue."""
    return int(
        session.query(PendingImportSynonymCandidate)
        .filter(
            PendingImportSynonymCandidate.pending_import_id == pending_import_id,
            PendingImportSynonymCandidate.status == ACTIVE_STATUS,
        )
        .update(
            {PendingImportSynonymCandidate.status: IGNORED_STATUS},
            synchronize_session=False,
        )
    )
