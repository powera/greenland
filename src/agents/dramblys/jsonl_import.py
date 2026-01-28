#!/usr/bin/env python3
"""
JSONL Import Module for DRAMBLYS

Handles importing lemmas from JSONL files with intelligent GUID collision handling
and category migration support.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union, cast

from wordfreq.storage.models.schema import Lemma, LemmaTranslation
from wordfreq.storage.translation_helpers import LANGUAGE_FIELDS

logger = logging.getLogger(__name__)


class CategoryMigration:
    """Handles category migration mappings."""

    def __init__(self, migration_file: str):
        """
        Initialize category migration from JSON file.

        Args:
            migration_file: Path to the category migrations JSON file
        """
        self.migration_file = migration_file
        self.splits: Dict[str, Any] = {}
        self.renames: Dict[str, str] = {}
        self.guid_overrides: Dict[str, Any] = {}
        self.import_rules: Dict[str, Any] = {}

        self._load_migrations()

    def _load_migrations(self) -> None:
        """Load migration configuration from file."""
        try:
            with open(self.migration_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            self.splits = config.get("category_splits", {})
            self.renames = config.get("category_renames", {})
            self.guid_overrides = config.get("guid_overrides", {})
            self.import_rules = config.get("import_rules", {})

            logger.info(
                f"Loaded migration config: {len(self.splits)} splits, "
                f"{len(self.renames)} renames, {len(self.guid_overrides)} GUID overrides"
            )

        except Exception as e:
            logger.warning(f"Could not load migration file {self.migration_file}: {e}")
            logger.warning("Proceeding without migration mappings")

    def should_import_guid(self, guid: str, jsonl_data: Dict) -> Tuple[bool, Optional[str]]:
        """
        Check if a GUID should be imported based on overrides.

        Args:
            guid: The GUID to check
            jsonl_data: The JSONL data for this GUID

        Returns:
            Tuple of (should_import, reason)
        """
        if guid in self.guid_overrides:
            override = self.guid_overrides[guid]
            action = override.get("action", "skip")
            reason = override.get("reason", "No reason provided")

            if action == "skip":
                return False, f"Skipped per override: {reason}"
            elif action == "manual_review":
                return False, f"Requires manual review: {reason}"
            # prefer_jsonl and prefer_db are handled by collision logic

        return True, None

    def get_category_targets(self, old_category: str) -> Optional[List[str]]:
        """
        Get target categories for a split category.

        Args:
            old_category: Original category name

        Returns:
            List of target categories if this is a split, None otherwise
        """
        if old_category in self.splits:
            result: List[str] = self.splits[old_category].get("split_into", [])
            return result
        return None

    def resolve_category(self, old_category: str) -> str:
        """
        Resolve category through renames.

        Args:
            old_category: Original category name

        Returns:
            Resolved category name
        """
        return self.renames.get(old_category, old_category)


class JSONLImporter:
    """Handles importing lemmas from JSONL files."""

    def __init__(
        self,
        session: Any,
        migration_config: Optional[CategoryMigration] = None,
        dry_run: bool = False,
        import_level: Optional[int] = None,
    ):
        """
        Initialize JSONL importer.

        Args:
            session: Database session
            migration_config: Category migration configuration
            dry_run: If True, don't make database changes
            import_level: Optional difficulty level override for all imported lemmas
        """
        self.session = session
        self.migration = migration_config
        self.dry_run = dry_run
        self.import_level = import_level

        # Statistics
        self.stats: Dict[str, Any] = {
            "files_processed": 0,
            "records_read": 0,
            "records_imported": 0,
            "records_skipped": 0,
            "guid_collisions": 0,
            "errors": 0,
            "error_details": [],
        }

    def read_jsonl_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Read a JSONL file and return list of records.

        Args:
            file_path: Path to JSONL file

        Returns:
            List of parsed JSON records
        """
        records = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        records.append(data)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parse error in {file_path}:{line_num}: {e}")
                        self.stats["errors"] += 1
                        self.stats["error_details"].append(
                            {"file": str(file_path), "line": line_num, "error": str(e)}
                        )

            logger.info(f"Read {len(records)} records from {file_path}")
            return records

        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            self.stats["errors"] += 1
            self.stats["error_details"].append({"file": str(file_path), "error": str(e)})
            return []

    def find_existing_lemma(self, guid: str) -> Optional[Lemma]:
        """
        Find existing lemma by GUID.

        Args:
            guid: The GUID to search for

        Returns:
            Existing lemma or None
        """
        result: Optional[Lemma] = self.session.query(Lemma).filter(Lemma.guid == guid).first()
        return result

    def check_category_coherence(
        self, existing: Lemma, jsonl_data: Dict
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if JSONL data matches existing lemma's category.

        Args:
            existing: Existing lemma from database
            jsonl_data: JSONL data to import

        Returns:
            Tuple of (is_coherent, reason_if_not)
        """
        existing_pos = existing.pos_type
        existing_sub = existing.pos_subtype or ""
        jsonl_pos = jsonl_data.get("pos_type", "")
        jsonl_sub = jsonl_data.get("pos_subtype", "")

        # Exact match is always coherent
        if existing_pos == jsonl_pos and existing_sub == jsonl_sub:
            return True, None

        # Check if this is a known split
        if self.migration:
            targets = self.migration.get_category_targets(existing_sub)
            if targets and jsonl_sub in targets:
                return True, f"Category split: {existing_sub} → {jsonl_sub}"

        # Category mismatch
        return (
            False,
            f"Category mismatch: DB has {existing_pos}/{existing_sub}, JSONL has {jsonl_pos}/{jsonl_sub}",
        )

    def get_field_differences(self, existing: Lemma, jsonl_data: Dict) -> List[str]:
        """
        Get list of differences between existing lemma and JSONL data.

        Args:
            existing: Existing lemma from database
            jsonl_data: JSONL data to import

        Returns:
            List of difference descriptions
        """
        diffs = []

        # Compare lemma_text (from translations['en'] or concept_label)
        translations = jsonl_data.get("translations", {})
        jsonl_label = translations.get("en", jsonl_data.get("concept_label", ""))
        if existing.lemma_text != jsonl_label:
            diffs.append(f"lemma_text: '{existing.lemma_text}' → '{jsonl_label}'")

        # Compare concept_definition (definition_text)
        jsonl_def = jsonl_data.get("concept_definition", "")
        if existing.definition_text != jsonl_def:
            # Truncate long definitions for display
            existing_def_short = (
                existing.definition_text[:60] + "..."
                if len(existing.definition_text) > 60
                else existing.definition_text
            )
            jsonl_def_short = jsonl_def[:60] + "..." if len(jsonl_def) > 60 else jsonl_def
            diffs.append(f"definition: '{existing_def_short}' → '{jsonl_def_short}'")

        # Compare difficulty_level
        jsonl_level = jsonl_data.get("difficulty_level")
        if existing.difficulty_level != jsonl_level:
            diffs.append(f"difficulty_level: {existing.difficulty_level} → {jsonl_level}")

        # Compare pos_type/subtype
        jsonl_pos = jsonl_data.get("pos_type", "")
        jsonl_sub = jsonl_data.get("pos_subtype", "")
        if existing.pos_type != jsonl_pos or existing.pos_subtype != jsonl_sub:
            diffs.append(
                f"category: {existing.pos_type}/{existing.pos_subtype} → {jsonl_pos}/{jsonl_sub}"
            )

        return diffs

    def should_prefer_jsonl(self, existing: Lemma, jsonl_data: Dict, guid: str) -> Tuple[bool, str]:
        """
        Determine whether to prefer JSONL data over existing DB entry.

        Args:
            existing: Existing lemma from database
            jsonl_data: JSONL data to import
            guid: The GUID

        Returns:
            Tuple of (prefer_jsonl, reason)
        """
        # Check GUID overrides first
        if self.migration and guid in self.migration.guid_overrides:
            override = self.migration.guid_overrides[guid]
            action = override.get("action", "skip")
            if action == "prefer_jsonl":
                return True, f"Override: {override.get('reason', 'prefer JSONL')}"
            elif action == "prefer_db":
                return False, f"Override: {override.get('reason', 'prefer DB')}"

        # Apply default rule
        if self.migration:
            default_rule = self.migration.import_rules.get("on_guid_collision", "prefer_jsonl")
        else:
            default_rule = "prefer_jsonl"

        if default_rule == "prefer_jsonl":
            return True, "Default rule: prefer JSONL"
        elif default_rule == "prefer_db":
            return False, "Default rule: prefer DB"
        elif default_rule == "prefer_newer":
            # Compare timestamps if available
            jsonl_notes = jsonl_data.get("notes", "")
            # Try to extract date from notes like "[2025-08-30 15:55]"
            # For now, default to JSONL
            return True, "Default rule: prefer newer (using JSONL)"
        elif default_rule == "skip":
            return False, "Default rule: skip on collision"
        else:
            return True, "Default rule: prefer JSONL"

    def create_lemma_from_jsonl(self, jsonl_data: Dict) -> Lemma:
        """
        Create a Lemma object from JSONL data.

        Args:
            jsonl_data: JSONL record (from base.jsonl which now includes translations)

        Returns:
            Lemma object
        """
        lemma = Lemma()
        lemma.guid = jsonl_data.get("guid")
        lemma.pos_type = jsonl_data.get("pos_type", "")
        lemma.pos_subtype = jsonl_data.get("pos_subtype")

        # Get translations dict (new format stores translations in base.jsonl)
        translations = jsonl_data.get("translations", {})

        # Use English translation for lemma_text, falling back to concept_label
        concept_label = jsonl_data.get("concept_label", "")
        lemma.lemma_text = translations.get("en", concept_label)

        # Use concept_definition for definition_text
        concept_definition = jsonl_data.get("concept_definition", "")
        lemma.definition_text = concept_definition

        # Use import_level override if provided, otherwise use JSONL data
        if self.import_level is not None:
            lemma.difficulty_level = self.import_level
        else:
            lemma.difficulty_level = jsonl_data.get("difficulty_level")

        lemma.notes = jsonl_data.get("notes")

        return lemma

    def import_translations_for_lemma(self, lemma: Lemma, translations: Dict[str, str]) -> int:
        """
        Import translations for a lemma from JSONL data.

        Args:
            lemma: The Lemma object to add translations to
            translations: Dictionary of language_code -> translation_text

        Returns:
            Number of translations imported
        """
        if not translations or self.dry_run:
            return 0

        imported_count = 0
        for lang_code, translation_text in translations.items():
            # Skip English (stored as lemma_text, not in LemmaTranslation)
            if lang_code == "en":
                continue

            # Skip empty translations
            if not translation_text or not translation_text.strip():
                continue

            # Check if this is a supported language code
            if lang_code not in LANGUAGE_FIELDS:
                logger.debug(f"  Skipping unsupported language code: {lang_code}")
                continue

            # Check if translation already exists
            existing = (
                self.session.query(LemmaTranslation)
                .filter(
                    LemmaTranslation.lemma_id == lemma.id,
                    LemmaTranslation.language_code == lang_code,
                )
                .first()
            )

            if existing:
                # Update only if translation differs
                if existing.translation != translation_text:
                    existing.translation = translation_text
                    imported_count += 1
                    logger.debug(f"  Updated {lang_code} translation: {translation_text}")
            else:
                # Create new translation
                translation_obj = LemmaTranslation(
                    lemma_id=lemma.id,
                    language_code=lang_code,
                    translation=translation_text,
                    verified=False,
                )
                self.session.add(translation_obj)
                imported_count += 1
                logger.debug(f"  Added {lang_code} translation: {translation_text}")

        return imported_count

    def update_lemma_from_jsonl(self, lemma: Lemma, jsonl_data: Dict[str, Any]) -> None:
        """
        Update existing lemma with JSONL data.

        Args:
            lemma: Existing lemma to update
            jsonl_data: JSONL data
        """
        # Update fields
        concept_label = jsonl_data.get("concept_label", "")
        concept_definition = jsonl_data.get("concept_definition", "")

        lemma.lemma_text = concept_label
        lemma.definition_text = concept_definition
        lemma.difficulty_level = jsonl_data.get("difficulty_level")

        # Append to notes if different
        new_notes = jsonl_data.get("notes", "")
        if new_notes:
            if lemma.notes:
                lemma.notes = f"{lemma.notes}\n{new_notes}"
            else:
                lemma.notes = new_notes

        lemma.updated_at = datetime.now()

    def import_record(self, jsonl_data: Dict) -> Tuple[bool, str]:
        """
        Import a single JSONL record.

        Simple logic:
        - If GUID exists and lemma_text matches: skip (already exists)
        - If GUID exists but lemma_text differs: error (collision)
        - If GUID is new: import it

        Args:
            jsonl_data: JSONL record to import

        Returns:
            Tuple of (success, message)
        """
        guid = jsonl_data.get("guid")
        if not guid:
            return False, "Missing GUID"

        # Get lemma text for logging (prefer translations['en'], fall back to concept_label)
        translations = jsonl_data.get("translations", {})
        lemma_text = translations.get("en", jsonl_data.get("concept_label", ""))

        # Check for existing lemma
        existing = self.find_existing_lemma(guid)

        if existing:
            # GUID exists - check if lemma_text matches
            if existing.lemma_text == lemma_text:
                # Same word, already exists - but still update/add translations
                if not self.dry_run:
                    translations_imported = self.import_translations_for_lemma(
                        existing, translations
                    )
                    if translations_imported > 0:
                        self.session.commit()
                        logger.info(
                            f"  UPDATE: '{lemma_text}' [{guid}] - Added {translations_imported} translations"
                        )
                        self.stats["records_imported"] += 1
                        return True, f"Added {translations_imported} translations"

                self.stats["records_skipped"] += 1
                logger.debug(f"  SKIP: '{lemma_text}' [{guid}] - Already exists")
                return False, "Already exists"
            else:
                # Same GUID but different lemma_text - collision error
                error_msg = (
                    f"GUID collision: '{existing.lemma_text}' in DB vs '{lemma_text}' in JSONL"
                )
                self.stats["errors"] += 1
                self.stats["guid_collisions"] += 1
                self.stats["error_details"].append(
                    {
                        "guid": guid,
                        "error": error_msg,
                        "db_lemma": existing.lemma_text,
                        "jsonl_lemma": lemma_text,
                    }
                )
                logger.error(f"  ERROR: [{guid}] - {error_msg}")
                return False, error_msg

        else:
            # New GUID - import it
            if not self.dry_run:
                lemma = self.create_lemma_from_jsonl(jsonl_data)
                self.session.add(lemma)
                self.session.flush()  # Get lemma.id for translations

                # Import translations from JSONL
                translations_imported = self.import_translations_for_lemma(lemma, translations)
                if translations_imported > 0:
                    logger.debug(f"  Imported {translations_imported} translations")

                self.session.commit()
            self.stats["records_imported"] += 1
            logger.info(f"  NEW: '{lemma_text}' [{guid}]")
            return True, "New lemma created"

    def import_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Import all records from a JSONL file.

        Args:
            file_path: Path to JSONL file

        Returns:
            Statistics dict for this file
        """
        logger.info(f"Importing {file_path}...")

        records = self.read_jsonl_file(file_path)
        self.stats["files_processed"] += 1
        self.stats["records_read"] += len(records)

        for record in records:
            success, message = self.import_record(record)
            if not success:
                logger.debug(f"  {record.get('guid')}: {message}")
            else:
                logger.debug(f"  {record.get('guid')}: {message}")

        return {
            "file": str(file_path),
            "records": len(records),
        }

    def import_directory(self, directory: Path, pattern: str = "**/*base.jsonl") -> Dict[str, Any]:
        """
        Import all JSONL files from a directory.

        Args:
            directory: Base directory to search
            pattern: Glob pattern for files (default: **/*base.jsonl)

        Returns:
            Import statistics
        """
        logger.info(f"Scanning {directory} for pattern {pattern}...")

        files = list(directory.glob(pattern))
        logger.info(f"Found {len(files)} files to import")

        if not files:
            logger.warning(f"No files found matching {pattern} in {directory}")

        for file_path in sorted(files):
            try:
                self.import_file(file_path)
            except Exception as e:
                logger.error(f"Error importing {file_path}: {e}")
                self.stats["errors"] += 1
                self.stats["error_details"].append({"file": str(file_path), "error": str(e)})

        return self.stats

    def get_summary(self) -> str:
        """Get a human-readable summary of import results."""
        lines = [
            "\n" + "=" * 80,
            "JSONL IMPORT SUMMARY",
            "=" * 80,
            f"Files processed: {self.stats['files_processed']}",
            f"Records read: {self.stats['records_read']}",
            f"Records imported (new): {self.stats['records_imported']}",
            f"Records skipped (already exist): {self.stats['records_skipped']}",
            f"Errors: {self.stats['errors']}",
        ]

        if self.stats["error_details"]:
            lines.append(f"\nErrors:")
            for detail in self.stats["error_details"][:10]:
                if "guid" in detail:
                    # GUID collision error
                    lines.append(f"  [{detail['guid']}]: {detail['error']}")
                    if "db_lemma" in detail and "jsonl_lemma" in detail:
                        lines.append(f"    DB: '{detail['db_lemma']}'")
                        lines.append(f"    JSONL: '{detail['jsonl_lemma']}'")
                else:
                    # File/parsing error
                    lines.append(f"  {detail.get('file', 'unknown')}: {detail['error']}")

        lines.append("=" * 80)
        if self.dry_run:
            lines.append("[DRY RUN MODE - No changes will be committed]")
            lines.append("=" * 80)

        return "\n".join(lines)
