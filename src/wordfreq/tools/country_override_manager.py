#!/usr/bin/env python3
"""
Manager for applying country-related word difficulty level overrides.

This module provides the business logic for:
1. Finding country-related words (countries, nationalities, language names)
2. Applying language-specific difficulty overrides based on priority configuration
3. Generating preview reports of proposed changes
4. Bulk applying overrides to the database

Usage:
    from wordfreq.tools.country_override_manager import CountryOverrideManager
    from wordfreq.storage.database import create_database_session

    session = create_database_session()
    manager = CountryOverrideManager(session)

    # Preview changes for Chinese learners
    changes = manager.preview_changes("zh")

    # Apply changes
    manager.apply_overrides("zh")
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from sqlalchemy.orm import Session

from wordfreq.storage.crud.difficulty_override import (
    add_difficulty_override,
    get_all_overrides_for_lemma,
    get_difficulty_override,
)
from wordfreq.storage.models.schema import Lemma, LemmaDifficultyOverride
from wordfreq.tools.country_word_priorities import (
    COUNTRY_TO_NATIONALITY_MAP,
    TIER_1_LEVEL,
    TIER_2_LEVEL,
    TIER_3_LEVEL,
    get_all_tier_levels,
    get_country_level_for_language,
    get_supported_languages,
)


@dataclass
class OverrideChange:
    """Represents a proposed or applied override change."""

    guid: str
    word_text: str
    pos_subtype: str
    country_label: str  # The country this word is related to
    default_level: Optional[int]
    current_override: Optional[int]
    proposed_level: int
    reason: str

    @property
    def is_change(self) -> bool:
        """Whether this represents an actual change."""
        if self.current_override is not None:
            return self.current_override != self.proposed_level
        return (self.default_level or 0) != self.proposed_level


@dataclass
class OverrideSummary:
    """Summary of override changes for a language."""

    target_language: str
    total_words_analyzed: int
    words_with_changes: int
    changes_by_tier: Dict[int, int]
    changes: List[OverrideChange]


class CountryOverrideManager:
    """
    Manager for country-related word difficulty overrides.

    This class handles finding country-related words and applying
    language-specific difficulty level overrides.
    """

    # POS subtypes that are considered "country-related"
    COUNTRY_SUBTYPES = {"country", "nationality"}

    def __init__(self, session: Session):
        """
        Initialize the manager.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self._country_words: Optional[Dict[str, List[Lemma]]] = None
        self._nationality_words: Optional[Dict[str, List[Lemma]]] = None

    def _load_country_words(self) -> Dict[str, List[Lemma]]:
        """
        Load all country words from the database.

        Returns:
            Dictionary mapping concept_label to list of Lemma objects
        """
        if self._country_words is not None:
            return self._country_words

        self._country_words = {}

        countries = (
            self.session.query(Lemma)
            .filter(
                Lemma.pos_type == "noun",
                Lemma.pos_subtype == "country",
            )
            .all()
        )

        for lemma in countries:
            label = lemma.concept_label or lemma.lemma_text
            if label not in self._country_words:
                self._country_words[label] = []
            self._country_words[label].append(lemma)

        return self._country_words

    def _load_nationality_words(self) -> Dict[str, List[Lemma]]:
        """
        Load all nationality words from the database.

        Returns:
            Dictionary mapping concept_label to list of Lemma objects
        """
        if self._nationality_words is not None:
            return self._nationality_words

        self._nationality_words = {}

        nationalities = (
            self.session.query(Lemma)
            .filter(
                Lemma.pos_type == "noun",
                Lemma.pos_subtype == "nationality",
            )
            .all()
        )

        for lemma in nationalities:
            label = lemma.concept_label or lemma.lemma_text
            if label not in self._nationality_words:
                self._nationality_words[label] = []
            self._nationality_words[label].append(lemma)

        return self._nationality_words

    def _find_related_words_for_country(self, country_label: str) -> List[Tuple[Lemma, str]]:
        """
        Find all words related to a country.

        Args:
            country_label: The country concept_label (e.g., "Lithuania")

        Returns:
            List of tuples: (Lemma, relationship_type)
            where relationship_type is "country", "nationality", etc.
        """
        results: List[Tuple[Lemma, str]] = []

        # Get the country itself
        countries = self._load_country_words()
        if country_label in countries:
            for lemma in countries[country_label]:
                results.append((lemma, "country"))

        # Get the nationality (person from country)
        nationality_label = COUNTRY_TO_NATIONALITY_MAP.get(country_label)
        if nationality_label:
            nationalities = self._load_nationality_words()
            if nationality_label in nationalities:
                for lemma in nationalities[nationality_label]:
                    results.append((lemma, "nationality"))

        return results

    def get_all_country_related_words(self) -> List[Lemma]:
        """
        Get all country-related words (countries and nationalities).

        Returns:
            List of Lemma objects
        """
        countries = self._load_country_words()
        nationalities = self._load_nationality_words()

        all_words: List[Lemma] = []
        for lemmas in countries.values():
            all_words.extend(lemmas)
        for lemmas in nationalities.values():
            all_words.extend(lemmas)

        return all_words

    def preview_changes(
        self,
        target_language: str,
        include_unchanged: bool = False,
    ) -> OverrideSummary:
        """
        Preview the changes that would be made for a target language.

        Args:
            target_language: Language code (e.g., "zh", "lt")
            include_unchanged: Whether to include words that won't change

        Returns:
            OverrideSummary with all proposed changes
        """
        if target_language not in get_supported_languages():
            raise ValueError(
                f"Language '{target_language}' not supported. "
                f"Supported: {', '.join(get_supported_languages())}"
            )

        changes: List[OverrideChange] = []
        changes_by_tier: Dict[int, int] = {
            TIER_1_LEVEL: 0,
            TIER_2_LEVEL: 0,
            TIER_3_LEVEL: 0,
        }

        # Process all countries
        countries = self._load_country_words()
        all_country_labels = set(countries.keys())

        # Also add countries from the priority config that might not be in DB yet
        for country_label in all_country_labels:
            proposed_level = get_country_level_for_language(country_label, target_language)

            if proposed_level is None:
                # Not in configuration - skip unless showing unchanged
                if not include_unchanged:
                    continue
                # Use a default "unchanged" marker
                proposed_level = -999

            # Find all related words for this country
            related_words = self._find_related_words_for_country(country_label)

            for lemma, relationship in related_words:
                # Get current state
                current_override = get_difficulty_override(self.session, lemma.id, target_language)
                current_override_level = (
                    current_override.difficulty_level if current_override else None
                )

                if proposed_level == -999:
                    # Unchanged - use default
                    proposed_level_actual = lemma.difficulty_level or 14
                else:
                    proposed_level_actual = proposed_level

                change = OverrideChange(
                    guid=lemma.guid or "",
                    word_text=lemma.lemma_text,
                    pos_subtype=lemma.pos_subtype or "",
                    country_label=country_label,
                    default_level=lemma.difficulty_level,
                    current_override=current_override_level,
                    proposed_level=proposed_level_actual,
                    reason=f"{relationship} word for {country_label}",
                )

                if change.is_change or include_unchanged:
                    changes.append(change)

                    if change.is_change and proposed_level_actual in changes_by_tier:
                        changes_by_tier[proposed_level_actual] += 1

        # Sort changes by proposed level, then by country label
        changes.sort(key=lambda c: (c.proposed_level, c.country_label, c.pos_subtype))

        return OverrideSummary(
            target_language=target_language,
            total_words_analyzed=len(self.get_all_country_related_words()),
            words_with_changes=sum(1 for c in changes if c.is_change),
            changes_by_tier=changes_by_tier,
            changes=changes,
        )

    def apply_overrides(
        self,
        target_language: str,
        dry_run: bool = False,
        notes_template: str = "Country word priority: {reason}",
    ) -> OverrideSummary:
        """
        Apply country-related overrides for a target language.

        Args:
            target_language: Language code (e.g., "zh", "lt")
            dry_run: If True, don't actually commit changes
            notes_template: Template for override notes, {reason} will be replaced

        Returns:
            OverrideSummary with applied changes
        """
        summary = self.preview_changes(target_language, include_unchanged=False)

        applied_count = 0
        for change in summary.changes:
            if not change.is_change:
                continue

            # Find the lemma
            lemma = self.session.query(Lemma).filter(Lemma.guid == change.guid).first()

            if not lemma:
                continue

            # Add/update the override
            notes = notes_template.format(reason=change.reason)
            add_difficulty_override(
                session=self.session,
                lemma_id=lemma.id,
                language_code=target_language,
                difficulty_level=change.proposed_level,
                notes=notes,
            )
            applied_count += 1

        if not dry_run:
            self.session.commit()
        else:
            self.session.rollback()

        return summary

    def apply_overrides_all_languages(
        self,
        dry_run: bool = False,
        notes_template: str = "Country word priority: {reason}",
    ) -> Dict[str, OverrideSummary]:
        """
        Apply country-related overrides for all supported languages.

        Args:
            dry_run: If True, don't actually commit changes
            notes_template: Template for override notes

        Returns:
            Dictionary mapping language code to OverrideSummary
        """
        results: Dict[str, OverrideSummary] = {}

        for lang_code in get_supported_languages():
            results[lang_code] = self.apply_overrides(
                lang_code, dry_run=dry_run, notes_template=notes_template
            )

        return results

    def get_current_overrides_for_language(
        self, target_language: str
    ) -> List[Tuple[Lemma, LemmaDifficultyOverride]]:
        """
        Get all current country-related overrides for a language.

        Args:
            target_language: Language code

        Returns:
            List of (Lemma, LemmaDifficultyOverride) tuples
        """
        results: List[Tuple[Lemma, LemmaDifficultyOverride]] = []

        for lemma in self.get_all_country_related_words():
            override = get_difficulty_override(self.session, lemma.id, target_language)
            if override:
                results.append((lemma, override))

        return results

    def clear_country_overrides_for_language(
        self,
        target_language: str,
        dry_run: bool = False,
    ) -> int:
        """
        Remove all country-related overrides for a language.

        Args:
            target_language: Language code
            dry_run: If True, don't commit changes

        Returns:
            Number of overrides removed
        """
        from wordfreq.storage.crud.difficulty_override import delete_difficulty_override

        count = 0
        for lemma in self.get_all_country_related_words():
            override = get_difficulty_override(self.session, lemma.id, target_language)
            if override:
                delete_difficulty_override(self.session, lemma.id, target_language)
                count += 1

        if not dry_run:
            self.session.commit()
        else:
            self.session.rollback()

        return count

    def format_summary_report(self, summary: OverrideSummary) -> str:
        """
        Format a summary as a human-readable report.

        Args:
            summary: OverrideSummary to format

        Returns:
            Formatted string report
        """
        lines = [
            f"Country Word Override Report for '{summary.target_language}'",
            "=" * 60,
            f"Total words analyzed: {summary.total_words_analyzed}",
            f"Words with changes: {summary.words_with_changes}",
            "",
            "Changes by tier:",
        ]

        tier_names = {
            TIER_1_LEVEL: f"Tier 1 (Level {TIER_1_LEVEL}) - Home/Neighbors/English",
            TIER_2_LEVEL: f"Tier 2 (Level {TIER_2_LEVEL}) - Major Powers",
            TIER_3_LEVEL: f"Tier 3 (Level {TIER_3_LEVEL}) - Remaining",
        }

        for level in get_all_tier_levels():
            count = summary.changes_by_tier.get(level, 0)
            tier_name = tier_names.get(level, f"Level {level}")
            lines.append(f"  {tier_name}: {count} words")

        lines.append("")
        lines.append("Detailed changes:")
        lines.append("-" * 60)

        current_level = None
        for change in summary.changes:
            if not change.is_change:
                continue

            if change.proposed_level != current_level:
                current_level = change.proposed_level
                tier_name = tier_names.get(current_level, f"Level {current_level}")
                lines.append(f"\n{tier_name}:")

            old_level = (
                change.current_override
                if change.current_override is not None
                else change.default_level
            )
            lines.append(
                f"  {change.guid:<12} {change.word_text:<20} "
                f"({change.pos_subtype:<12}) {old_level or 'N/A':>3} -> {change.proposed_level}"
            )

        return "\n".join(lines)
