#!/usr/bin/env python3
"""
Export manager for trakaido data.

Provides the TrakaidoExporter class for exporting trakaido data
in various formats (JSON, WireWord).

For WireWord format exports, see wireword/export_wireword.py
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import constants
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import create_session
from storage.models.schema import Lemma, WordToken
from storage.crud.difficulty_override import bulk_get_effective_difficulty_levels
from storage.translation_helpers import (
    LANG_CODE_TO_LLM_FIELD,
    LANGUAGE_FIELDS,
    TIER_1_LANGUAGES,
    TIER_2_LANGUAGES,
    bulk_get_translations,
    get_translation,
)
from langtools.zh.converter import to_simplified

from .data_models import ExportStats, create_export_stats
from .text_rendering import format_subtype_display_name

# Configure logging
logger = logging.getLogger(__name__)


class TrakaidoExporter:
    """Main class for exporting trakaido data in various formats."""

    # Language configuration mapping - generated from tier 1 and tier 2 languages
    LANGUAGE_CONFIG = {
        lang_code: {
            "name": LANGUAGE_FIELDS[lang_code][1],  # Display name
            "field": LANG_CODE_TO_LLM_FIELD[lang_code],  # LLM field name
        }
        for lang_code in TIER_1_LANGUAGES + TIER_2_LANGUAGES
    }

    def __init__(
        self,
        config: Optional[DataSourceConfig] = None,
        debug: bool = False,
        language: str = "lt",
        simplified_chinese: bool = True,
        include_unreviewed_audio: bool = False,
        source_language: str = "en",
    ):
        """
        Initialize the TrakaidoExporter.

        Args:
            config: DataSourceConfig with backend settings (uses default SQLite if None)
            debug: Enable debug logging
            language: Target language code ('lt' for Lithuanian, 'zh' for Chinese)
            simplified_chinese: If True and language is 'zh', convert to Simplified Chinese (default: True)
            include_unreviewed_audio: If True, include audio that exists in staging but hasn't been
                reviewed yet. The manifest's audio_prefix will be changed to point to staging.
            source_language: Source language code (default: 'en'). The language the learner already
                knows. When not 'en', base_english is replaced with base_source in wireword output.
        """
        # Use provided config or create default SQLite config
        if config is None:
            config = DataSourceConfig(backend_type=BackendType.SQLITE)
        self.config = config
        self.debug = debug
        self.language = language
        self.simplified_chinese = simplified_chinese
        self.include_unreviewed_audio = include_unreviewed_audio
        self.source_language = source_language

        if language not in self.LANGUAGE_CONFIG:
            raise ValueError(
                f"Unsupported language: {language}. Supported: {', '.join(self.LANGUAGE_CONFIG.keys())}"
            )

        self.language_name = self.LANGUAGE_CONFIG[language]["name"]
        self.language_field = self.LANGUAGE_CONFIG[language]["field"]

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        """Get database session."""
        return create_session(self.config)

    def get_english_word_from_lemma(self, session: Any, lemma: Lemma) -> Optional[str]:
        """
        Get the primary English word for a lemma.

        Uses lemma_text directly to preserve proper capitalization
        (e.g., "Christmas", "Monday", "Lithuania").

        Args:
            session: Database session
            lemma: Lemma object

        Returns:
            English word string or None if not found
        """
        # Use lemma_text directly - it has the correct capitalization
        # Derivative forms are typically lowercase for tokenization/matching
        return lemma.lemma_text

    def query_trakaido_data(
        self,
        session: Any,
        difficulty_level: Optional[int] = None,
        pos_type: Optional[str] = None,
        pos_subtype: Optional[str] = None,
        limit: Optional[int] = None,
        include_without_guid: bool = False,
        include_unverified: bool = True,
        exclude_verbs: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Query trakaido data from the database with flexible filtering.

        Uses language-specific difficulty level overrides when available.
        Excludes lemmas with effective difficulty level of -1 for this language.

        Optimized for remote databases: uses bulk queries to minimize round trips.

        Args:
            session: Database session
            difficulty_level: Filter by specific difficulty level (optional)
            pos_type: Filter by specific POS type (optional)
            pos_subtype: Filter by specific POS subtype (optional)
            limit: Limit number of results (optional)
            include_without_guid: Include lemmas without GUIDs (default: False)
            include_unverified: Include unverified entries (default: True)
            exclude_verbs: Exclude verbs from results (default: True, for backward compatibility)

        Returns:
            List of dictionaries with trakaido data
        """
        from sqlalchemy import func

        from storage.models.schema import LemmaDifficultyOverride

        logger.info(f"Querying database for trakaido data (language: {self.language_name})...")

        # Check if language uses column (can filter in SQL) or table (filter in Python)
        _, _, use_translation_table = LANGUAGE_FIELDS[self.language]

        # Build the query
        query = session.query(Lemma)

        # Optionally exclude verbs (default behavior for backward compatibility)
        if exclude_verbs:
            query = query.filter(Lemma.pos_type != "verb")

        # For column-based translations, we can filter in SQL
        if not use_translation_table:
            language_column = getattr(Lemma, self.language_field)
            query = query.filter(language_column != None).filter(language_column != "")

        # Apply filters
        if not include_without_guid:
            query = query.filter(Lemma.guid != None)

        if not include_unverified:
            query = query.filter(Lemma.verified == True)

        # Handle difficulty level filtering with language-specific overrides
        if difficulty_level is not None:
            # Left join with overrides to get language-specific levels
            query = query.outerjoin(
                LemmaDifficultyOverride,
                (LemmaDifficultyOverride.lemma_id == Lemma.id)
                & (LemmaDifficultyOverride.language_code == self.language),
            )
            # Use override if exists, otherwise use default
            # COALESCE returns first non-null value
            effective_level = func.coalesce(
                LemmaDifficultyOverride.difficulty_level, Lemma.difficulty_level
            )
            query = query.filter(effective_level == difficulty_level)
            logger.info(
                f"Filtering by effective difficulty level: {difficulty_level} for language: {self.language}"
            )

        if pos_type:
            query = query.filter(Lemma.pos_type == pos_type.lower())
            logger.info(f"Filtering by POS type: {pos_type}")

        if pos_subtype:
            query = query.filter(Lemma.pos_subtype == pos_subtype)
            logger.info(f"Filtering by POS subtype: {pos_subtype}")

        # Order by GUID for consistent output
        query = query.order_by(Lemma.guid.asc().nullslast())

        if limit:
            query = query.limit(limit)
            logger.info(f"Limiting results to: {limit}")

        all_lemmas = query.all()
        logger.info(f"Found {len(all_lemmas)} lemmas matching criteria")

        # OPTIMIZATION: Bulk fetch difficulty levels and translations in two queries
        # instead of N queries per lemma
        difficulty_levels_by_id = bulk_get_effective_difficulty_levels(
            session, all_lemmas, self.language
        )
        translations_by_id = bulk_get_translations(session, all_lemmas, self.language)
        logger.info("Bulk fetched difficulty levels and translations")

        # Filter out lemmas with effective level -1 (excluded from this language)
        # This is important when difficulty_level is not specified
        if difficulty_level != -1:  # Unless we're explicitly querying for excluded items
            filtered_lemmas = []
            for lemma in all_lemmas:
                effective = difficulty_levels_by_id.get(lemma.id)
                if effective != -1:
                    filtered_lemmas.append(lemma)
            if len(filtered_lemmas) < len(all_lemmas):
                logger.info(
                    f"Filtered out {len(all_lemmas) - len(filtered_lemmas)} lemmas with level -1 (excluded from {self.language})"
                )
            all_lemmas = filtered_lemmas

        # For table-based translations, filter by translation availability using pre-fetched data
        if use_translation_table:
            lemmas = []
            for lemma in all_lemmas:
                translation = translations_by_id.get(lemma.id)
                if translation and translation.strip():
                    lemmas.append(lemma)
                if limit and len(lemmas) >= limit:
                    break
            logger.info(f"Filtered to {len(lemmas)} lemmas with {self.language_name} translations")
        else:
            lemmas = all_lemmas

        # Convert to export format using pre-fetched data
        export_data = []
        skipped_count = 0

        for lemma in lemmas:
            # Get the English word
            english_word = self.get_english_word_from_lemma(session, lemma)

            if not english_word:
                logger.warning(
                    f"No English word found for lemma ID {lemma.id} (GUID: {lemma.guid})"
                )
                skipped_count += 1
                continue

            # Get the target language translation from pre-fetched data
            target_translation = translations_by_id.get(lemma.id)

            # For Chinese, optionally convert to simplified
            if self.language == "zh" and self.simplified_chinese and target_translation:
                target_translation = to_simplified(target_translation)

            # Create the export entry with standardized key names
            entry = {
                "English": english_word,
                "Target": target_translation,  # Use "Target" instead of language-specific name
                "GUID": lemma.guid or "",
                "trakaido_level": lemma.difficulty_level or 1,
                "POS": lemma.pos_type or "noun",
                "subtype": lemma.pos_subtype or "other",
            }

            export_data.append(entry)

        if skipped_count > 0:
            logger.warning(f"Skipped {skipped_count} lemmas without English words")

        # Sort the data by trakaido_level, then POS, then subtype, then English alphabetically
        logger.info("Sorting export data...")
        export_data.sort(
            key=lambda x: (
                x.get("trakaido_level", 999),  # Sort by level first
                x.get("POS", "zzz"),  # Then by POS
                x.get("subtype", "zzz"),  # Then by subtype
                str(x.get("English", "")).lower(),  # Finally by English word alphabetically
            )
        )

        logger.info(f"Successfully prepared {len(export_data)} entries for export")
        return export_data

    def write_json_file(
        self, data: List[Dict[str, Any]], output_path: str, pretty_print: bool = True
    ) -> ExportStats:
        """
        Write the export data to a JSON file.

        Args:
            data: List of dictionaries to export
            output_path: Path to write the JSON file
            pretty_print: Whether to format JSON with indentation

        Returns:
            ExportStats object with export statistics
        """
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                if pretty_print:
                    # Write with nice formatting, one entry per line
                    f.write("[\n")
                    for i, entry in enumerate(data):
                        line = json.dumps(entry, ensure_ascii=False, separators=(", ", ": "))
                        if i < len(data) - 1:
                            f.write(f"  {line},\n")
                        else:
                            f.write(f"  {line}\n")
                    f.write("]\n")
                else:
                    # Compact format
                    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

            # Calculate statistics
            stats = create_export_stats(data)

            logger.info(f"Successfully wrote {len(data)} entries to {output_path}")
            logger.info(f"Entries with GUIDs: {stats.entries_with_guids}/{stats.total_entries}")
            logger.info(f"POS distribution: {stats.pos_distribution}")
            logger.info(f"Level distribution: {stats.level_distribution}")

            return stats

        except Exception as e:
            logger.error(f"Failed to write JSON file: {e}")
            raise

    def export_to_json(
        self,
        output_path: str,
        difficulty_level: Optional[int] = None,
        pos_type: Optional[str] = None,
        pos_subtype: Optional[str] = None,
        limit: Optional[int] = None,
        include_without_guid: bool = False,
        include_unverified: bool = True,
        pretty_print: bool = True,
    ) -> Tuple[bool, Optional[ExportStats]]:
        """
        Export trakaido data to JSON format.

        Args:
            output_path: Path to write the JSON file
            difficulty_level: Filter by specific difficulty level (optional)
            pos_type: Filter by specific POS type (optional)
            pos_subtype: Filter by specific POS subtype (optional)
            limit: Limit number of results (optional)
            include_without_guid: Include lemmas without GUIDs (default: False)
            include_unverified: Include unverified entries (default: True)
            pretty_print: Whether to format JSON with indentation (default: True)

        Returns:
            Tuple of (success flag, export statistics)
        """
        session = self.get_session()
        try:
            # Query the data
            export_data = self.query_trakaido_data(
                session=session,
                difficulty_level=difficulty_level,
                pos_type=pos_type,
                pos_subtype=pos_subtype,
                limit=limit,
                include_without_guid=include_without_guid,
                include_unverified=include_unverified,
            )

            if not export_data:
                logger.warning("No data found matching the specified criteria")
                return False, None

            # Write to JSON file
            stats = self.write_json_file(export_data, output_path, pretty_print)

            return True, stats

        except Exception as e:
            logger.error(f"Export to JSON failed: {e}")
            return False, None
        finally:
            session.close()

    def export_to_wireword_format(
        self, output_path: str, **kwargs: Any
    ) -> Tuple[bool, Optional[ExportStats]]:
        """Delegate to WirewordExporter. See wireword/export_wireword.py for details."""
        from wireword.export_wireword import WirewordExporter

        exporter = WirewordExporter(
            config=self.config,
            debug=self.debug,
            language=self.language,
            simplified_chinese=self.simplified_chinese,
            include_unreviewed_audio=self.include_unreviewed_audio,
            source_language=self.source_language,
        )
        return exporter.export_to_wireword_format(output_path, **kwargs)

    def export_wireword_directory(self, output_dir: str) -> Tuple[bool, Dict[str, Any]]:
        """Delegate to WirewordExporter. See wireword/export_wireword.py for details."""
        from wireword.export_wireword import WirewordExporter

        exporter = WirewordExporter(
            config=self.config,
            debug=self.debug,
            language=self.language,
            simplified_chinese=self.simplified_chinese,
            include_unreviewed_audio=self.include_unreviewed_audio,
            source_language=self.source_language,
        )
        return exporter.export_wireword_directory(output_dir)

    def export_verbs_to_wireword_format(
        self, output_path: str, **kwargs: Any
    ) -> Tuple[bool, Optional[ExportStats]]:
        """Delegate to WirewordExporter. See wireword/export_wireword.py for details."""
        from wireword.export_wireword import WirewordExporter

        exporter = WirewordExporter(
            config=self.config,
            debug=self.debug,
            language=self.language,
            simplified_chinese=self.simplified_chinese,
            include_unreviewed_audio=self.include_unreviewed_audio,
            source_language=self.source_language,
        )
        return exporter.export_verbs_to_wireword_format(output_path, **kwargs)
