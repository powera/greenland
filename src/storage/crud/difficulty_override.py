"""CRUD operations for LemmaDifficultyOverride model."""

from typing import Any, Dict, List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from storage.models.schema import Lemma, LemmaDifficultyOverride


def add_difficulty_override(
    session: Session,
    lemma_id: int,
    language_code: str,
    difficulty_level: int,
    notes: Optional[str] = None,
) -> LemmaDifficultyOverride:
    """
    Add or update a difficulty level override for a lemma in a specific language.

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code (e.g., 'zh', 'fr', 'de')
        difficulty_level: Difficulty level (1-20) or -1 to exclude from language
        notes: Optional notes explaining the override

    Returns:
        The created or updated LemmaDifficultyOverride
    """
    # Check if override already exists
    existing = (
        session.query(LemmaDifficultyOverride)
        .filter(
            and_(
                LemmaDifficultyOverride.lemma_id == lemma_id,
                LemmaDifficultyOverride.language_code == language_code,
            )
        )
        .first()
    )

    if existing:
        # Update existing override
        existing.difficulty_level = difficulty_level
        if notes is not None:
            existing.notes = notes
        session.flush()
        result: LemmaDifficultyOverride = existing
        return result

    # Create new override
    override = LemmaDifficultyOverride(
        lemma_id=lemma_id,
        language_code=language_code,
        difficulty_level=difficulty_level,
        notes=notes,
    )
    session.add(override)
    session.flush()
    return override


def get_difficulty_override(
    session: Session, lemma_id: int, language_code: str
) -> Optional[LemmaDifficultyOverride]:
    """
    Get a difficulty override for a specific lemma and language.

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code

    Returns:
        LemmaDifficultyOverride if found, None otherwise
    """
    result: Optional[LemmaDifficultyOverride] = (
        session.query(LemmaDifficultyOverride)
        .filter(
            and_(
                LemmaDifficultyOverride.lemma_id == lemma_id,
                LemmaDifficultyOverride.language_code == language_code,
            )
        )
        .first()
    )
    return result


def get_all_overrides_for_lemma(session: Session, lemma_id: int) -> List[LemmaDifficultyOverride]:
    """
    Get all difficulty overrides for a specific lemma across all languages.

    Args:
        session: Database session
        lemma_id: ID of the lemma

    Returns:
        List of LemmaDifficultyOverride objects
    """
    result: list[LemmaDifficultyOverride] = (
        session.query(LemmaDifficultyOverride)
        .filter(LemmaDifficultyOverride.lemma_id == lemma_id)
        .all()
    )
    return result


def get_all_overrides_for_language(
    session: Session, language_code: str
) -> List[LemmaDifficultyOverride]:
    """
    Get all difficulty overrides for a specific language.

    Args:
        session: Database session
        language_code: Language code

    Returns:
        List of LemmaDifficultyOverride objects
    """
    result: list[LemmaDifficultyOverride] = (
        session.query(LemmaDifficultyOverride)
        .filter(LemmaDifficultyOverride.language_code == language_code)
        .all()
    )
    return result


def delete_difficulty_override(session: Session, lemma_id: int, language_code: str) -> bool:
    """
    Delete a difficulty override.

    Args:
        session: Database session
        lemma_id: ID of the lemma
        language_code: Language code

    Returns:
        True if an override was deleted, False if none existed
    """
    override = get_difficulty_override(session, lemma_id, language_code)
    if override:
        session.delete(override)
        session.flush()
        return True
    return False


def get_effective_difficulty_level(
    session: Session, lemma: Lemma, language_code: str
) -> Optional[int]:
    """
    Get the effective difficulty level for a lemma in a specific language.

    This checks for language-specific overrides first, then falls back to
    the default difficulty_level on the lemma.

    A return value of -1 means the word should be excluded from this language.
    A return value of None means no difficulty level is set.

    Args:
        session: Database session
        lemma: Lemma object
        language_code: Language code (e.g., 'zh', 'fr', 'de')

    Returns:
        Effective difficulty level (1-20), -1 (excluded), or None (no level set)
    """
    # Check for override first
    override = get_difficulty_override(session, lemma.id, language_code)
    if override:
        result: Optional[int] = override.difficulty_level
        return result

    # Fall back to default difficulty level
    fallback: Optional[int] = lemma.difficulty_level
    return fallback


def get_lemmas_by_effective_level(
    session: Session,
    language_code: str,
    difficulty_level: int,
    pos_type: Optional[str] = None,
    pos_subtype: Optional[str] = None,
) -> List[Lemma]:
    """
    Get all lemmas that have a specific effective difficulty level in a language.

    This considers both default levels and language-specific overrides.
    Excludes lemmas with level -1 (excluded from language).

    Args:
        session: Database session
        language_code: Language code
        difficulty_level: Target difficulty level
        pos_type: Optional filter by POS type
        pos_subtype: Optional filter by POS subtype

    Returns:
        List of Lemma objects
    """
    # Start with base query
    query = session.query(Lemma)

    # Apply POS filters if provided
    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)
    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)

    # Get all matching lemmas
    all_lemmas = query.all()

    # Filter by effective difficulty level
    result = []
    for lemma in all_lemmas:
        effective_level = get_effective_difficulty_level(session, lemma, language_code)
        if effective_level == difficulty_level:
            result.append(lemma)

    return result


def bulk_add_overrides(session: Session, overrides: List[Dict[str, Any]]) -> int:
    """
    Bulk add or update difficulty overrides.

    Args:
        session: Database session
        overrides: List of dicts with keys: lemma_id, language_code, difficulty_level, notes (optional)

    Returns:
        Number of overrides added/updated
    """
    count = 0
    for override_data in overrides:
        add_difficulty_override(
            session=session,
            lemma_id=override_data["lemma_id"],
            language_code=override_data["language_code"],
            difficulty_level=override_data["difficulty_level"],
            notes=override_data.get("notes"),
        )
        count += 1

    session.flush()
    return count


def bulk_get_effective_difficulty_levels(
    session: Session, lemmas: List[Lemma], language_code: str
) -> Dict[int, Optional[int]]:
    """
    Get effective difficulty levels for multiple lemmas in a single query.

    This is an optimized version of get_effective_difficulty_level for bulk operations,
    reducing N+1 query problems when processing many lemmas.

    Args:
        session: Database session
        lemmas: List of Lemma objects
        language_code: Language code (e.g., 'zh', 'fr', 'de')

    Returns:
        Dictionary mapping lemma_id to effective difficulty level.
        Level is -1 for excluded, None for no level set, or 1-20 for actual level.
    """
    if not lemmas:
        return {}

    lemma_ids = [lemma.id for lemma in lemmas]

    # Fetch all overrides for this language in one query
    overrides = (
        session.query(LemmaDifficultyOverride)
        .filter(
            LemmaDifficultyOverride.lemma_id.in_(lemma_ids),
            LemmaDifficultyOverride.language_code == language_code,
        )
        .all()
    )

    # Build override lookup
    override_by_lemma = {o.lemma_id: o.difficulty_level for o in overrides}

    # Build result: use override if exists, otherwise use lemma's default
    result: Dict[int, Optional[int]] = {}
    for lemma in lemmas:
        if lemma.id in override_by_lemma:
            result[lemma.id] = override_by_lemma[lemma.id]
        else:
            result[lemma.id] = lemma.difficulty_level

    return result
