"""General-purpose lemma query functions."""

from typing import Optional
from sqlalchemy import case, func, or_

from wordfreq.storage.models.schema import Lemma, LemmaDifficultyOverride, LemmaTranslation


def apply_effective_difficulty_filter(query, language_code: str, difficulty_level: int):
    """
    Apply difficulty level filter considering language-specific overrides.

    This uses a SQL COALESCE to prefer override difficulty over base difficulty.
    The query must already have Lemma joined.

    Args:
        query: SQLAlchemy query with Lemma joined
        language_code: Language code (e.g., "lt", "zh")
        difficulty_level: Target difficulty level

    Returns:
        Modified query with difficulty filter applied
    """
    # Left join with difficulty overrides for the specific language
    query = query.outerjoin(
        LemmaDifficultyOverride,
        (LemmaDifficultyOverride.lemma_id == Lemma.id)
        & (LemmaDifficultyOverride.language_code == language_code),
    )

    # Use COALESCE to prefer override difficulty, fall back to base difficulty
    # Filter by the effective difficulty level
    effective_difficulty = case(
        (
            LemmaDifficultyOverride.difficulty_level.isnot(None),
            LemmaDifficultyOverride.difficulty_level,
        ),
        else_=Lemma.difficulty_level,
    )

    query = query.filter(effective_difficulty == difficulty_level)

    return query


def get_difficulty_stats(session, pos_type, pos_subtype):
    """
    Get difficulty level distribution for a given POS type/subtype.

    Args:
        session: Database session
        pos_type: Part of speech type
        pos_subtype: Part of speech subtype (optional)

    Returns:
        Dictionary mapping difficulty levels to counts
        Example: {1: 45, 2: 123, 3: 67}
    """
    query = session.query(Lemma.difficulty_level, func.count(Lemma.id)).filter(
        Lemma.pos_type == pos_type, Lemma.difficulty_level.isnot(None)
    )

    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)

    query = query.group_by(Lemma.difficulty_level).order_by(Lemma.difficulty_level)

    results = query.all()

    # Format as a dictionary
    stats = {}
    for level, count in results:
        stats[level] = count

    return stats


def build_lemma_search_query(
    session,
    search: Optional[str] = None,
    pos_type: Optional[str] = None,
    difficulty: Optional[str] = None,
):
    """
    Build a filtered and ordered lemma query for search/listing.

    Args:
        session: Database session
        search: Search term to find in lemma text, definition, disambiguation, and translations
        pos_type: Filter by part of speech type
        difficulty: Filter by difficulty level (supports "-1", "null", or numeric string)

    Returns:
        SQLAlchemy query object with filters and ordering applied
    """
    # Build base query
    query = session.query(Lemma)

    # Apply search filter
    if search:
        # Search in lemma text, definition, disambiguation, and ALL translations
        search_conditions = [
            Lemma.lemma_text.ilike(f"%{search}%"),
            Lemma.definition_text.ilike(f"%{search}%"),
            Lemma.disambiguation.ilike(f"%{search}%"),
            # Search in legacy translation columns
            Lemma.chinese_translation.ilike(f"%{search}%"),
            Lemma.french_translation.ilike(f"%{search}%"),
            Lemma.korean_translation.ilike(f"%{search}%"),
            Lemma.swahili_translation.ilike(f"%{search}%"),
            Lemma.lithuanian_translation.ilike(f"%{search}%"),
            Lemma.vietnamese_translation.ilike(f"%{search}%"),
        ]

        # Also search in LemmaTranslation table
        translation_subquery = session.query(LemmaTranslation.lemma_id).filter(
            LemmaTranslation.translation.ilike(f"%{search}%")
        )

        search_conditions.append(Lemma.id.in_(translation_subquery))

        query = query.filter(or_(*search_conditions))

    # Apply POS type filter
    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)

    # Apply difficulty filter
    if difficulty:
        if difficulty == "-1":
            query = query.filter(Lemma.difficulty_level == -1)
        elif difficulty == "null":
            query = query.filter(Lemma.difficulty_level.is_(None))
        else:
            query = query.filter(Lemma.difficulty_level == int(difficulty))

    # Apply ordering
    if search:
        # Order by relevance: exact matches first, then starts-with, then contains
        search_lower = search.lower()
        relevance = case(
            (func.lower(Lemma.lemma_text) == search_lower, 1),  # Exact match in lemma
            (func.lower(Lemma.lemma_text).startswith(search_lower), 2),  # Starts with in lemma
            (func.lower(Lemma.lemma_text).contains(search_lower), 3),  # Contains in lemma
            (func.lower(Lemma.definition_text).contains(search_lower), 4),  # Contains in definition
            (
                func.lower(Lemma.disambiguation).contains(search_lower),
                5,
            ),  # Contains in disambiguation
            # Translation matches
            (func.lower(Lemma.lithuanian_translation).contains(search_lower), 6),
            (func.lower(Lemma.chinese_translation).contains(search_lower), 6),
            (func.lower(Lemma.french_translation).contains(search_lower), 6),
            (func.lower(Lemma.korean_translation).contains(search_lower), 6),
            (func.lower(Lemma.swahili_translation).contains(search_lower), 6),
            (func.lower(Lemma.vietnamese_translation).contains(search_lower), 6),
            else_=7,
        )
        query = query.order_by(relevance, func.lower(Lemma.lemma_text))
    else:
        # No search: order by difficulty level first, then case-insensitive alphabetically
        # Put NULL levels at the end, then -1 (not applicable), then levels 1-9
        level_order = case(
            (Lemma.difficulty_level.is_(None), 99),  # NULL levels last
            (Lemma.difficulty_level == -1, 98),  # -1 (not applicable) second to last
            else_=Lemma.difficulty_level,
        )
        query = query.order_by(level_order, func.lower(Lemma.lemma_text))

    return query
