"""Standardized lemma selection and filtering utilities for agents.

This module provides tested, reusable functions for selecting which lemmas
to process in agent scripts. It standardizes common patterns like:
- GUID-based single lemma lookup
- Curated lemmas filtering (lemmas with GUIDs)
- Difficulty level filtering
- Language translation availability filtering
- Limit and sample-rate application

Usage:
    from agents.lemma_selection import (
        find_lemma_by_guid,
        LemmaQueryBuilder,
        apply_limit_and_sample_rate,
    )

    # Single lemma by GUID
    lemma = find_lemma_by_guid(session, args.guid)

    # Batch query with filters
    query = (
        LemmaQueryBuilder(session)
        .curated_only()
        .by_difficulty_level(args.difficulty_level)
        .order_by_id()
        .build()
    )
    lemmas = apply_limit_and_sample_rate(query, args.limit, args.sample_rate)
"""

import sys
import random
from typing import Optional, List, Callable

from sqlalchemy.orm import Query
from wordfreq.storage.backend.base import BaseSession

from wordfreq.storage.models.schema import Lemma


class LemmaNotFoundError(Exception):
    """Raised when a lemma lookup fails."""
    pass


def find_lemma_by_guid(
    session: "BaseSession",
    guid: str,
    error_on_missing: bool = True,
) -> Optional[Lemma]:
    """Find a lemma by its GUID with standardized error handling.

    Args:
        session: Database session
        guid: The GUID to look up (e.g., "N14_001")
        error_on_missing: If True, print error and exit on missing GUID.
                         If False, return None silently.

    Returns:
        Lemma object if found, None if not found and error_on_missing=False

    Raises:
        SystemExit: If lemma not found and error_on_missing=True

    Example:
        lemma = find_lemma_by_guid(session, args.guid)
        print(f"Processing: {lemma.lemma_text}")
    """
    lemma = session.query(Lemma).filter(Lemma.guid == guid).first()

    if not lemma and error_on_missing:
        print(f"\nError: No lemma found with GUID: {guid}")
        print("Tip: Use the BARSUKAS web interface to find valid GUIDs")
        sys.exit(1)

    return lemma


class LemmaQueryBuilder:
    """Fluent interface for building lemma queries with common filters.

    This class provides a chainable interface for constructing SQLAlchemy
    queries with commonly-used filters across agents.

    Example:
        query = (
            LemmaQueryBuilder(session)
            .curated_only()
            .by_difficulty_level(1)
            .has_translation_in('fr')
            .order_by_id()
            .build()
        )
        lemmas = query.all()
    """

    def __init__(self, session: "BaseSession"):
        """Initialize query builder.

        Args:
            session: Database session to use for queries
        """
        self.session = session
        self.query = session.query(Lemma)

    def curated_only(self) -> 'LemmaQueryBuilder':
        """Filter to only curated lemmas (those with GUIDs assigned).

        This is the most common filter - agents typically only process
        lemmas that have been curated and assigned a GUID.

        Returns:
            Self for method chaining
        """
        self.query = self.query.filter(Lemma.guid.isnot(None))
        return self

    def by_difficulty_level(self, level: Optional[int]) -> 'LemmaQueryBuilder':
        """Filter by difficulty level.

        Args:
            level: Difficulty level (1-20 for Trakaido levels), or None to skip filter

        Returns:
            Self for method chaining
        """
        if level is not None:
            self.query = self.query.filter(Lemma.difficulty_level == level)
        return self

    def has_translation_in(self, language_code: str) -> 'LemmaQueryBuilder':
        """Filter to lemmas that have a translation in the specified language.

        This checks the language-specific translation columns on the Lemma model
        (e.g., french_translation, chinese_translation, etc.).

        Args:
            language_code: Language code (e.g., 'fr', 'zh', 'ko', 'sw', 'lt', 'vi')

        Returns:
            Self for method chaining

        Raises:
            ValueError: If language_code is not a recognized translation column
        """
        from wordfreq.storage.translation_helpers import LANG_CODE_TO_LLM_FIELD

        if language_code not in LANG_CODE_TO_LLM_FIELD:
            raise ValueError(
                f"Language code '{language_code}' not recognized. "
                f"Valid codes: {sorted(LANG_CODE_TO_LLM_FIELD.keys())}"
            )

        column_name = LANG_CODE_TO_LLM_FIELD[language_code]
        column = getattr(Lemma, column_name)
        self.query = self.query.filter(column.isnot(None))
        return self

    def order_by_id(self, ascending: bool = True) -> 'LemmaQueryBuilder':
        """Order results by lemma ID for consistent, reproducible ordering.

        Args:
            ascending: If True, order ascending (default). If False, descending.

        Returns:
            Self for method chaining
        """
        if ascending:
            self.query = self.query.order_by(Lemma.id)
        else:
            self.query = self.query.order_by(Lemma.id.desc())
        return self

    def filter_custom(self, filter_func: Callable) -> 'LemmaQueryBuilder':
        """Apply a custom filter function to the query.

        This allows agents to add specialized filters while still using
        the builder pattern.

        Args:
            filter_func: Function that takes a query and returns a modified query

        Returns:
            Self for method chaining

        Example:
            def only_verbs(q):
                return q.filter(Lemma.pos_type == 'verb')

            query = builder.filter_custom(only_verbs).build()
        """
        self.query = filter_func(self.query)
        return self

    def build(self) -> Query:
        """Return the constructed SQLAlchemy query.

        Returns:
            SQLAlchemy Query object ready for .all(), .first(), .count(), etc.
        """
        return self.query


