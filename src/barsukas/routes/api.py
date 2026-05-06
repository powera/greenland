#!/usr/bin/python3

"""API routes for AJAX requests and REST API endpoints.

MIRRORED: routes annotated with ``@mirrored_facade`` have a typed Python
wrapper in the root-level ``api/`` package (``api/lemmas.py``,
``api/sentences.py``, ``api/batch_operations.py``, ...). Edits to a mirrored
route's path, query params, or response shape MUST be made in the matching
facade in the same commit. See ``api/AGENTS.md`` for the mirroring contract.
"""

from typing import Any, Dict, List, Optional, Tuple, Union

from barsukas.config import Config
from barsukas.routes._mirror import mirrored_facade
from flask import Blueprint, Response, g, jsonify, request
from flask.typing import ResponseReturnValue
from sqlalchemy import and_, case, func, or_

from storage.crud.grammar_fact import get_grammar_facts
from storage.crud.lemma import get_lemma_by_guid
from storage.models import (
    DerivativeForm,
    GrammarFact,
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from storage.models.schema import AudioQualityReview, LemmaDifficultyOverride
from storage.queries.lemma import build_lemma_search_query
from storage.translation_helpers import (
    LANGUAGE_HIERARCHY,
    get_all_translations,
    get_translation_pronunciations,
)

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

        client = LinguisticClient(model="gpt-5.4-mini", db_path=Config.DB_PATH, debug=Config.DEBUG)

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
            prompt=prompt, model="gpt-5.4-mini", json_schema=schema, timeout=30
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
                    "description": "Filter by difficulty level (1-30, '-1' for excluded, 'null' for not set)",
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
            "path": "/api/v1/models",
            "method": "GET",
            "description": "List LLM models registered in the benchmarks database (requires postgres)",
            "parameters": [
                {
                    "name": "q",
                    "type": "query",
                    "required": False,
                    "description": "Case-insensitive substring search across codename, displayname, model_path, lmstudio_model_name",
                }
            ],
        },
        {
            "path": "/api/v1/metadata/words",
            "method": "GET",
            "description": "Get per-language lemma counts and metadata coverage (audio, derivative forms, subtypes)",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to a specific language code (e.g., 'en', 'zh', 'lt')",
                }
            ],
        },
        {
            "path": "/api/v1/metadata/sentences",
            "method": "GET",
            "description": "Get per-language sentence counts and metadata coverage (audio, verification, pattern types)",
            "parameters": [
                {
                    "name": "language",
                    "type": "query",
                    "required": False,
                    "description": "Filter to a specific language code (e.g., 'en', 'zh', 'lt')",
                }
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
            "path": "/api/v1/lemma/<guid>/audio",
            "method": "GET",
            "description": "Get lemma-level and form-level audio availability by language",
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
@mirrored_facade("/api/v1/search", "GET")
def search_lemmas() -> ResponseReturnValue:
    """
    Search for lemmas by keyword across multiple fields.

    Query parameters:
        - q: Required. Search query to find in lemma text, definition, disambiguation, and translations
        - pos_type: Optional. Filter by part of speech (e.g., 'noun', 'verb')
        - difficulty: Optional. Filter by difficulty level (1-30, '-1' for excluded, 'null' for not set)
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
@mirrored_facade("/api/v1/lemma/<guid>", "GET")
def get_lemma_info(guid: str) -> ResponseReturnValue:
    """
    Get basic information about a lemma by GUID.

    Returns:
        - guid: The lemma's unique identifier
        - lemma_text: The lemma's base form (in English)
        - definition: The English definition
        - pos_type: Part of speech type (noun, verb, etc.)
        - pos_subtype: Part of speech subtype (if populated)
        - difficulty_level: Difficulty level (1-30, or -1 for excluded, or null if not set)
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


@bp.route("/v1/lemma/<guid>", methods=["POST", "PATCH"])
@mirrored_facade("/api/v1/lemma/<guid>", "POST")
@mirrored_facade("/api/v1/lemma/<guid>", "PATCH")
def update_lemma_info(guid: str) -> ResponseReturnValue:
    """Update mutable lemma fields.

    Supports:
      - ``difficulty_level``: integer in configured range, ``-1`` to exclude,
        or ``null`` to unset.
    """
    lemma = get_lemma_by_guid(g.db, guid)
    if not lemma:
        return _build_error_response(f"Lemma with GUID '{guid}' not found", 404)

    payload = request.get_json(silent=True) or {}
    if "difficulty_level" not in payload:
        return _build_error_response("JSON body must include 'difficulty_level'", 400)

    difficulty_value = payload["difficulty_level"]
    if difficulty_value is None:
        new_difficulty_level: Optional[int] = None
    else:
        try:
            new_difficulty_level = int(difficulty_value)
        except (TypeError, ValueError):
            return _build_error_response("difficulty_level must be an integer or null", 400)

        if new_difficulty_level != Config.EXCLUDE_DIFFICULTY_LEVEL and (
            new_difficulty_level < Config.MIN_DIFFICULTY_LEVEL
            or new_difficulty_level > Config.MAX_DIFFICULTY_LEVEL
        ):
            return _build_error_response(
                f"difficulty_level must be between {Config.MIN_DIFFICULTY_LEVEL} and "
                f"{Config.MAX_DIFFICULTY_LEVEL}, or {Config.EXCLUDE_DIFFICULTY_LEVEL}",
                400,
            )

    old_difficulty_level = lemma.difficulty_level
    lemma.difficulty_level = new_difficulty_level
    g.db.commit()

    return _build_success_response(
        {
            "guid": lemma.guid,
            "difficulty_level": _serialize_value(lemma.difficulty_level),
            "previous_difficulty_level": _serialize_value(old_difficulty_level),
            "updated": old_difficulty_level != lemma.difficulty_level,
        }
    )


@bp.route("/v1/lemma/<guid>/translations")
@mirrored_facade("/api/v1/lemma/<guid>/translations", "GET")
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
@mirrored_facade("/api/v1/lemma/<guid>/forms", "GET")
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
@mirrored_facade("/api/v1/lemma/<guid>/grammar", "GET")
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
@mirrored_facade("/api/v1/lemma/<guid>/pronunciations", "GET")
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

    # Build pronunciations dictionary (only include if at least one pronunciation exists)
    pronunciations: Dict[str, Dict[str, Any]] = {}
    languages_present: set = set()
    language_codes = [language_filter] if language_filter else sorted(LANGUAGE_HIERARCHY)

    for language_code in language_codes:
        translation_ipa, translation_phonetic = get_translation_pronunciations(
            g.db, lemma, language_code
        )

        base_form = (
            g.db.query(DerivativeForm)
            .filter(
                DerivativeForm.lemma_id == lemma.id,
                DerivativeForm.language_code == language_code,
                DerivativeForm.is_base_form == True,
            )
            .first()
        )

        ipa_value = translation_ipa or (base_form.ipa_pronunciation if base_form else None)
        phonetic_value = translation_phonetic or (
            base_form.phonetic_pronunciation if base_form else None
        )

        if ipa_value or phonetic_value:
            languages_present.add(language_code)
            pronunciations[language_code] = {
                "ipa": _serialize_value(ipa_value),
                "phonetic": _serialize_value(phonetic_value),
            }

    metadata: Dict[str, Any] = {
        "guid": guid,
        "languages_with_pronunciations": sorted(list(languages_present)),
    }

    if language_filter:
        metadata["requested_language"] = language_filter
        metadata["is_populated"] = language_filter in pronunciations

    return _build_success_response(pronunciations, metadata)


@bp.route("/v1/lemma/<guid>/audio")
@mirrored_facade("/api/v1/lemma/<guid>/audio", "GET")
def get_lemma_audio(guid: str) -> ResponseReturnValue:
    """
    Get audio availability for a lemma by language.

    Query parameters:
        - language: Optional. Filter to a specific language code (e.g., 'en', 'lt', 'fr')

    Returns a dictionary mapping language codes to:
        - has_lemma_audio: Whether lemma-level audio exists for this language
        - form_audio_count: Number of distinct grammatical forms with form-level audio
        - audio_files: Audio file pointers (md5 + URL metadata)

    Only languages with at least one audio row (lemma-level or form-level) are included.

    Example:
        GET /api/v1/lemma/N01_001/audio
        GET /api/v1/lemma/N01_001/audio?language=lt
    """
    lemma = get_lemma_by_guid(g.db, guid)

    if not lemma:
        return _build_error_response(f"Lemma with GUID '{guid}' not found", 404)

    language_filter = request.args.get("language", "").strip().lower()

    has_lemma_audio_expr = func.max(
        case(
            (AudioQualityReview.grammatical_form.is_(None), 1),
            else_=0,
        )
    ).label("has_lemma_audio")
    form_audio_count_expr = func.count(
        func.distinct(
            case(
                (
                    AudioQualityReview.grammatical_form.is_not(None),
                    AudioQualityReview.grammatical_form,
                ),
                else_=None,
            )
        )
    ).label("form_audio_count")

    audio_query = (
        g.db.query(
            AudioQualityReview.language_code.label("language_code"),
            has_lemma_audio_expr,
            form_audio_count_expr,
        )
        .filter(
            AudioQualityReview.guid == lemma.guid,
            AudioQualityReview.sentence_id.is_(None),
        )
        .group_by(AudioQualityReview.language_code)
    )

    if language_filter:
        audio_query = audio_query.filter(AudioQualityReview.language_code == language_filter)

    audio_rows = audio_query.all()

    details_query = g.db.query(AudioQualityReview).filter(
        AudioQualityReview.guid == lemma.guid,
        AudioQualityReview.sentence_id.is_(None),
    )
    if language_filter:
        details_query = details_query.filter(AudioQualityReview.language_code == language_filter)
    detail_rows = details_query.order_by(
        AudioQualityReview.language_code,
        AudioQualityReview.grammatical_form,
        AudioQualityReview.voice_name,
    ).all()

    language_audio: Dict[str, Dict[str, Any]] = {}
    for row in audio_rows:
        language_audio[row.language_code] = {
            "has_lemma_audio": bool(row.has_lemma_audio),
            "form_audio_count": int(row.form_audio_count or 0),
        }

    files_by_language: Dict[str, List[Dict[str, Any]]] = {}
    for detail_row in detail_rows:
        detail_language = detail_row.language_code
        if detail_language not in files_by_language:
            files_by_language[detail_language] = []

        files_by_language[detail_language].append(
            {
                "grammatical_form": _serialize_value(detail_row.grammatical_form),
                "voice_name": detail_row.voice_name,
                "display_voice": detail_row.display_voice,
                "manifest_md5": detail_row.manifest_md5,
                "audio_url": _serialize_value(detail_row.s3_prod_url or detail_row.s3_staging_url),
                "s3_prod_url": _serialize_value(detail_row.s3_prod_url),
                "s3_staging_url": _serialize_value(detail_row.s3_staging_url),
                "status": detail_row.status,
            }
        )

    if language_filter:
        language_codes = [language_filter]
    else:
        hierarchy_languages = [lang for lang in LANGUAGE_HIERARCHY if lang in language_audio]
        extra_languages = sorted(
            [lang for lang in language_audio if lang not in LANGUAGE_HIERARCHY]
        )
        language_codes = hierarchy_languages + extra_languages

    audio_data: Dict[str, Dict[str, Any]] = {}
    languages_with_lemma_audio: List[str] = []
    languages_with_any_audio: List[str] = []

    for language_code in language_codes:
        current_audio = language_audio.get(language_code)
        if not current_audio:
            continue

        has_lemma_audio = current_audio["has_lemma_audio"]
        form_audio_count = current_audio["form_audio_count"]

        if has_lemma_audio or form_audio_count > 0:
            audio_data[language_code] = {
                "has_lemma_audio": has_lemma_audio,
                "form_audio_count": form_audio_count,
                "audio_files": files_by_language.get(language_code, []),
            }
            languages_with_any_audio.append(language_code)
            if has_lemma_audio:
                languages_with_lemma_audio.append(language_code)

    metadata: Dict[str, Any] = {
        "guid": guid,
        "languages_with_lemma_audio": languages_with_lemma_audio,
        "languages_with_any_audio": languages_with_any_audio,
    }

    if language_filter:
        metadata["requested_language"] = language_filter
        metadata["is_populated"] = language_filter in audio_data

    return _build_success_response(audio_data, metadata)


@bp.route("/v1/lemma/<guid>/sentences")
@mirrored_facade("/api/v1/lemma/<guid>/sentences", "GET")
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


def _has_translation_expression(language_code: str) -> Any:
    """Build a SQL expression that indicates whether a lemma is available in the language."""
    if language_code == "en":
        return Lemma.lemma_text.isnot(None)

    return and_(
        LemmaTranslation.language_code == language_code,
        LemmaTranslation.translation.isnot(None),
        LemmaTranslation.translation != "",
    )


@bp.route("/v1/metadata/words")
@mirrored_facade("/api/v1/metadata/words", "GET")
def get_word_metadata() -> ResponseReturnValue:
    """Get per-language metadata counts for lemma coverage, audio, and derivative forms.

    Optional query params:
      language=<code>       Filter to a single language.
      max_difficulty=<int>  Only count words whose effective difficulty (COALESCE of
                            per-language override and base lemma difficulty) is between
                            1 and max_difficulty inclusive (excludes -1 / unset).
      difficulty=<int>      Only count words whose effective difficulty exactly equals this
                            value.
    """
    requested_language = request.args.get("language", "").strip().lower()
    max_difficulty_param = request.args.get("max_difficulty", "").strip()
    difficulty_param = request.args.get("difficulty", "").strip()
    max_difficulty: Optional[int] = None
    exact_difficulty: Optional[int] = None
    if max_difficulty_param:
        try:
            max_difficulty = int(max_difficulty_param)
        except ValueError:
            return _build_error_response("max_difficulty must be an integer", 400)
    if difficulty_param:
        try:
            exact_difficulty = int(difficulty_param)
        except ValueError:
            return _build_error_response("difficulty must be an integer", 400)

    translation_languages = {
        row[0]
        for row in g.db.query(LemmaTranslation.language_code)
        .filter(LemmaTranslation.translation.isnot(None), LemmaTranslation.translation != "")
        .distinct()
        .all()
    }
    derivative_languages = {
        row[0] for row in g.db.query(DerivativeForm.language_code).distinct().all()
    }
    audio_languages = {
        row[0]
        for row in g.db.query(AudioQualityReview.language_code)
        .filter(
            AudioQualityReview.guid.isnot(None),
            AudioQualityReview.sentence_id.is_(None),
            AudioQualityReview.grammatical_form.is_(None),
        )
        .distinct()
        .all()
    }

    available_languages = (
        set(LANGUAGE_HIERARCHY) | translation_languages | derivative_languages | audio_languages
    )

    if requested_language and requested_language not in available_languages:
        return _build_error_response(
            f"Language '{requested_language}' not found in metadata sources",
            404,
        )

    ordered_languages = [lang for lang in LANGUAGE_HIERARCHY if lang in available_languages]
    extra_languages = sorted(lang for lang in available_languages if lang not in LANGUAGE_HIERARCHY)
    all_languages = ordered_languages + extra_languages

    selected_languages = [requested_language] if requested_language else all_languages

    summary_data: Dict[str, Any] = {}

    for current_language in selected_languages:
        if current_language == "en":
            base_query = g.db.query(Lemma.id, Lemma.pos_subtype).filter(
                Lemma.lemma_text.isnot(None)
            )
        else:
            base_query = (
                g.db.query(Lemma.id, Lemma.pos_subtype)
                .join(LemmaTranslation, LemmaTranslation.lemma_id == Lemma.id)
                .filter(_has_translation_expression(current_language))
                .distinct()
            )

        if max_difficulty is not None:
            # COALESCE(override.difficulty_level, lemma.difficulty_level) BETWEEN 1 AND max_difficulty
            # We must join Lemma back (it is already the root of the query) and left-join overrides.
            effective_difficulty = case(
                (
                    LemmaDifficultyOverride.difficulty_level.isnot(None),
                    LemmaDifficultyOverride.difficulty_level,
                ),
                else_=Lemma.difficulty_level,
            )
            base_query = base_query.outerjoin(
                LemmaDifficultyOverride,
                (LemmaDifficultyOverride.lemma_id == Lemma.id)
                & (LemmaDifficultyOverride.language_code == current_language),
            ).filter(
                effective_difficulty >= 1,
                effective_difficulty <= max_difficulty,
            )
        elif exact_difficulty is not None:
            effective_difficulty = case(
                (
                    LemmaDifficultyOverride.difficulty_level.isnot(None),
                    LemmaDifficultyOverride.difficulty_level,
                ),
                else_=Lemma.difficulty_level,
            )
            base_query = base_query.outerjoin(
                LemmaDifficultyOverride,
                (LemmaDifficultyOverride.lemma_id == Lemma.id)
                & (LemmaDifficultyOverride.language_code == current_language),
            ).filter(effective_difficulty == exact_difficulty)

        base_subquery = base_query.subquery()

        total_words = g.db.query(func.count()).select_from(base_subquery).scalar() or 0

        subtype_rows = (
            g.db.query(
                case(
                    (base_subquery.c.pos_subtype.is_(None), "unspecified"),
                    else_=base_subquery.c.pos_subtype,
                ).label("subtype"),
                func.count().label("count"),
            )
            .group_by("subtype")
            .order_by("subtype")
            .all()
        )
        words_by_subtype = {row.subtype: row.count for row in subtype_rows}

        derivative_count = (
            g.db.query(func.count(func.distinct(base_subquery.c.id)))
            .select_from(base_subquery)
            .join(
                DerivativeForm,
                and_(
                    DerivativeForm.lemma_id == base_subquery.c.id,
                    DerivativeForm.language_code == current_language,
                ),
            )
            .scalar()
            or 0
        )

        audio_count = (
            g.db.query(func.count(func.distinct(base_subquery.c.id)))
            .select_from(base_subquery)
            .join(Lemma, Lemma.id == base_subquery.c.id)
            .join(
                AudioQualityReview,
                and_(
                    AudioQualityReview.guid == Lemma.guid,
                    AudioQualityReview.language_code == current_language,
                    AudioQualityReview.sentence_id.is_(None),
                    AudioQualityReview.grammatical_form.is_(None),
                ),
            )
            .scalar()
            or 0
        )

        words_without_audio = total_words - audio_count
        words_without_derivatives = total_words - derivative_count

        summary_data[current_language] = {
            "total_words": total_words,
            "words_by_subtype": words_by_subtype,
            "audio": {
                "with_audio": audio_count,
                "without_audio": words_without_audio,
            },
            "derivative_forms": {
                "with_derivative_forms": derivative_count,
                "without_derivative_forms": words_without_derivatives,
            },
        }

    metadata: Dict[str, Any] = {
        "languages": selected_languages,
        "count": len(selected_languages),
        "notes": {
            "word_definition": "A lemma with populated text in that language (lemma_text for 'en', non-empty lemma_translations.translation otherwise)",
            "audio_definition": "A lemma-level audio_quality_reviews row (guid set, sentence_id null, grammatical_form null)",
            "derivative_definition": "At least one derivative_forms row for the lemma in that language",
        },
    }

    if requested_language:
        metadata["requested_language"] = requested_language
    if max_difficulty is not None:
        metadata["max_difficulty"] = max_difficulty
    if exact_difficulty is not None:
        metadata["difficulty"] = exact_difficulty

    return _build_success_response(summary_data, metadata)


@bp.route("/v1/metadata/sentences")
@mirrored_facade("/api/v1/metadata/sentences", "GET")
def get_sentence_metadata() -> ResponseReturnValue:
    """Get per-language metadata counts for sentence coverage and sentence-level audio.

    Optional query params:
      language=<code>       Filter to a single language.
      max_difficulty=<int>  Only count sentences whose minimum_level is between
                            1 and max_difficulty inclusive (excludes NULL / unset).
    """
    requested_language = request.args.get("language", "").strip().lower()
    max_difficulty_param = request.args.get("max_difficulty", "").strip()
    max_difficulty_sentences: Optional[int] = None
    if max_difficulty_param:
        try:
            max_difficulty_sentences = int(max_difficulty_param)
        except ValueError:
            return _build_error_response("max_difficulty must be an integer", 400)

    sentence_translation_languages = {
        row[0]
        for row in g.db.query(SentenceTranslation.language_code)
        .filter(
            SentenceTranslation.translation_text.isnot(None),
            SentenceTranslation.translation_text != "",
        )
        .distinct()
        .all()
    }
    sentence_audio_languages = {
        row[0]
        for row in g.db.query(AudioQualityReview.language_code)
        .filter(AudioQualityReview.sentence_id.isnot(None))
        .distinct()
        .all()
    }

    available_languages = (
        set(LANGUAGE_HIERARCHY) | sentence_translation_languages | sentence_audio_languages
    )

    if requested_language and requested_language not in available_languages:
        return _build_error_response(
            f"Language '{requested_language}' not found in metadata sources",
            404,
        )

    ordered_languages = [lang for lang in LANGUAGE_HIERARCHY if lang in available_languages]
    extra_languages = sorted(lang for lang in available_languages if lang not in LANGUAGE_HIERARCHY)
    all_languages = ordered_languages + extra_languages

    selected_languages = [requested_language] if requested_language else all_languages

    summary_data: Dict[str, Any] = {}

    for current_language in selected_languages:
        sentence_filters = [
            SentenceTranslation.language_code == current_language,
            SentenceTranslation.translation_text.isnot(None),
            SentenceTranslation.translation_text != "",
        ]
        if max_difficulty_sentences is not None:
            sentence_filters.extend(
                [
                    Sentence.minimum_level.isnot(None),
                    Sentence.minimum_level >= 1,
                    Sentence.minimum_level <= max_difficulty_sentences,
                ]
            )
        base_query = (
            g.db.query(Sentence.id, Sentence.pattern_type, Sentence.verified)
            .join(SentenceTranslation, SentenceTranslation.sentence_id == Sentence.id)
            .filter(*sentence_filters)
            .distinct()
        )

        base_subquery = base_query.subquery()

        total_sentences = g.db.query(func.count()).select_from(base_subquery).scalar() or 0

        pattern_rows = (
            g.db.query(
                case(
                    (base_subquery.c.pattern_type.is_(None), "unspecified"),
                    else_=base_subquery.c.pattern_type,
                ).label("pattern_type"),
                func.count().label("count"),
            )
            .group_by("pattern_type")
            .order_by("pattern_type")
            .all()
        )
        sentences_by_pattern = {row.pattern_type: row.count for row in pattern_rows}

        audio_count = (
            g.db.query(func.count(func.distinct(base_subquery.c.id)))
            .select_from(base_subquery)
            .join(
                AudioQualityReview,
                and_(
                    AudioQualityReview.sentence_id == base_subquery.c.id,
                    AudioQualityReview.language_code == current_language,
                ),
            )
            .scalar()
            or 0
        )

        verified_count = (
            g.db.query(func.count())
            .select_from(base_subquery)
            .filter(base_subquery.c.verified.is_(True))
            .scalar()
            or 0
        )

        summary_data[current_language] = {
            "total_sentences": total_sentences,
            "sentences_by_pattern": sentences_by_pattern,
            "audio": {
                "with_audio": audio_count,
                "without_audio": total_sentences - audio_count,
            },
            "verification": {
                "verified": verified_count,
                "unverified": total_sentences - verified_count,
            },
        }

    metadata: Dict[str, Any] = {
        "languages": selected_languages,
        "count": len(selected_languages),
        "notes": {
            "sentence_definition": "A sentence with non-empty sentence_translations.translation_text in that language",
            "audio_definition": "At least one sentence-level audio_quality_reviews row for the sentence and language (sentence_id set)",
            "verification_definition": "Sentence.verified value among sentences counted in that language",
        },
    }

    if requested_language:
        metadata["requested_language"] = requested_language
    if max_difficulty_sentences is not None:
        metadata["max_difficulty"] = max_difficulty_sentences

    return _build_success_response(summary_data, metadata)


@bp.route("/v1/models")
@mirrored_facade("/api/v1/models", "GET")
def list_models() -> ResponseReturnValue:
    """Search LLM models registered in the benchmarks database.

    Query parameters:
        - q: Optional. Case-insensitive substring search across codename, displayname,
             model_path, and lmstudio_model_name fields.
    """
    bench_db = g.get("bench_db")
    if bench_db is None:
        return _build_error_response(
            "Model registry not available (benchmarks database not configured)", 503
        )

    from benchmarks.datastore.common import Model

    query = bench_db.query(Model).order_by(Model.codename)

    search_term = request.args.get("q", "").strip()
    if search_term:
        pattern = f"%{search_term}%"
        query = query.filter(
            or_(
                Model.codename.ilike(pattern),
                Model.displayname.ilike(pattern),
                Model.model_path.ilike(pattern),
                Model.lmstudio_model_name.ilike(pattern),
            )
        )

    models = query.all()

    models_data = [
        {
            "codename": m.codename,
            "displayname": m.displayname,
            "model_path": m.model_path,
            "model_type": m.model_type,
            "lmstudio_model_name": m.lmstudio_model_name,
            "launch_date": str(m.launch_date) if m.launch_date else None,
            "license_name": m.license_name,
        }
        for m in models
    ]

    return _build_success_response(
        models_data,
        {"count": len(models_data), "search": search_term or None},
    )
