#!/usr/bin/python3

"""
Sentence Rapid Review Routes

Provides streamlined keyboard-driven sentence review interface for verifying
translations (ES, FR, ZH, LT) before final approval.
"""

from typing import Any, Dict, List, Optional

from flask import (
    Blueprint,
    g,
    jsonify,
    render_template,
    request,
)
from flask.typing import ResponseReturnValue
from sqlalchemy import case
from sqlalchemy.orm import Query

from langtools.zh.pinyin_helper import generate_pinyin
from wordfreq.storage.models.schema import (
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)

bp = Blueprint("sentence_rapid_review", __name__, url_prefix="/sentences/rapid-review")

# The 4 key languages for review (plus English as reference)
REVIEW_LANGUAGES = ["en", "es", "fr", "zh", "lt"]


def get_sentence_translations(sentence_id: int) -> Dict[str, str]:
    """Get all translations for a sentence as a dict keyed by language code."""
    translations = (
        g.db.query(SentenceTranslation).filter(SentenceTranslation.sentence_id == sentence_id).all()
    )
    return {t.language_code: t.translation_text for t in translations}


def has_required_translations(translations: Dict[str, str]) -> bool:
    """Check if sentence has all required translations (ES, FR, ZH, LT)."""
    required = {"es", "fr", "zh", "lt"}
    return required.issubset(translations.keys())


def calculate_sentence_minimum_level(sentence_id: int) -> int:
    """Calculate minimum_level for a sentence based on its word difficulty levels.

    Returns the max difficulty level of all linked lemmas, or -1 if:
    - No words are linked to lemmas
    - Any linked lemma has difficulty_level = -1 or NULL

    Args:
        sentence_id: The sentence ID to calculate level for

    Returns:
        Calculated minimum level, or -1 as fallback
    """
    # Get all words for this sentence that have linked lemmas
    words_with_lemmas = (
        g.db.query(SentenceWord, Lemma)
        .join(Lemma, SentenceWord.lemma_id == Lemma.id)
        .filter(SentenceWord.sentence_id == sentence_id)
        .all()
    )

    if not words_with_lemmas:
        return -1

    max_level = -1
    for word, lemma in words_with_lemmas:
        if lemma.difficulty_level is None or lemma.difficulty_level == -1:
            # Any unset or -1 level means the sentence level should be -1
            return -1
        if lemma.difficulty_level > max_level:
            max_level = lemma.difficulty_level

    return max_level if max_level > 0 else -1


def build_sentence_query(
    status_filter: str = "ready",
    level_filter: str = "",
    pattern_filter: str = "",
) -> Query:
    """Build query for sentences based on filters.

    status_filter options:
    - "ready": Has translations and level, not verified/rejected (default)
    - "verified": Already verified
    - "rejected": Already rejected
    - "all": Show all
    """
    query = g.db.query(Sentence)

    if status_filter == "ready":
        query = query.filter(Sentence.verified == False)
        query = query.filter(Sentence.rejected == False)
        # Note: We don't filter by minimum_level - sentences without it can still be reviewed
    elif status_filter == "verified":
        query = query.filter(Sentence.verified == True)
    elif status_filter == "rejected":
        query = query.filter(Sentence.rejected == True)
    # "all" has no status filter

    if level_filter:
        try:
            level_int = int(level_filter)
            query = query.filter(Sentence.minimum_level == level_int)
        except ValueError:
            pass

    if pattern_filter:
        query = query.filter(Sentence.pattern_type == pattern_filter)

    # Order by level, then ID
    level_order = case((Sentence.minimum_level.is_(None), 99), else_=Sentence.minimum_level)
    query = query.order_by(level_order, Sentence.id)

    return query


