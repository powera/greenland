"""CRUD operations for Lemma model."""

import json
from typing import List, Optional

from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.utils.guid import generate_guid
from wordfreq.storage.crud.operation_log import log_translation_change


def add_lemma(
    session,
    lemma_text: str,
    definition_text: str,
    pos_type: str,
    pos_subtype: Optional[str] = None,
    difficulty_level: Optional[int] = None,
    frequency_rank: Optional[int] = None,
    tags: Optional[List[str]] = None,
    chinese_translation: Optional[str] = None,
    french_translation: Optional[str] = None,
    korean_translation: Optional[str] = None,
    swahili_translation: Optional[str] = None,
    lithuanian_translation: Optional[str] = None,
    vietnamese_translation: Optional[str] = None,
    confidence: float = 0.0,
    verified: bool = False,
    notes: Optional[str] = None,
    auto_generate_guid: bool = True,
    source: Optional[str] = None,
) -> Lemma:
    """Add or get a lemma (concept/meaning)."""
    # Check if lemma already exists with same text, definition, and POS
    existing = (
        session.query(Lemma)
        .filter(
            Lemma.lemma_text == lemma_text,
            Lemma.definition_text == definition_text,
            Lemma.pos_type == pos_type,
        )
        .first()
    )

    if existing:
        return existing

    # Generate GUID if pos_subtype is provided and auto_generate_guid is True
    guid = None
    if pos_subtype and auto_generate_guid:
        guid = generate_guid(session, pos_subtype)

    # Convert tags list to JSON string
    tags_json = None
    if tags:
        tags_json = json.dumps(tags)

    lemma = Lemma(
        lemma_text=lemma_text,
        definition_text=definition_text,
        pos_type=pos_type,
        pos_subtype=pos_subtype,
        guid=guid,
        difficulty_level=difficulty_level,
        frequency_rank=frequency_rank,
        tags=tags_json,
        chinese_translation=chinese_translation,
        french_translation=french_translation,
        korean_translation=korean_translation,
        swahili_translation=swahili_translation,
        lithuanian_translation=lithuanian_translation,
        vietnamese_translation=vietnamese_translation,
        confidence=confidence,
        verified=verified,
        notes=notes,
    )
    session.add(lemma)
    session.flush()

    # Log translation additions
    translation_map = {
        "zh": chinese_translation,
        "fr": french_translation,
        "ko": korean_translation,
        "sw": swahili_translation,
        "lt": lithuanian_translation,
        "vi": vietnamese_translation,
    }

    for lang_code, translation in translation_map.items():
        if translation:
            log_translation_change(
                session=session,
                source=source or "lemma-crud/add",
                operation_type="translation",
                lemma_id=lemma.id,
                language_code=lang_code,
                old_translation=None,
                new_translation=translation,
            )

    return lemma


def update_lemma(
    session,
    lemma_id: int,
    lemma_text: Optional[str] = None,
    definition_text: Optional[str] = None,
    pos_type: Optional[str] = None,
    pos_subtype: Optional[str] = None,
    difficulty_level: Optional[int] = None,
    frequency_rank: Optional[int] = None,
    tags: Optional[List[str]] = None,
    chinese_translation: Optional[str] = None,
    french_translation: Optional[str] = None,
    korean_translation: Optional[str] = None,
    swahili_translation: Optional[str] = None,
    lithuanian_translation: Optional[str] = None,
    vietnamese_translation: Optional[str] = None,
    confidence: Optional[float] = None,
    verified: Optional[bool] = None,
    notes: Optional[str] = None,
    source: Optional[str] = None,
) -> bool:
    """Update lemma information.

    Args:
        session: Database session
        lemma_id: ID of the lemma to update
        source: Source of the update (for operation logging)
        ... (other parameters as before)
    """
    lemma = session.query(Lemma).filter(Lemma.id == lemma_id).first()
    if not lemma:
        return False

    # Map of translation parameters to language codes
    translation_updates = {
        "zh": ("chinese_translation", chinese_translation),
        "fr": ("french_translation", french_translation),
        "ko": ("korean_translation", korean_translation),
        "sw": ("swahili_translation", swahili_translation),
        "lt": ("lithuanian_translation", lithuanian_translation),
        "vi": ("vietnamese_translation", vietnamese_translation),
    }

    # Track translation changes for logging
    for lang_code, (field_name, new_value) in translation_updates.items():
        if new_value is not None:
            old_value = getattr(lemma, field_name, None)
            if old_value != new_value:
                # Log the translation change
                log_translation_change(
                    session=session,
                    source=source or "lemma-crud/update",
                    operation_type="translation",
                    lemma_id=lemma.id,
                    language_code=lang_code,
                    old_translation=old_value,
                    new_translation=new_value,
                )

    if lemma_text is not None:
        lemma.lemma_text = lemma_text
    if definition_text is not None:
        lemma.definition_text = definition_text
    if pos_type is not None:
        lemma.pos_type = pos_type
    if pos_subtype is not None:
        lemma.pos_subtype = pos_subtype
    if difficulty_level is not None:
        lemma.difficulty_level = difficulty_level
    if frequency_rank is not None:
        lemma.frequency_rank = frequency_rank
    if tags is not None:
        lemma.tags = json.dumps(tags)
    if chinese_translation is not None:
        lemma.chinese_translation = chinese_translation
    if french_translation is not None:
        lemma.french_translation = french_translation
    if korean_translation is not None:
        lemma.korean_translation = korean_translation
    if swahili_translation is not None:
        lemma.swahili_translation = swahili_translation
    if lithuanian_translation is not None:
        lemma.lithuanian_translation = lithuanian_translation
    if vietnamese_translation is not None:
        lemma.vietnamese_translation = vietnamese_translation
    if confidence is not None:
        lemma.confidence = confidence
    if verified is not None:
        lemma.verified = verified
    if notes is not None:
        lemma.notes = notes

    session.commit()
    return True


