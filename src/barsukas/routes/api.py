#!/usr/bin/python3

"""API routes for AJAX requests and REST API endpoints."""

from typing import Any, Dict, List, Optional, Tuple, Union

from barsukas.config import Config
from flask import Blueprint, Response, g, jsonify, request
from flask.typing import ResponseReturnValue
from sqlalchemy import func, or_

from wordfreq.storage.crud.grammar_fact import get_grammar_facts
from wordfreq.storage.crud.lemma import get_lemma_by_guid
from wordfreq.storage.models import (
    DerivativeForm,
    GrammarFact,
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from wordfreq.storage.queries.lemma import build_lemma_search_query
from wordfreq.storage.translation_helpers import LANGUAGE_HIERARCHY, get_all_translations

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/check_lemma_exists")
def check_lemma_exists() -> ResponseReturnValue:
    """Check if a lemma exists or find similar lemmas."""
    search = request.args.get("search", "").strip()
    pos_type = request.args.get("pos_type", "").strip()

    if not search:
        return jsonify({"exact_match": None, "similar_matches": []})

    # Check for exact match
    exact_query = g.db.query(Lemma).filter(func.lower(Lemma.lemma_text) == search.lower())
    if pos_type:
        exact_query = exact_query.filter(Lemma.pos_type == pos_type)

    exact_match = exact_query.first()

    # Find similar matches (case-insensitive LIKE search)
    similar_query = g.db.query(Lemma).filter(Lemma.lemma_text.ilike(f"%{search}%"))

    # If exact match found, exclude it from similar matches
    if exact_match:
        similar_query = similar_query.filter(Lemma.id != exact_match.id)

    similar_matches = similar_query.limit(5).all()

    return jsonify(
        {
            "exact_match": (
                {
                    "id": exact_match.id,
                    "lemma_text": exact_match.lemma_text,
                    "pos_type": exact_match.pos_type,
                    "definition_text": exact_match.definition_text,
                }
                if exact_match
                else None
            ),
            "similar_matches": [
                {
                    "id": lemma.id,
                    "lemma_text": lemma.lemma_text,
                    "pos_type": lemma.pos_type,
                    "definition_text": lemma.definition_text,
                }
                for lemma in similar_matches
            ],
        }
    )


@bp.route("/auto_populate_lemma")
def auto_populate_lemma() -> ResponseReturnValue:
    """Auto-populate lemma fields using LLM based on word and optional translation."""
    word = request.args.get("word", "").strip()
    translation = request.args.get("translation", "").strip()
    lang_code = request.args.get("lang_code", "").strip()

    if not word:
        return jsonify({"success": False, "error": "Word is required"})

    try:
        # Use LLM to generate definition, POS type, and POS subtype
        from wordfreq.translation.client import LinguisticClient

        client = LinguisticClient(model="gpt-5-mini", db_path=Config.DB_PATH, debug=Config.DEBUG)

        # Build prompt for LLM
        if translation and lang_code:
            context = f'English word: "{word}"\n{lang_code.upper()} translation: "{translation}"'
        else:
            context = f'English word: "{word}"'

        prompt = f"""Analyze this word and provide its linguistic properties:

{context}

Provide:
1. A clear, concise definition (1-2 sentences)
2. Part of speech (pos_type): Choose from: noun, verb, adjective, adverb, pronoun, preposition, conjunction, interjection, determiner, numeral
3. Part of speech subtype (pos_subtype): Choose the most appropriate:
   - For nouns: animal, body_part, building_structure, clothing_accessory, concept_idea, emotion_feeling, food, beverage, furniture, vehicle, plant, plant_part, human, material_substance, nationality, natural_feature, personal_name, place_name, small_movable_object, temporal_name, time_period, tool_machine, unit_of_measurement
   - For verbs: physical_action, creation_action, destruction_action, mental_state, emotional_state, perception, communication, possession, existence, development, change, directional_movement, manner_movement
   - For adjectives: size, color, shape, texture, personal_quality, condition, quality, aesthetic, importance, origin, purpose, material, indefinite_quantity, duration, frequency, sequence
   - For adverbs: style, attitude, specific_time, relative_time, duration, direction, location, distance, intensity, completeness, approximation, definite_frequency, indefinite_frequency
   - For numerals: cardinal, ordinal
   - For other POS: use appropriate subtype or "other"

The definition should be suitable for language learners."""

        # Define schema for structured output
        from clients.types import Schema, SchemaProperty

        schema = Schema(
            name="LemmaProperties",
            description="Linguistic properties of a word",
            properties={
                "definition": SchemaProperty(
                    type="string",
                    description="Clear, concise definition of the word (1-2 sentences)",
                ),
                "pos_type": SchemaProperty(type="string", description="Part of speech type"),
                "pos_subtype": SchemaProperty(type="string", description="Part of speech subtype"),
            },
        )

        response = client.client.generate_chat(
            prompt=prompt, model="gpt-5-mini", json_schema=schema, timeout=30
        )

        if not response.structured_data:
            return jsonify(
                {"success": False, "error": "Failed to get structured response from LLM"}
            )

        result = response.structured_data

        # Get the maximum difficulty level for this pos_subtype
        max_level = None
        if result.get("pos_subtype"):
            max_level_query = (
                g.db.query(func.max(Lemma.difficulty_level))
                .filter(
                    Lemma.pos_subtype == result["pos_subtype"],
                    Lemma.difficulty_level.isnot(None),
                    Lemma.difficulty_level != -1,  # Exclude "excluded" words
                )
                .scalar()
            )
            if max_level_query:
                max_level = int(max_level_query)

        return jsonify(
            {
                "success": True,
                "definition": result.get("definition", ""),
                "pos_type": result.get("pos_type", ""),
                "pos_subtype": result.get("pos_subtype", ""),
                "suggested_difficulty_level": max_level,
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ============================================================================
# REST API v1 - Read-only endpoints for external consumption
# ============================================================================


@bp.route("/v1")
def api_info() -> ResponseReturnValue:
    """
    Get information about the API and available endpoints.

    Returns:
        - version: API version
        - endpoints: List of available endpoints with descriptions
    """
    endpoints = [
        {
            "path": "/api/v1/search",
            "method": "GET",
            "description": "Search for lemmas by keyword",
            "parameters": [
                {
                    "name": "q",
                    "type": "query",
                    "required": True,
                    "description": "Search query (searches lemma text, definition, disambiguation, translations)",
                },
                {
                    "name": "pos_type",
                    "type": "query",
                    "required": False,
                    "description": "Filter by part of speech (e.g., 'noun', 'verb')",
                },
                {
                    "name": "difficulty",
                    "type": "query",
                    "required": False,
                    "description": "Filter by difficulty level (1-20, '-1' for excluded, 'null' for not set)",
                },
                {
                    "name": "limit",
                    "type": "query",
                    "required": False,
                    "description": "Max results to return (default: 20, max: 100)",
                },
                {
                    "name": "offset",
                    "type": "query",
                    "required": False,
                    "description": "Number of results to skip for pagination (default: 0)",
                },
            ],
        },
        {
            "path": "/api/v1/lemma/<guid>",
            "method": "GET",
            "description": "Get basic information about a lemma",
            "parameters": [],
        },
        {
            "path": "/api/v1/lemma/<guid>/translations",
            "method": "GET",
            "description": "Get translations of a lemma in various languages",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to specific language code (e.g., 'zh', 'fr', 'lt')",
                }
            ],
        },
        {
            "path": "/api/v1/lemma/<guid>/forms",
            "method": "GET",
            "description": "Get derivative/declined forms of a lemma",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to specific language code (e.g., 'zh', 'fr', 'lt')",
                }
            ],
        },
        {
            "path": "/api/v1/lemma/<guid>/grammar",
            "method": "GET",
            "description": "Get grammar facts about a lemma",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to specific language code (e.g., 'zh', 'fr', 'lt')",
                }
            ],
        },
        {
            "path": "/api/v1/lemma/<guid>/pronunciations",
            "method": "GET",
            "description": "Get pronunciations (IPA and phonetic) for base forms of a lemma",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to specific language code (e.g., 'en', 'lt', 'fr')",
                }
            ],
        },
        {
            "path": "/api/v1/lemma/<guid>/sentences",
            "method": "GET",
            "description": "Get example sentences that use this lemma",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter sentence translations to specific language code",
                }
            ],
        },
    ]

    return jsonify(
        {
            "version": "1.0",
            "description": "Read-only API for accessing lemma information",
            "endpoints": endpoints,
        }
    )