def find_sentences_with_translations(query: Query, limit: int = 100) -> List[Dict[str, Any]]:
    """Find sentences that have all required translations.

    Returns list of sentence data dicts with translations included.
    """
    # Get candidate sentences
    candidates = query.limit(limit * 2).all()  # Fetch extra to filter

    # Batch load translations for all candidates
    if not candidates:
        return []

    sentence_ids = [s.id for s in candidates]
    all_translations = (
        g.db.query(SentenceTranslation)
        .filter(SentenceTranslation.sentence_id.in_(sentence_ids))
        .all()
    )

    # Group translations by sentence
    translations_by_sentence: Dict[int, Dict[str, str]] = {}
    for t in all_translations:
        if t.sentence_id not in translations_by_sentence:
            translations_by_sentence[t.sentence_id] = {}
        translations_by_sentence[t.sentence_id][t.language_code] = t.translation_text

    # Filter to sentences with all required translations
    result = []
    for sentence in candidates:
        translations = translations_by_sentence.get(sentence.id, {})
        if has_required_translations(translations):
            result.append(
                {
                    "sentence": sentence,
                    "translations": translations,
                }
            )
            if len(result) >= limit:
                break

    return result


@bp.route("/")
def index() -> ResponseReturnValue:
    """Streamlined rapid review interface for sentences with keyboard shortcuts."""
    # Get filter parameters
    status_filter = request.args.get("status", "ready")
    level_filter = request.args.get("level", "")
    pattern_filter = request.args.get("pattern", "")

    # Build query
    query = build_sentence_query(status_filter, level_filter, pattern_filter)

    # Find sentences with all required translations
    sentences_with_translations = find_sentences_with_translations(query, limit=1)

    # Get total count (approximate - includes sentences without all translations)
    total_count = query.count()

    # Get first sentence to review
    current_sentence = None
    current_translations = {}
    if sentences_with_translations:
        current_sentence = sentences_with_translations[0]["sentence"]
        current_translations = sentences_with_translations[0]["translations"]

    # Get filter options
    statuses = ["ready", "verified", "rejected", "all"]

    levels = (
        g.db.query(Sentence.minimum_level)
        .filter(Sentence.minimum_level.isnot(None))
        .distinct()
        .order_by(Sentence.minimum_level)
        .all()
    )
    levels = [l[0] for l in levels]

    patterns = (
        g.db.query(Sentence.pattern_type)
        .filter(Sentence.pattern_type.isnot(None))
        .distinct()
        .order_by(Sentence.pattern_type)
        .all()
    )
    patterns = [p[0] for p in patterns]

    # Generate pinyin for Chinese
    pinyin_text = None
    if current_translations.get("zh"):
        pinyin_text = generate_pinyin(current_translations["zh"])

    return render_template(
        "sentences/rapid_review.html",
        sentence=current_sentence,
        translations=current_translations,
        pinyin_text=pinyin_text,
        total_count=total_count,
        statuses=statuses,
        levels=levels,
        patterns=patterns,
        status_filter=status_filter,
        level_filter=level_filter,
        pattern_filter=pattern_filter,
    )


def get_next_sentence(
    current_id: int,
    status_filter: str,
    level_filter: str,
    pattern_filter: str,
) -> Optional[Dict[str, Any]]:
    """Get the next sentence after current_id matching filters."""
    query = build_sentence_query(status_filter, level_filter, pattern_filter)
    query = query.filter(Sentence.id > current_id)

    sentences_with_translations = find_sentences_with_translations(query, limit=1)

    if not sentences_with_translations:
        return None

    sentence = sentences_with_translations[0]["sentence"]
    translations = sentences_with_translations[0]["translations"]

    # Generate pinyin for Chinese
    pinyin_text = None
    if translations.get("zh"):
        pinyin_text = generate_pinyin(translations["zh"])

    return {
        "id": sentence.id,
        "pattern_type": sentence.pattern_type,
        "tense": sentence.tense,
        "minimum_level": sentence.minimum_level,
        "translations": translations,
        "pinyin": pinyin_text,
    }


