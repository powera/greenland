"""General-purpose lemma query functions."""

from sqlalchemy import case, func

from wordfreq.storage.models.schema import Lemma, LemmaDifficultyOverride


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