@bp.route("/v1/search")
def search_lemmas() -> ResponseReturnValue:
    """
    Search for lemmas by keyword across multiple fields.

    Query parameters:
        - q: Required. Search query to find in lemma text, definition, disambiguation, and translations
        - pos_type: Optional. Filter by part of speech (e.g., 'noun', 'verb')
        - difficulty: Optional. Filter by difficulty level (1-20, '-1' for excluded, 'null' for not set)
        - limit: Optional. Maximum number of results to return (default: 20, max: 100)
        - offset: Optional. Number of results to skip for pagination (default: 0)

    Returns a list of matching lemmas with enough information to distinguish between them.
    Each result includes:
        - guid: The lemma's unique identifier
        - lemma_text: The lemma's base form (in English)
        - definition: The English definition (truncated if very long)
        - pos_type: Part of speech type
        - pos_subtype: Part of speech subtype (if populated)
        - difficulty_level: Difficulty level (or null)
        - disambiguation: Disambiguation text (or null)
        - translations: Sample of available translations (up to 3 languages)
        - verified: Whether the lemma has been verified

    The results are ordered by relevance (exact matches first, then starts-with, then contains).

    Example:
        GET /api/v1/search?q=tire
        GET /api/v1/search?q=dog&pos_type=noun&difficulty=1
        GET /api/v1/search?q=gyventi&limit=10&offset=0
    """
    # Get query parameters
    search_query = request.args.get("q", "").strip()
    pos_type = request.args.get("pos_type", "").strip()
    difficulty = request.args.get("difficulty", "").strip()

    # Pagination parameters
    try:
        limit = min(int(request.args.get("limit", "20")), 100)  # Max 100 results
    except ValueError:
        limit = 20

    try:
        offset = max(int(request.args.get("offset", "0")), 0)
    except ValueError:
        offset = 0

    # Validate required parameter
    if not search_query:
        return _build_error_response("Query parameter 'q' is required", 400)

    # Build the search query using existing function
    query = build_lemma_search_query(
        session=g.db,
        search=search_query,
        pos_type=pos_type or None,
        difficulty=difficulty or None,
    )

    # Get total count before pagination
    total_count = query.count()

    # Apply pagination
    results = query.limit(limit).offset(offset).all()

    # Bulk fetch all translations for all results in ONE query (replaces N separate queries)
    from barsukas.helpers.db_optimization import bulk_get_translations_for_lemmas

    all_translations_by_lemma = bulk_get_translations_for_lemmas(g.db, results)

    # Serialize results with enough info to distinguish between them
    lemmas_data = []
    for lemma in results:
        # Get translations from bulk-fetched data
        all_translations_raw = all_translations_by_lemma.get(lemma.id, {"en": lemma.lemma_text})
        all_translations = {
            k: v for k, v in all_translations_raw.items() if v is not None and v.strip()
        }

        # Pick up to 3 translations to show (follows LANGUAGE_HIERARCHY from translation_helpers)
        # Exclude 'en' since it's the source language (stored in lemma_text, not as a translation)
        priority_langs = [lang for lang in LANGUAGE_HIERARCHY if lang != "en"]
        sample_translations = {}
        for lang in priority_langs:
            if lang in all_translations:
                sample_translations[lang] = all_translations[lang]
                if len(sample_translations) >= 3:
                    break

        # If we don't have 3 yet, add any remaining
        if len(sample_translations) < 3:
            for lang, trans in all_translations.items():
                if lang not in sample_translations:
                    sample_translations[lang] = trans
                    if len(sample_translations) >= 3:
                        break

        # Truncate definition if very long (keep first 200 chars)
        definition = lemma.definition_text
        if len(definition) > 200:
            definition = definition[:197] + "..."

        lemmas_data.append(
            {
                "guid": lemma.guid,
                "lemma_text": lemma.lemma_text,
                "definition": definition,
                "pos_type": lemma.pos_type,
                "pos_subtype": _serialize_value(lemma.pos_subtype),
                "difficulty_level": _serialize_value(lemma.difficulty_level),
                "disambiguation": _serialize_value(lemma.disambiguation),
                "translations": sample_translations,
                "verified": lemma.verified,
            }
        )

    # Build metadata
    metadata = {
        "query": search_query,
        "total_results": total_count,
        "limit": limit,
        "offset": offset,
        "returned": len(lemmas_data),
    }

    if pos_type:
        metadata["pos_type_filter"] = pos_type
    if difficulty:
        metadata["difficulty_filter"] = difficulty

    # Add pagination info
    metadata["has_more"] = (offset + limit) < total_count
    if metadata["has_more"]:
        metadata["next_offset"] = offset + limit

    return _build_success_response(lemmas_data, metadata)