@bp.route("/verify/<int:sentence_id>", methods=["POST"])
def verify(sentence_id: int) -> ResponseReturnValue:
    """Verify sentence and get next (AJAX endpoint)."""
    sentence = g.db.query(Sentence).filter_by(id=sentence_id).first()

    if not sentence:
        return jsonify({"error": "Sentence not found"}), 404

    data = request.get_json()
    status_filter = data.get("status_filter", "ready")
    level_filter = data.get("level", "")
    pattern_filter = data.get("pattern", "")

    try:
        # Calculate and set minimum_level based on word difficulty levels
        sentence.minimum_level = calculate_sentence_minimum_level(sentence_id)

        # Mark as verified
        sentence.verified = True
        g.db.commit()

        # Get next sentence
        next_sentence = get_next_sentence(sentence_id, status_filter, level_filter, pattern_filter)

        if next_sentence:
            return jsonify(
                {
                    "success": True,
                    "has_next": True,
                    "next_sentence": next_sentence,
                }
            )
        else:
            return jsonify(
                {"success": True, "has_next": False, "message": "No more sentences to review"}
            )

    except Exception as e:
        g.db.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/reject/<int:sentence_id>", methods=["POST"])
def reject(sentence_id: int) -> ResponseReturnValue:
    """Reject sentence and get next (AJAX endpoint)."""
    sentence = g.db.query(Sentence).filter_by(id=sentence_id).first()

    if not sentence:
        return jsonify({"error": "Sentence not found"}), 404

    data = request.get_json()
    status_filter = data.get("status_filter", "ready")
    level_filter = data.get("level", "")
    pattern_filter = data.get("pattern", "")

    try:
        # Mark as rejected
        sentence.rejected = True
        g.db.commit()

        # Get next sentence
        next_sentence = get_next_sentence(sentence_id, status_filter, level_filter, pattern_filter)

        if next_sentence:
            return jsonify(
                {
                    "success": True,
                    "has_next": True,
                    "next_sentence": next_sentence,
                }
            )
        else:
            return jsonify(
                {"success": True, "has_next": False, "message": "No more sentences to review"}
            )

    except Exception as e:
        g.db.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/skip/<int:sentence_id>", methods=["POST"])
def skip(sentence_id: int) -> ResponseReturnValue:
    """Skip to next sentence without changing status (AJAX endpoint)."""
    sentence = g.db.query(Sentence).filter_by(id=sentence_id).first()

    if not sentence:
        return jsonify({"error": "Sentence not found"}), 404

    data = request.get_json()
    status_filter = data.get("status_filter", "ready")
    level_filter = data.get("level", "")
    pattern_filter = data.get("pattern", "")

    try:
        # Get next sentence
        next_sentence = get_next_sentence(sentence_id, status_filter, level_filter, pattern_filter)

        if next_sentence:
            return jsonify(
                {
                    "success": True,
                    "has_next": True,
                    "next_sentence": next_sentence,
                }
            )
        else:
            return jsonify(
                {"success": True, "has_next": False, "message": "No more sentences to review"}
            )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/undo/<int:sentence_id>", methods=["POST"])
def undo(sentence_id: int) -> ResponseReturnValue:
    """Undo verification/rejection of a sentence (AJAX endpoint)."""
    sentence = g.db.query(Sentence).filter_by(id=sentence_id).first()

    if not sentence:
        return jsonify({"error": "Sentence not found"}), 404

    data = request.get_json()
    previous_verified = data.get("previous_verified", False)
    previous_rejected = data.get("previous_rejected", False)

    try:
        # Restore previous state
        sentence.verified = previous_verified
        sentence.rejected = previous_rejected
        g.db.commit()

        # Get translations for this sentence
        translations = get_sentence_translations(sentence_id)

        # Generate pinyin for Chinese
        pinyin_text = None
        if translations.get("zh"):
            pinyin_text = generate_pinyin(translations["zh"])

        return jsonify(
            {
                "success": True,
                "sentence": {
                    "id": sentence.id,
                    "pattern_type": sentence.pattern_type,
                    "tense": sentence.tense,
                    "minimum_level": sentence.minimum_level,
                    "translations": translations,
                    "pinyin": pinyin_text,
                },
            }
        )

    except Exception as e:
        g.db.rollback()
        return jsonify({"error": str(e)}), 500