def apply_limit_and_sample_rate(
    query: Query,
    limit: Optional[int] = None,
    sample_rate: float = 1.0,
) -> List[Lemma]:
    """Apply limit and sample rate to a query and return results.

    This standardizes the logic for applying --limit and --sample-rate flags.

    Args:
        query: SQLAlchemy query to execute
        limit: Maximum number of items to return (applied before sampling)
        sample_rate: Fraction of items to randomly sample (0.0-1.0)
                    If < 1.0, items are randomly sampled after limit is applied

    Returns:
        List of Lemma objects

    Example:
        query = session.query(Lemma).filter(Lemma.guid.isnot(None))
        lemmas = apply_limit_and_sample_rate(query, args.limit, args.sample_rate)
    """
    # Apply limit first
    if limit is not None:
        query = query.limit(limit)

    lemmas = query.all()

    # Apply sample rate
    if 0.0 < sample_rate < 1.0:
        sample_size = max(1, int(len(lemmas) * sample_rate))
        lemmas = random.sample(lemmas, sample_size)

    return lemmas


def count_for_confirmation(
    query: Query,
    limit: Optional[int] = None,
    sample_rate: float = 1.0,
) -> int:
    """Count items that will be processed, for confirmation prompts.

    This applies the same logic as apply_limit_and_sample_rate but only
    returns the count. Useful for confirmation prompts.

    Args:
        query: SQLAlchemy query to count
        limit: Maximum number of items (applied before sampling)
        sample_rate: Fraction of items to sample (0.0-1.0)

    Returns:
        Estimated count of items that will be processed

    Example:
        query = LemmaQueryBuilder(session).curated_only().build()
        count = count_for_confirmation(query, args.limit, args.sample_rate)
        print(f"Will process {count} lemmas")
    """
    # Apply limit first
    if limit is not None:
        query = query.limit(limit)

    count = query.count()

    # Apply sample rate
    if 0.0 < sample_rate < 1.0:
        count = max(1, int(count * sample_rate))

    return count


def get_lemmas_for_processing(
    session: "BaseSession",
    guid: Optional[str] = None,
    curated_only: bool = True,
    difficulty_level: Optional[int] = None,
    language_code: Optional[str] = None,
    limit: Optional[int] = None,
    sample_rate: float = 1.0,
    order_by_id: bool = True,
) -> List[Lemma]:
    """High-level function to get lemmas based on common agent patterns.

    This is a convenience function that handles the common case of either:
    1. Single lemma by GUID (if guid is provided)
    2. Batch of lemmas with standard filters (if guid is None)

    Args:
        session: Database session
        guid: If provided, return only this lemma (ignoring other filters)
        curated_only: If True, only include lemmas with GUIDs
        difficulty_level: Filter by difficulty level (or None)
        language_code: Filter to lemmas with translation in this language (or None)
        limit: Maximum number of lemmas to process
        sample_rate: Fraction of lemmas to sample (0.0-1.0)
        order_by_id: If True, order by ID for reproducibility

    Returns:
        List of Lemma objects (single-item list if guid is provided)

    Example:
        # Single lemma mode
        lemmas = get_lemmas_for_processing(session, guid=args.guid)

        # Batch mode
        lemmas = get_lemmas_for_processing(
            session,
            difficulty_level=1,
            language_code='fr',
            limit=args.limit,
            sample_rate=args.sample_rate,
        )
    """
    # Single lemma mode
    if guid:
        lemma = find_lemma_by_guid(session, guid, error_on_missing=True)
        if lemma:
            return [lemma]
        else:
            raise Exception(f"Unexpected error: Lemma with GUID {guid} not found.")

    # Batch mode: build query with filters
    builder = LemmaQueryBuilder(session)

    if curated_only:
        builder = builder.curated_only()

    if difficulty_level is not None:
        builder = builder.by_difficulty_level(difficulty_level)

    if language_code:
        builder = builder.has_translation_in(language_code)

    if order_by_id:
        builder = builder.order_by_id()

    query = builder.build()

    return apply_limit_and_sample_rate(query, limit, sample_rate)


def get_lemmas_for_agent(session: "BaseSession", args) -> List[Lemma]:
    """Get lemmas for processing based on command-line arguments.

    This is the standard entry point for agents that need to process lemmas.
    It extracts the relevant arguments and delegates to get_lemmas_for_processing.

    Args:
        session: Database session
        args: Parsed command-line arguments (argparse Namespace)
              Expected attributes: guid, limit, sample_rate, difficulty_level (optional)

    Returns:
        List of Lemma objects to process

    Example:
        # In agent CLI main():
        session = agent.get_session()
        lemmas = get_lemmas_for_agent(session, args)
        for lemma in lemmas:
            process(lemma)
    """
    return get_lemmas_for_processing(
        session=session,
        guid=getattr(args, 'guid', None),
        curated_only=True,
        difficulty_level=getattr(args, 'difficulty_level', None),
        language_code=getattr(args, 'language', None),
        limit=getattr(args, 'limit', None),
        sample_rate=getattr(args, 'sample_rate', 1.0),
        order_by_id=True,
    )