def _serialize_value(value: Any, field_name: str = "") -> Any:
    """
    Serialize a value for JSON response, preserving None/null for unpopulated fields.

    This helps distinguish between:
    - None/null: field hasn't been populated yet
    - False: field is explicitly false
    - Empty string: field is explicitly empty (but populated)
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value
    return str(value)


def _build_error_response(message: str, status_code: int = 400) -> ResponseReturnValue:
    """Build a standardized error response."""
    return jsonify({"error": message}), status_code


def _build_success_response(
    data: Union[Dict[str, Any], List[Dict[str, Any]]], metadata: Optional[Dict[str, Any]] = None
) -> ResponseReturnValue:
    """Build a standardized success response with optional metadata."""
    response: Dict[str, Any] = {"data": data}
    if metadata:
        response["metadata"] = metadata
    return jsonify(response)


@bp.route("/v1/lemma/<guid>")
def get_lemma_info(guid: str) -> ResponseReturnValue:
    """
    Get basic information about a lemma by GUID.

    Returns:
        - guid: The lemma's unique identifier
        - lemma_text: The lemma's base form (in English)
        - definition: The English definition
        - pos_type: Part of speech type (noun, verb, etc.)
        - pos_subtype: Part of speech subtype (if populated)
        - difficulty_level: Difficulty level (1-20, or -1 for excluded, or null if not set)
        - verified: Whether the lemma has been human-verified
        - tags: JSON array of tags (or null if not set)
        - disambiguation: Disambiguation text (or null)

    Example:
        GET /api/v1/lemma/N01_001
    """
    lemma = get_lemma_by_guid(g.db, guid)

    if not lemma:
        return _build_error_response(f"Lemma with GUID '{guid}' not found", 404)

    data = {
        "guid": lemma.guid,
        "lemma_text": lemma.lemma_text,
        "definition": lemma.definition_text,
        "pos_type": lemma.pos_type,
        "pos_subtype": _serialize_value(lemma.pos_subtype),
        "difficulty_level": _serialize_value(lemma.difficulty_level),
        "verified": lemma.verified,
        "tags": _serialize_value(lemma.tags),
        "disambiguation": _serialize_value(lemma.disambiguation),
    }

    return _build_success_response(data)


@bp.route("/v1/lemma/<guid>/translations")
def get_lemma_translations(guid: str) -> ResponseReturnValue:
    """
    Get translations of a lemma in various languages.

    Query parameters:
        - language: Optional. Filter to a specific language code (e.g., 'zh', 'fr', 'lt')

    Returns a dictionary mapping language codes to translations.
    Languages with no translation will not appear in the response (distinguishing
    "not populated" from "explicitly empty").

    Example:
        GET /api/v1/lemma/N01_001/translations
        GET /api/v1/lemma/N01_001/translations?language=zh
    """
    lemma = get_lemma_by_guid(g.db, guid)

    if not lemma:
        return _build_error_response(f"Lemma with GUID '{guid}' not found", 404)

    language_filter = request.args.get("language", "").strip().lower()

    # Get all translations for this lemma (only include populated ones)
    all_translations_raw = get_all_translations(g.db, lemma)
    all_translations = {
        k: v for k, v in all_translations_raw.items() if v is not None and v.strip()
    }

    # Filter by language if requested
    translations: Dict[str, str]
    if language_filter:
        if language_filter in all_translations:
            translations = {language_filter: all_translations[language_filter]}
        else:
            translations = {}
    else:
        translations = all_translations

    # Add metadata about available vs requested
    metadata: Dict[str, Any] = {
        "guid": guid,
        "available_languages": list(all_translations.keys()),
    }

    if language_filter:
        metadata["requested_language"] = language_filter
        metadata["is_populated"] = language_filter in all_translations

    return _build_success_response(translations, metadata)


@bp.route("/v1/lemma/<guid>/forms")
def get_lemma_forms(guid: str) -> ResponseReturnValue:
    """
    Get derivative/declined forms of a lemma (conjugations, declensions, etc.).

    Query parameters:
        - language: Optional. Filter to a specific language code (e.g., 'zh', 'fr', 'lt')

    Returns a list of derivative forms, each containing:
        - form_text: The actual derivative form
        - language_code: Language of this form
        - grammatical_form: The grammatical form (e.g., "gerund", "1st_person_singular_present")
        - is_base_form: Whether this is the base/dictionary form
        - ipa_pronunciation: IPA pronunciation (if populated)
        - phonetic_pronunciation: Phonetic pronunciation (if populated)
        - verified: Whether this form has been verified

    Example:
        GET /api/v1/lemma/V01_001/forms
        GET /api/v1/lemma/V01_001/forms?language=lt
    """
    lemma = get_lemma_by_guid(g.db, guid)

    if not lemma:
        return _build_error_response(f"Lemma with GUID '{guid}' not found", 404)

    language_filter = request.args.get("language", "").strip().lower()

    # Query derivative forms
    query = g.db.query(DerivativeForm).filter(DerivativeForm.lemma_id == lemma.id)

    if language_filter:
        query = query.filter(DerivativeForm.language_code == language_filter)

    forms = query.order_by(
        DerivativeForm.language_code,
        DerivativeForm.is_base_form.desc(),
        DerivativeForm.grammatical_form,
    ).all()

    # Serialize forms
    forms_data = []
    languages_present = set()

    for form in forms:
        languages_present.add(form.language_code)
        forms_data.append(
            {
                "form_text": form.derivative_form_text,
                "language_code": form.language_code,
                "grammatical_form": form.grammatical_form,
                "is_base_form": form.is_base_form,
                "ipa_pronunciation": _serialize_value(form.ipa_pronunciation),
                "phonetic_pronunciation": _serialize_value(form.phonetic_pronunciation),
                "verified": form.verified,
            }
        )

    metadata = {
        "guid": guid,
        "count": len(forms_data),
        "languages_present": sorted(list(languages_present)),
    }

    if language_filter:
        metadata["requested_language"] = language_filter
        metadata["is_populated"] = len(forms_data) > 0

    return _build_success_response(forms_data, metadata)


@bp.route("/v1/lemma/<guid>/grammar")
def get_lemma_grammar(guid: str) -> ResponseReturnValue:
    """
    Get grammar facts about a lemma (e.g., gender, plurale tantum, declension class).

    Query parameters:
        - language: Optional. Filter to a specific language code (e.g., 'zh', 'fr', 'lt')

    Returns a list of grammar facts, each containing:
        - language_code: Language this fact applies to
        - fact_type: Type of grammatical fact (e.g., "gender", "number_type", "declension")
        - fact_value: The value of this fact (e.g., "masculine", "plurale_tantum", "1")
        - notes: Any additional notes (if present)
        - verified: Whether this fact has been verified

    Example:
        GET /api/v1/lemma/N05_012/grammar
        GET /api/v1/lemma/N05_012/grammar?language=lt
    """
    lemma = get_lemma_by_guid(g.db, guid)

    if not lemma:
        return _build_error_response(f"Lemma with GUID '{guid}' not found", 404)

    language_filter = request.args.get("language", "").strip().lower()

    # Query grammar facts
    query = g.db.query(GrammarFact).filter(GrammarFact.lemma_id == lemma.id)

    if language_filter:
        query = query.filter(GrammarFact.language_code == language_filter)

    facts = query.order_by(GrammarFact.language_code, GrammarFact.fact_type).all()

    # Serialize facts
    facts_data = []
    languages_present = set()

    for fact in facts:
        languages_present.add(fact.language_code)
        facts_data.append(
            {
                "language_code": fact.language_code,
                "fact_type": fact.fact_type,
                "fact_value": _serialize_value(fact.fact_value),
                "notes": _serialize_value(fact.notes),
                "verified": fact.verified,
            }
        )

    metadata = {
        "guid": guid,
        "count": len(facts_data),
        "languages_present": sorted(list(languages_present)),
    }

    if language_filter:
        metadata["requested_language"] = language_filter
        metadata["is_populated"] = len(facts_data) > 0

    return _build_success_response(facts_data, metadata)


@bp.route("/v1/lemma/<guid>/pronunciations")
def get_lemma_pronunciations(guid: str) -> ResponseReturnValue:
    """
    Get pronunciations for the base forms of a lemma.

    Query parameters:
        - language: Optional. Filter to a specific language code (e.g., 'en', 'lt', 'fr')

    Returns a dictionary mapping language codes to pronunciation objects.
    Each pronunciation object contains:
        - ipa: IPA pronunciation (if populated)
        - phonetic: Phonetic/simplified pronunciation (if populated)

    Only languages with at least one pronunciation populated will be included.

    Example:
        GET /api/v1/lemma/N01_001/pronunciations
        GET /api/v1/lemma/N01_001/pronunciations?language=en
    """
    lemma = get_lemma_by_guid(g.db, guid)

    if not lemma:
        return _build_error_response(f"Lemma with GUID '{guid}' not found", 404)

    language_filter = request.args.get("language", "").strip().lower()

    # Query base forms with pronunciations
    query = g.db.query(DerivativeForm).filter(
        DerivativeForm.lemma_id == lemma.id,
        DerivativeForm.is_base_form == True,
    )

    if language_filter:
        query = query.filter(DerivativeForm.language_code == language_filter)

    base_forms = query.all()

    # Build pronunciations dictionary (only include if at least one pronunciation exists)
    pronunciations: Dict[str, Dict[str, Any]] = {}
    languages_present: set = set()

    for form in base_forms:
        ipa = form.ipa_pronunciation
        phonetic = form.phonetic_pronunciation

        # Only include if at least one pronunciation is populated
        if ipa or phonetic:
            languages_present.add(form.language_code)
            pronunciations[form.language_code] = {
                "ipa": _serialize_value(ipa),
                "phonetic": _serialize_value(phonetic),
            }

    metadata: Dict[str, Any] = {
        "guid": guid,
        "languages_with_pronunciations": sorted(list(languages_present)),
    }

    if language_filter:
        metadata["requested_language"] = language_filter
        metadata["is_populated"] = language_filter in pronunciations

    return _build_success_response(pronunciations, metadata)


@bp.route("/v1/lemma/<guid>/sentences")
def get_lemma_sentences(guid: str) -> ResponseReturnValue:
    """
    Get example sentences that use this lemma.

    Query parameters:
        - language: Optional. Filter sentence translations to a specific language code

    Returns a list of sentences, each containing:
        - sentence_id: The sentence's database ID
        - translations: Dictionary mapping language codes to sentence text
        - minimum_level: Minimum difficulty level needed to understand this sentence
        - pattern_type: Sentence pattern type (if populated)
        - tense: Sentence tense (if populated)
        - verified: Whether this sentence has been verified
        - word_info: Information about how this lemma is used in the sentence (role, grammatical form, etc.)

    Example:
        GET /api/v1/lemma/V01_001/sentences
        GET /api/v1/lemma/V01_001/sentences?language=lt
    """
    lemma = get_lemma_by_guid(g.db, guid)

    if not lemma:
        return _build_error_response(f"Lemma with GUID '{guid}' not found", 404)

    language_filter = request.args.get("language", "").strip().lower()

    # Find all sentences that use this lemma
    sentence_words = (
        g.db.query(SentenceWord)
        .filter(SentenceWord.lemma_id == lemma.id)
        .order_by(SentenceWord.sentence_id)
        .all()
    )

    # Collect unique sentence IDs
    sentence_ids = list(set(sw.sentence_id for sw in sentence_words))

    if not sentence_ids:
        return _build_success_response([], {"guid": guid, "count": 0})

    # Fetch sentences
    sentences = g.db.query(Sentence).filter(Sentence.id.in_(sentence_ids)).all()

    # Build response
    sentences_data = []

    for sentence in sentences:
        # Get translations for this sentence
        translations_query = g.db.query(SentenceTranslation).filter(
            SentenceTranslation.sentence_id == sentence.id
        )

        if language_filter:
            translations_query = translations_query.filter(
                SentenceTranslation.language_code == language_filter
            )

        translations = {t.language_code: t.translation_text for t in translations_query.all()}

        # Skip this sentence if language filter is set and no translation exists
        if language_filter and not translations:
            continue

        # Find how this lemma is used in the sentence
        word_info_list = [sw for sw in sentence_words if sw.sentence_id == sentence.id]

        word_info = []
        for sw in word_info_list:
            word_info.append(
                {
                    "position": sw.position,
                    "word_role": sw.word_role,
                    "english_text": _serialize_value(sw.english_text),
                    "target_language_text": _serialize_value(sw.target_language_text),
                    "grammatical_form": _serialize_value(sw.grammatical_form),
                    "declined_form": _serialize_value(sw.declined_form),
                    "language_code": sw.language_code,
                }
            )

        sentences_data.append(
            {
                "sentence_id": sentence.id,
                "translations": translations,
                "minimum_level": _serialize_value(sentence.minimum_level),
                "pattern_type": _serialize_value(sentence.pattern_type),
                "tense": _serialize_value(sentence.tense),
                "verified": sentence.verified,
                "word_info": word_info,
            }
        )

    metadata = {
        "guid": guid,
        "count": len(sentences_data),
    }

    if language_filter:
        metadata["requested_language"] = language_filter

    return _build_success_response(sentences_data, metadata)
