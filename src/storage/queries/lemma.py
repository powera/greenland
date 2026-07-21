"""General-purpose lemma query functions."""

from typing import Any, Dict, Optional

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Query, Session

from storage.models.schema import Lemma, LemmaDifficultyOverride, LemmaTranslation


def apply_effective_difficulty_filter(
    query: Query[Any], language_code: str, difficulty_level: int
) -> Query[Any]:
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


def get_difficulty_stats(
    session: Session, pos_type: str, pos_subtype: Optional[str] = None
) -> Dict[int, int]:
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
    session: Session,
    search: Optional[str] = None,
    pos_type: Optional[str] = None,
    pos_subtype: Optional[str] = None,
    difficulty: Optional[str] = None,
    display_language_code: str = "en",
) -> Query[Lemma]:
    """
    Build a filtered and ordered lemma query for search/listing.

    Args:
        session: Database session
        search: Search term to find in lemma text, definition, disambiguation, and translations
        pos_type: Filter by part of speech type
        pos_subtype: Filter by part of speech subtype
        difficulty: Filter by difficulty level (supports "-1", "null", or numeric string)

    Returns:
        SQLAlchemy query object with filters and ordering applied
    """
    # Build base query
    query = session.query(Lemma)

    # Join display language translation for sorting/relevance in non-English views
    display_translation_joined = False
    if display_language_code != "en":
        query = query.outerjoin(
            LemmaTranslation,
            (LemmaTranslation.lemma_id == Lemma.id)
            & (LemmaTranslation.language_code == display_language_code),
        )
        display_translation_joined = True

    # Apply search filter
    if search:
        # Search in lemma text, definition, disambiguation, and ALL translations
        search_conditions = [
            Lemma.lemma_text.ilike(f"%{search}%"),
            Lemma.definition_text.ilike(f"%{search}%"),
            Lemma.disambiguation.ilike(f"%{search}%"),
            # Translations are matched via the LemmaTranslation subquery below.
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

    # Apply POS subtype filter
    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)

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
            # Translation matches, in any language
            (
                Lemma.id.in_(
                    session.query(LemmaTranslation.lemma_id).filter(
                        func.lower(LemmaTranslation.translation).contains(search_lower)
                    )
                ),
                6,
            ),
            else_=7,
        )
        if display_translation_joined:
            display_text_order = func.lower(
                func.coalesce(
                    LemmaTranslation.sort_key, LemmaTranslation.translation, Lemma.lemma_text
                )
            )
            query = query.order_by(relevance, display_text_order)
        else:
            query = query.order_by(relevance, func.lower(Lemma.lemma_text))
    else:
        # No search: order by difficulty level first, then case-insensitive alphabetically
        # Put NULL levels at the end, then -1 (not applicable), then levels 1-9
        level_order = case(
            (Lemma.difficulty_level.is_(None), 99),  # NULL levels last
            (Lemma.difficulty_level == -1, 98),  # -1 (not applicable) second to last
            else_=Lemma.difficulty_level,
        )
        if display_translation_joined:
            display_text_order = func.lower(
                func.coalesce(
                    LemmaTranslation.sort_key, LemmaTranslation.translation, Lemma.lemma_text
                )
            )
            query = query.order_by(level_order, display_text_order)
        else:
            query = query.order_by(level_order, func.lower(Lemma.lemma_text))

    return query
