#!/usr/bin/env python3
"""
Manager for applying family relation word difficulty level overrides.

This module provides the business logic for:
1. Finding family relation words in the database
2. Applying language-specific exclusion overrides based on priority configuration
3. Generating preview reports of proposed changes
4. Bulk applying overrides to the database

Usage:
    from wordfreq.tools.family_relation_override_manager import FamilyRelationOverrideManager
    from storage.backend.factory import create_session
    from storage.backend.config import DataSourceConfig, BackendType

    config = DataSourceConfig(backend_type=BackendType.SQLITE)
    session = create_session(config)
    manager = FamilyRelationOverrideManager(session)

    # Preview changes for Chinese learners
    summary = manager.preview_changes("zh")

    # Apply changes
    manager.apply_overrides("zh")
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from sqlalchemy.orm import Session

from storage.crud.difficulty_override import (
    add_difficulty_override,
    delete_difficulty_override,
    get_difficulty_override,
)
from storage.models.schema import Lemma, LemmaDifficultyOverride
from wordfreq.tools.family_relation_priorities import (
    ALL_FAMILY_RELATIONS,
    get_excluded_terms_for_language,
    get_included_terms_for_language,
    get_supported_languages,
    is_term_excluded_for_language,
)

# Difficulty level used for excluded/null terms
EXCLUDED_DIFFICULTY_LEVEL = -1


@dataclass
class OverrideChange:
    """Represents a proposed or applied override change."""

    guid: str
    word_text: str
    concept_label: str
    default_level: Optional[int]
    current_override: Optional[int]
    proposed_level: int
    reason: str

    @property
    def is_change(self) -> bool:
        """Whether this represents an actual change."""
        if self.current_override is not None:
            return self.current_override != self.proposed_level
        # If there's no current override, check if we need to add one
        # (i.e., if the default level differs from proposed)
        return True  # Always a change if adding exclusion override

    @property
    def is_exclusion(self) -> bool:
        """Whether this change is an exclusion (null) override."""
        return self.proposed_level == EXCLUDED_DIFFICULTY_LEVEL


@dataclass
class OverrideSummary:
    """Summary of override changes for a language."""

    target_language: str
    total_words_analyzed: int
    words_to_exclude: int
    words_to_include: int
    changes: List[OverrideChange]


class FamilyRelationOverrideManager:
    """
    Manager for family relation word difficulty overrides.

    This class handles finding family relation words and applying
    language-specific exclusion overrides for terms that don't
    map naturally to the target language.
    """

    POS_SUBTYPE = "family_relation"

    def __init__(self, session: Session):
        """
        Initialize the manager.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self._family_relation_words: Optional[Dict[str, List[Lemma]]] = None

    def _load_family_relation_words(self) -> Dict[str, List[Lemma]]:
        """
        Load all family relation words from the database.

        Returns:
            Dictionary mapping concept_label to list of Lemma objects
        """
        if self._family_relation_words is not None:
            return self._family_relation_words

        self._family_relation_words = {}

        lemmas = (
            self.session.query(Lemma)
            .filter(
                Lemma.pos_type == "noun",
                Lemma.pos_subtype == self.POS_SUBTYPE,
            )
            .all()
        )

        for lemma in lemmas:
            label = lemma.lemma_text
            if label not in self._family_relation_words:
                self._family_relation_words[label] = []
            self._family_relation_words[label].append(lemma)

        return self._family_relation_words

    def get_all_family_relation_words(self) -> List[Lemma]:
        """
        Get all family relation words.

        Returns:
            List of Lemma objects
        """
        words = self._load_family_relation_words()
        all_words: List[Lemma] = []
        for lemmas in words.values():
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
        changes: List[OverrideChange] = []
        words_to_exclude = 0
        words_to_include = 0

        # Get all family relation words from database
        family_words = self._load_family_relation_words()

        for concept_label, lemmas in family_words.items():
            # Check if this term should be excluded for the language
            should_exclude = is_term_excluded_for_language(concept_label, target_language)

            for lemma in lemmas:
                # Get current override state
                current_override = get_difficulty_override(self.session, lemma.id, target_language)
                current_override_level = (
                    current_override.difficulty_level if current_override else None
                )

                if should_exclude:
                    proposed_level = EXCLUDED_DIFFICULTY_LEVEL
                    reason = f"Term '{concept_label}' is awkward/doesn't exist in {target_language}"
                    words_to_exclude += 1

                    # Only add to changes if it's actually changing something
                    if current_override_level != proposed_level:
                        change = OverrideChange(
                            guid=lemma.guid or "",
                            word_text=lemma.lemma_text,
                            concept_label=concept_label,
                            default_level=lemma.difficulty_level,
                            current_override=current_override_level,
                            proposed_level=proposed_level,
                            reason=reason,
                        )
                        changes.append(change)
                    elif include_unchanged:
                        change = OverrideChange(
                            guid=lemma.guid or "",
                            word_text=lemma.lemma_text,
                            concept_label=concept_label,
                            default_level=lemma.difficulty_level,
                            current_override=current_override_level,
                            proposed_level=proposed_level,
                            reason=reason + " (already excluded)",
                        )
                        changes.append(change)
                else:
                    words_to_include += 1
                    # If currently excluded but shouldn't be, we need to remove the override
                    if current_override_level == EXCLUDED_DIFFICULTY_LEVEL:
                        change = OverrideChange(
                            guid=lemma.guid or "",
                            word_text=lemma.lemma_text,
                            concept_label=concept_label,
                            default_level=lemma.difficulty_level,
                            current_override=current_override_level,
                            proposed_level=lemma.difficulty_level or 0,  # Restore default
                            reason=f"Term '{concept_label}' should be included in {target_language}",
                        )
                        changes.append(change)
                    elif include_unchanged:
                        change = OverrideChange(
                            guid=lemma.guid or "",
                            word_text=lemma.lemma_text,
                            concept_label=concept_label,
                            default_level=lemma.difficulty_level,
                            current_override=current_override_level,
                            proposed_level=lemma.difficulty_level or 0,
                            reason=f"Term '{concept_label}' included in {target_language} (no change)",
                        )
                        changes.append(change)

        # Sort changes by concept_label, then by exclusion status
        changes.sort(key=lambda c: (not c.is_exclusion, c.concept_label, c.word_text))

        return OverrideSummary(
            target_language=target_language,
            total_words_analyzed=len(self.get_all_family_relation_words()),
            words_to_exclude=words_to_exclude,
            words_to_include=words_to_include,
            changes=changes,
        )

    def apply_overrides(
        self,
        target_language: str,
        dry_run: bool = False,
        notes_template: str = "Family relation: {reason}",
    ) -> OverrideSummary:
        """
        Apply family relation overrides for a target language.

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
            # Find the lemma
            lemma = self.session.query(Lemma).filter(Lemma.guid == change.guid).first()

            if not lemma:
                continue

            if change.is_exclusion:
                # Add/update exclusion override
                notes = notes_template.format(reason=change.reason)
                add_difficulty_override(
                    session=self.session,
                    lemma_id=lemma.id,
                    language_code=target_language,
                    difficulty_level=EXCLUDED_DIFFICULTY_LEVEL,
                    notes=notes,
                )
                applied_count += 1
            else:
                # Remove exclusion override (restore to default)
                existing = get_difficulty_override(self.session, lemma.id, target_language)
                if existing and existing.difficulty_level == EXCLUDED_DIFFICULTY_LEVEL:
                    delete_difficulty_override(self.session, lemma.id, target_language)
                    applied_count += 1

        if not dry_run:
            self.session.commit()
        else:
            self.session.rollback()

        return summary

    def apply_overrides_all_languages(
        self,
        dry_run: bool = False,
        notes_template: str = "Family relation: {reason}",
    ) -> Dict[str, OverrideSummary]:
        """
        Apply family relation overrides for all supported languages.

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
        Get all current family relation overrides for a language.

        Args:
            target_language: Language code

        Returns:
            List of (Lemma, LemmaDifficultyOverride) tuples
        """
        results: List[Tuple[Lemma, LemmaDifficultyOverride]] = []

        for lemma in self.get_all_family_relation_words():
            override = get_difficulty_override(self.session, lemma.id, target_language)
            if override:
                results.append((lemma, override))

        return results

    def clear_family_relation_overrides_for_language(
        self,
        target_language: str,
        dry_run: bool = False,
    ) -> int:
        """
        Remove all family relation overrides for a language.

        Args:
            target_language: Language code
            dry_run: If True, don't commit changes

        Returns:
            Number of overrides removed
        """
        count = 0
        for lemma in self.get_all_family_relation_words():
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
            f"Family Relation Override Report for '{summary.target_language}'",
            "=" * 60,
            f"Total words analyzed: {summary.total_words_analyzed}",
            f"Words to exclude (null): {summary.words_to_exclude}",
            f"Words to include: {summary.words_to_include}",
            f"Changes to apply: {len(summary.changes)}",
            "",
        ]

        if summary.changes:
            # Group by exclusion status
            exclusions = [c for c in summary.changes if c.is_exclusion]
            inclusions = [c for c in summary.changes if not c.is_exclusion]

            if exclusions:
                lines.append("Terms to EXCLUDE (set to null/-1):")
                lines.append("-" * 40)
                for change in exclusions:
                    old_level = (
                        change.current_override
                        if change.current_override is not None
                        else change.default_level
                    )
                    lines.append(
                        f"  {change.guid:<12} {change.concept_label:<25} "
                        f"{old_level or 'N/A':>3} -> {change.proposed_level}"
                    )
                lines.append("")

            if inclusions:
                lines.append("Terms to INCLUDE (remove exclusion):")
                lines.append("-" * 40)
                for change in inclusions:
                    lines.append(
                        f"  {change.guid:<12} {change.concept_label:<25} "
                        f"{change.current_override or 'N/A':>3} -> (default)"
                    )
        else:
            lines.append("No changes needed.")

        return "\n".join(lines)