def get_lemma_by_guid(session, guid: str) -> Optional[Lemma]:
    """
    Get a lemma by its GUID.

    Args:
        session: Database session
        guid: The lemma's GUID (e.g., "N02_001")

    Returns:
        Lemma object or None if not found
    """
    return session.query(Lemma).filter(Lemma.guid == guid).first()


def get_lemmas_without_subtypes(session, limit: int = 100) -> List[Lemma]:
    """Get lemmas that need POS subtypes."""
    return (
        session.query(Lemma)
        .filter(Lemma.pos_subtype == None)
        .order_by(Lemma.id.desc())
        .limit(limit)
        .all()
    )


def get_all_subtypes(session, lang=None) -> List[str]:
    """Get all pos_subtypes that have lemmas with GUIDs."""
    query = (
        session.query(Lemma.pos_subtype)
        .filter(Lemma.pos_subtype != None)
        .filter(Lemma.guid != None)
    )

    if lang == "chinese":
        query = query.filter(Lemma.chinese_translation != None)

    subtypes = query.distinct().all()
    return [subtype[0] for subtype in subtypes if subtype[0]]


def get_lemmas_by_subtype(session, pos_subtype: str, lang=None) -> List[Lemma]:
    """Get all lemmas for a specific subtype, ordered by GUID."""
    query = session.query(Lemma).filter(Lemma.pos_subtype == pos_subtype).filter(Lemma.guid != None)
    if lang == "chinese":
        query = query.filter(Lemma.chinese_translation != None)

    return query.order_by(Lemma.guid).all()


def get_lemmas_by_subtype_and_level(
    session,
    pos_subtype: str = None,
    difficulty_level: int = None,
    limit: int = None,
    lang: str = None,
) -> List[Lemma]:
    """
    Get lemmas filtered by POS subtype and/or difficulty level.

    When lang is specified and difficulty_level is provided, uses language-specific
    overrides if available, otherwise uses the default difficulty_level.
    Excludes lemmas with effective difficulty level of -1 (excluded from language).

    Args:
        session: Database session
        pos_subtype: POS subtype to filter by (optional)
        difficulty_level: Difficulty level to filter by (optional)
        limit: Maximum number of lemmas to return (optional)
        lang: Language code (e.g., 'zh', 'lt', 'fr') for filtering by effective difficulty (optional)

    Returns:
        List of Lemma objects
    """
    from sqlalchemy import func
    from wordfreq.storage.models.schema import LemmaDifficultyOverride

    # Convert lang parameter to language code if needed
    lang_code = None
    if lang:
        lang_map = {
            "chinese": "zh",
            "lithuanian": "lt",
            "french": "fr",
            "german": "de",
            "korean": "ko",
            "vietnamese": "vi",
            "swahili": "sw",
        }
        lang_code = lang_map.get(lang, lang)

    query = session.query(Lemma)

    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)

    # Handle difficulty level filtering with language-specific overrides
    if difficulty_level is not None and lang_code:
        # Left join with overrides to get language-specific levels
        query = query.outerjoin(
            LemmaDifficultyOverride,
            (LemmaDifficultyOverride.lemma_id == Lemma.id)
            & (LemmaDifficultyOverride.language_code == lang_code),
        )
        # Use override if exists, otherwise use default
        # COALESCE returns first non-null value
        effective_level = func.coalesce(
            LemmaDifficultyOverride.difficulty_level, Lemma.difficulty_level
        )
        query = query.filter(effective_level == difficulty_level)
    elif difficulty_level is not None:
        # No language specified, just use default difficulty level
        query = query.filter(Lemma.difficulty_level == difficulty_level)

    # Exclude lemmas that are marked as excluded (-1) for this language
    if lang_code:
        # Also need to exclude lemmas with override level of -1
        # This is a bit tricky - we need another left join check
        # For now, we'll filter this in Python after the query
        pass

    # Order by frequency rank (lower is more frequent), then by GUID
    query = query.order_by(Lemma.frequency_rank.nulls_last(), Lemma.guid)

    if limit:
        query = query.limit(limit)

    results = query.all()

    # Post-process to exclude lemmas marked with level -1 for this language
    # (only when lang is specified but difficulty_level is not, or when we want to be safe)
    if lang_code and difficulty_level != -1:
        from wordfreq.storage.crud.difficulty_override import get_effective_difficulty_level

        filtered_results = []
        for lemma in results:
            effective = get_effective_difficulty_level(session, lemma, lang_code)
            # Exclude if effective level is -1 (unless we're explicitly querying for -1)
            if effective != -1 or difficulty_level == -1:
                filtered_results.append(lemma)
        return filtered_results

    return results
