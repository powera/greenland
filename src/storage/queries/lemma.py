"""General-purpose lemma query functions."""

from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Query, Session

from storage.models.schema import (
    DerivativeForm,
    Lemma,
    LemmaDifficultyOverride,
    LemmaTranslation,
)
from storage.models.variant_form import VariantForm


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

    The text search covers the same ground as ``word_exists_in_english``: lemma
    text, definition, disambiguation, translations in any language, and -- for
    English -- derivative forms and alternate spellings. Folding the last two in
    keeps search and the import guard agreeing about what the database holds, so
    "grey" finds the existing "gray" lemma rather than reporting it missing.

    Args:
        session: Database session
        search: Search term to find in lemma text, definition, disambiguation,
            translations, and English derivative/variant forms
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

        # English derivative forms ("grayer", "walked") and alternate spellings
        # ("grey" for "gray"). Without these, search disagrees with
        # word_exists_in_english about what the database contains -- the guard
        # folds both in, so a caller surveying for missing words gets one answer
        # from search and another from the add endpoint.
        derivative_subquery = session.query(DerivativeForm.lemma_id).filter(
            DerivativeForm.language_code == "en",
            DerivativeForm.derivative_form_text.ilike(f"%{search}%"),
        )
        search_conditions.append(Lemma.id.in_(derivative_subquery))

        variant_subquery = session.query(VariantForm.lemma_id).filter(
            VariantForm.language_code == "en",
            VariantForm.variant_form_text.ilike(f"%{search}%"),
        )
        search_conditions.append(Lemma.id.in_(variant_subquery))

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
            # An alternate spelling is a closer hit than an inflection: "grey"
            # names the same lexeme, "walked" is a form of it.
            (
                Lemma.id.in_(
                    session.query(VariantForm.lemma_id).filter(
                        VariantForm.language_code == "en",
                        func.lower(VariantForm.variant_form_text).contains(search_lower),
                    )
                ),
                7,
            ),
            (
                Lemma.id.in_(
                    session.query(DerivativeForm.lemma_id).filter(
                        DerivativeForm.language_code == "en",
                        func.lower(DerivativeForm.derivative_form_text).contains(search_lower),
                    )
                ),
                8,
            ),
            else_=9,
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


def _disambiguation_base(lemma_text: str) -> Optional[str]:
    """Return the bare word behind a disambiguated lemma, if it is one.

    "light (color)" -> "light"; "light" -> None.
    """
    paren_idx = lemma_text.find(" (")
    return lemma_text[:paren_idx] if paren_idx > 0 else None


def word_exists_in_english(
    session: Session, word: str, *, include_exclusions: bool = False
) -> bool:
    """
    Return whether the database already accounts for this English word, in any form.

    This is the canonical "do we already have this lexeme?" check. The answer is
    deliberately broader than the lemmas table -- a word counts as existing if it
    appears as any of:

      * a lemma ("gray")
      * a disambiguated lemma whose base is this word -- a plain "light" is
        covered by an existing "light (color)"
      * an English derivative form ("grayer", "walked")
      * an English variant form -- alternate spellings such as "grey" for
        "gray", which live in ``variant_forms`` rather than as their own lemma

    Callers that gate *imports* should pass ``include_exclusions=True`` to fold
    in the word-exclusions list, so a word rejected once is not re-proposed.
    Callers that measure *coverage* should leave it False: an excluded word is
    genuinely absent from the dictionary, and counting it as present would
    overstate coverage.

    For more than a handful of words use ``filter_existing_english_words``,
    which answers the same question for a whole batch in a few queries.

    Args:
        session: SQLAlchemy database session
        word: English word to look for
        include_exclusions: Also count words on the English exclusions list

    Returns:
        True if the word is already accounted for
    """
    from storage.models.imports import WordExclusion
    from storage.models.schema import DerivativeForm
    from storage.models.variant_form import VariantForm

    normalized = word.strip().lower()
    if not normalized:
        return False

    lemma_match = (
        session.query(Lemma.id)
        .filter(
            or_(
                func.lower(Lemma.lemma_text) == normalized,
                func.lower(Lemma.lemma_text).startswith(normalized + " ("),
            )
        )
        .first()
    )
    if lemma_match is not None:
        return True

    form_match = (
        session.query(DerivativeForm.id)
        .filter(
            DerivativeForm.language_code == "en",
            func.lower(DerivativeForm.derivative_form_text) == normalized,
        )
        .first()
    )
    if form_match is not None:
        return True

    variant_match = (
        session.query(VariantForm.id)
        .filter(
            VariantForm.language_code == "en",
            func.lower(VariantForm.variant_form_text) == normalized,
        )
        .first()
    )
    if variant_match is not None:
        return True

    if include_exclusions:
        exclusion_match = (
            session.query(WordExclusion.id)
            .filter(
                WordExclusion.language_code == "en",
                func.lower(WordExclusion.excluded_word) == normalized,
            )
            .first()
        )
        if exclusion_match is not None:
            return True

    return False


def filter_existing_english_words(
    session: Session, words: Iterable[str], *, include_exclusions: bool = False
) -> Set[str]:
    """
    Return which of ``words`` the database already accounts for.

    The batch form of ``word_exists_in_english`` -- same definition of
    "exists", answered for many words in a fixed number of queries rather than
    one per word. Callers checking thousands of candidates (the frequency check,
    wordlist coverage) should use this.

    Only the given words are looked up, so cost scales with the batch rather
    than with the size of the dictionary.

    Args:
        session: SQLAlchemy database session
        words: English words to look for
        include_exclusions: Also count words on the English exclusions list

    Returns:
        The subset of ``words``, lowercased, that already exist. Words absent
        from the database do not appear.
    """
    from storage.models.imports import WordExclusion
    from storage.models.schema import DerivativeForm
    from storage.models.variant_form import VariantForm

    wanted = {word.strip().lower() for word in words}
    wanted.discard("")
    if not wanted:
        return set()

    found: Set[str] = set()

    # SQLite caps the number of variables per statement (999 by default), and
    # these run over thousands of candidates, so the IN-lists are chunked.
    chunk_size = 500
    wanted_list: List[str] = sorted(wanted)

    def _collect(column: Any, extra_filter: Any = None) -> None:
        for start in range(0, len(wanted_list), chunk_size):
            chunk = wanted_list[start : start + chunk_size]
            query = session.query(column).filter(func.lower(column).in_(chunk))
            if extra_filter is not None:
                query = query.filter(extra_filter)
            for (value,) in query.all():
                found.add(value.strip().lower())

    _collect(Lemma.lemma_text)
    _collect(DerivativeForm.derivative_form_text, DerivativeForm.language_code == "en")
    _collect(VariantForm.variant_form_text, VariantForm.language_code == "en")
    if include_exclusions:
        _collect(WordExclusion.excluded_word, WordExclusion.language_code == "en")

    # Disambiguated lemmas: a bare "light" is covered by "light (color)". These
    # cannot be matched by equality, so ask for the prefixed forms directly.
    missing = wanted - found
    if missing:
        missing_list = sorted(missing)
        for start in range(0, len(missing_list), chunk_size):
            chunk = missing_list[start : start + chunk_size]
            clauses = [
                func.lower(Lemma.lemma_text).startswith(candidate + " (") for candidate in chunk
            ]
            rows = session.query(Lemma.lemma_text).filter(or_(*clauses)).all()
            for (lemma_text,) in rows:
                base = _disambiguation_base(lemma_text.strip().lower())
                if base is not None and base in wanted:
                    found.add(base)

    return found
