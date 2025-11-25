#!/usr/bin/python3

"""API routes for AJAX requests."""

from flask import Blueprint, jsonify, request, g
from sqlalchemy import or_, func

from wordfreq.storage.models.schema import Lemma
from config import Config

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/check_lemma_exists")
def check_lemma_exists():
    """Check if a lemma exists or find similar lemmas."""
    search = request.args.get("search", "").strip()
    pos_type = request.args.get("pos_type", "").strip()

    if not search:
        return jsonify({
            "exact_match": None,
            "similar_matches": []
        })

    # Check for exact match
    exact_query = g.db.query(Lemma).filter(
        func.lower(Lemma.lemma_text) == search.lower()
    )
    if pos_type:
        exact_query = exact_query.filter(Lemma.pos_type == pos_type)

    exact_match = exact_query.first()

    # Find similar matches (case-insensitive LIKE search)
    similar_query = g.db.query(Lemma).filter(
        Lemma.lemma_text.ilike(f'%{search}%')
    )

    # If exact match found, exclude it from similar matches
    if exact_match:
        similar_query = similar_query.filter(Lemma.id != exact_match.id)

    similar_matches = similar_query.limit(5).all()

    return jsonify({
        "exact_match": {
            "id": exact_match.id,
            "lemma_text": exact_match.lemma_text,
            "pos_type": exact_match.pos_type,
            "definition_text": exact_match.definition_text
        } if exact_match else None,
        "similar_matches": [
            {
                "id": lemma.id,
                "lemma_text": lemma.lemma_text,
                "pos_type": lemma.pos_type,
                "definition_text": lemma.definition_text
            }
            for lemma in similar_matches
        ]
    })


@bp.route("/auto_populate_lemma")
def auto_populate_lemma():
    """Auto-populate lemma fields using LLM based on word and optional translation."""
    word = request.args.get("word", "").strip()
    translation = request.args.get("translation", "").strip()
    lang_code = request.args.get("lang_code", "").strip()

    if not word:
        return jsonify({
            "success": False,
            "error": "Word is required"
        })

    try:
        # Use LLM to generate definition, POS type, and POS subtype
        from wordfreq.translation.client import LinguisticClient

        client = LinguisticClient(
            model="gpt-5-mini",
            db_path=Config.DB_PATH,
            debug=Config.DEBUG
        )

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
   - For nouns: animal, body_part, building_structure, clothing_accessory, concept_idea, emotion_feeling, food_drink, human, material_substance, nationality, natural_feature, personal_name, place_name, plant, small_movable_object, temporal_name, time_period, tool_machine, unit_of_measurement
   - For verbs: directional_movement, emotional_state, mental_state, physical_action, possession
   - For adjectives: color, definite_quantity, quality, sequence, shape
   - For adverbs: location, other, style
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
                    description="Clear, concise definition of the word (1-2 sentences)"
                ),
                "pos_type": SchemaProperty(
                    type="string",
                    description="Part of speech type"
                ),
                "pos_subtype": SchemaProperty(
                    type="string",
                    description="Part of speech subtype"
                )
            }
        )

        response = client.client.generate_chat(
            prompt=prompt,
            model="gpt-5-mini",
            json_schema=schema,
            timeout=30
        )

        if not response.structured_data:
            return jsonify({
                "success": False,
                "error": "Failed to get structured response from LLM"
            })

        result = response.structured_data

        # Get the maximum difficulty level for this pos_subtype
        max_level = None
        if result.get("pos_subtype"):
            max_level_query = g.db.query(func.max(Lemma.difficulty_level)).filter(
                Lemma.pos_subtype == result["pos_subtype"],
                Lemma.difficulty_level.isnot(None),
                Lemma.difficulty_level != -1  # Exclude "excluded" words
            ).scalar()
            if max_level_query:
                max_level = int(max_level_query)

        return jsonify({
            "success": True,
            "definition": result.get("definition", ""),
            "pos_type": result.get("pos_type", ""),
            "pos_subtype": result.get("pos_subtype", ""),
            "suggested_difficulty_level": max_level
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })
