#!/usr/bin/env python3
"""
Ungurys - WireWord Export Agent

This agent runs autonomously to export word data to WireWord API format.
It replaces the legacy "export wireword" functionality from trakaido/utils.py.

"Ungurys" means "eel" in Lithuanian - swimming data downstream to external systems!
"""

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend.config import BackendType, DataSourceConfig
from storage.translation_helpers import (
    LANGUAGE_NAMES,
    TIER_1_LANGUAGES,
    TIER_2_LANGUAGES,
)
from storage.backend.factory import create_session
from wireword.export_manager import TrakaidoExporter
from wordfreq.tools.country_word_priorities import (
    get_supported_languages as get_country_override_languages,
)
from wordfreq.tools.family_relation_priorities import (
    get_supported_languages as get_family_override_languages,
)
from wireword.export_wireword_conversations import WirewordConversationExporter
from wireword.export_wireword_sentences import WirewordSentenceExporter

# Supported languages: Tier 1 and Tier 2 (excludes experimental tier 3)
SUPPORTED_LANGUAGES = {
    lang_code: LANGUAGE_NAMES[lang_code] for lang_code in TIER_1_LANGUAGES + TIER_2_LANGUAGES
}

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class UngurysAgent:
    """Agent for exporting word data to WireWord format."""

    def __init__(
        self,
        config: DataSourceConfig,
        language: str = "lt",
        simplified_chinese: bool = True,
        include_unreviewed_audio: bool = False,
        source_language: str = "en",
    ):
        """
        Initialize the Ungurys agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
            language: Language code ('lt' for Lithuanian, 'zh' for Chinese, 'zh-Hant' for Traditional Chinese)
            simplified_chinese: For 'zh', whether to convert to Simplified (default: True)
            include_unreviewed_audio: If True, include audio that exists in staging but hasn't been
                reviewed yet. The manifest's audio_prefix will be changed to point to staging.
            source_language: Source language code (default: 'en'). The language the learner already
                knows. When not 'en', output uses base_source instead of base_english, and output
                directory uses a _from_{source} suffix (e.g. lang_lt_from_uk/).
        """
        self.config = config
        self.debug = config.debug
        self.simplified_chinese = simplified_chinese
        self.include_unreviewed_audio = include_unreviewed_audio
        self.source_language = source_language

        # Handle language variants
        if language == "zh-Hant":
            self.language = "zh"
            self.simplified_chinese = False
            self.language_suffix = "zh_Hant"
        elif language == "zh" and not self.simplified_chinese:
            # Traditional Chinese passed as language="zh" with simplified_chinese=False
            self.language = "zh"
            self.language_suffix = "zh_Hant"
        else:
            self.language = language
            self.language_suffix = language

        # Append source language suffix for non-English source languages
        if self.source_language != "en":
            self.language_suffix = f"{self.language_suffix}_from_{self.source_language}"

        if self.debug:
            logger.setLevel(logging.DEBUG)

        # Validate language
        if self.language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language: {self.language}. Supported: {', '.join(SUPPORTED_LANGUAGES.keys())}"
            )

        # Initialize exporter with language parameter and Chinese variant
        # Pass config directly so exporters use correct backend (SQLite or PostgreSQL)
        self.exporter = TrakaidoExporter(
            config=config,
            debug=self.debug,
            language=self.language,
            simplified_chinese=self.simplified_chinese if self.language == "zh" else True,
            include_unreviewed_audio=self.include_unreviewed_audio,
            source_language=self.source_language,
        )

        # Initialize sentence exporter with Chinese variant support
        self.sentence_exporter = WirewordSentenceExporter(
            config=config,
            debug=self.debug,
            language=self.language,
            simplified_chinese=self.simplified_chinese if self.language == "zh" else True,
            include_unreviewed_audio=self.include_unreviewed_audio,
            source_language=self.source_language,
        )

        # Initialize conversation exporter with Chinese variant support
        self.conversation_exporter = WirewordConversationExporter(
            config=config,
            debug=self.debug,
            language=self.language,
            simplified_chinese=self.simplified_chinese if self.language == "zh" else True,
            include_unreviewed_audio=self.include_unreviewed_audio,
            source_language=self.source_language,
        )

        variant_info = ""
        if self.language == "zh":
            variant_info = f" ({'Simplified' if self.simplified_chinese else 'Traditional'})"
        source_info = ""
        if self.source_language != "en":
            source_info = f" from {LANGUAGE_NAMES.get(self.source_language, self.source_language)}"
        logger.info(
            f"Initialized Ungurys agent for {SUPPORTED_LANGUAGES[self.language]}{variant_info}{source_info} (lang_{self.language_suffix})"
        )

    def _apply_country_overrides(self) -> Dict[str, Any]:
        """
        Apply country-related difficulty level overrides for the target language.

        This ensures country words appear at appropriate difficulty levels
        based on the target language being learned. For example, "South Korea"
        appears earlier for Chinese learners but later for Lithuanian learners.

        Returns:
            Dictionary with override results
        """
        # Check if this language has country override configuration
        if self.language not in get_country_override_languages():
            logger.info(f"No country override configuration for '{self.language}' - skipping")
            return {"applied": False, "reason": "no_configuration"}

        try:
            from wordfreq.tools.country_override_manager import CountryOverrideManager

            session = create_session(self.config)
            manager = CountryOverrideManager(session)

            # Apply overrides (this is idempotent - safe to run multiple times)
            summary = manager.apply_overrides(self.language)

            logger.info(
                f"Applied country word overrides for '{self.language}': "
                f"{summary.words_with_changes} words updated"
            )

            session.close()

            return {
                "applied": True,
                "language": self.language,
                "words_updated": summary.words_with_changes,
                "changes_by_tier": summary.changes_by_tier,
            }

        except Exception as e:
            logger.warning(f"Failed to apply country overrides: {e}")
            return {"applied": False, "reason": str(e)}

    def _apply_family_relation_overrides(self) -> Dict[str, Any]:
        """
        Apply family relation difficulty level overrides for the target language.

        This excludes family relation terms that don't map naturally to the
        target language (e.g., "older brother" doesn't exist in English but
        does in Chinese/Korean).

        Returns:
            Dictionary with override results
        """
        # Check if this language has family relation override configuration
        if self.language not in get_family_override_languages():
            logger.info(
                f"No family relation override configuration for '{self.language}' - skipping"
            )
            return {"applied": False, "reason": "no_configuration"}

        try:
            from wordfreq.tools.family_relation_override_manager import (
                FamilyRelationOverrideManager,
            )

            session = create_session(self.config)
            manager = FamilyRelationOverrideManager(session)

            # Apply overrides (this is idempotent - safe to run multiple times)
            summary = manager.apply_overrides(self.language)

            excluded_count = len([c for c in summary.changes if c.is_exclusion])
            included_count = len([c for c in summary.changes if not c.is_exclusion])

            logger.info(
                f"Applied family relation overrides for '{self.language}': "
                f"{excluded_count} words excluded, {included_count} words included"
            )

            session.close()

            return {
                "applied": True,
                "language": self.language,
                "words_excluded": excluded_count,
                "words_included": included_count,
                "total_changes": len(summary.changes),
            }

        except Exception as e:
            logger.warning(f"Failed to apply family relation overrides: {e}")
            return {"applied": False, "reason": str(e)}

    def apply_level_overrides(self) -> Dict[str, Any]:
        """
        Apply all difficulty level overrides for the target language.

        This is a public method that applies both country and family relation
        overrides. Useful for calling from Barsukas before export.

        Returns:
            Dictionary with results for each override type
        """
        results: Dict[str, Any] = {}

        logger.info("Applying country word difficulty overrides...")
        results["country_overrides"] = self._apply_country_overrides()

        logger.info("Applying family relation difficulty overrides...")
        results["family_relation_overrides"] = self._apply_family_relation_overrides()

        return results

    def get_language_output_dir(self) -> str:
        """
        Get the output directory path for the current language.

        Returns:
            Path to data/trakaido_wordlists/lang_{code}/generated/
            For Traditional Chinese: lang_zh_Hant/generated/
            For Simplified Chinese: lang_zh/generated/
        """
        # Get project root (greenland directory)
        project_root = constants.PROJECT_ROOT

        # Build path to data/trakaido_wordlists/lang_{suffix}/generated/
        lang_dir = os.path.join(
            project_root, "data", "trakaido_wordlists", f"lang_{self.language_suffix}", "generated"
        )

        return lang_dir

    def get_default_single_file_path(self) -> str:
        """
        Get the default single-file output path for the current language.

        Returns:
            Path to data/trakaido_wordlists/lang_{code}/generated/wireword/wireword_nouns.json
        """
        lang_dir = self.get_language_output_dir()
        return os.path.join(lang_dir, "wireword", "wireword_nouns.json")

    def export_wireword_single(
        self,
        output_path: str,
        difficulty_level: Optional[int] = None,
        pos_type: Optional[str] = None,
        pos_subtype: Optional[str] = None,
        limit: Optional[int] = None,
        include_without_guid: bool = False,
        include_unverified: bool = True,
    ) -> Tuple[bool, Optional[Any]]:
        """
        Export to a single WireWord format JSON file.

        Args:
            output_path: Path to write the JSON file
            difficulty_level: Filter by specific difficulty level (optional)
            pos_type: Filter by specific POS type (optional)
            pos_subtype: Filter by specific POS subtype (optional)
            limit: Limit number of results (optional)
            include_without_guid: Include lemmas without GUIDs (default: False)
            include_unverified: Include unverified entries (default: True)

        Returns:
            Tuple of (success flag, export statistics)
        """
        logger.info("Starting WireWord single-file export...")

        success, stats = self.exporter.export_to_wireword_format(
            output_path=output_path,
            difficulty_level=difficulty_level,
            pos_type=pos_type,
            pos_subtype=pos_subtype,
            limit=limit,
            include_without_guid=include_without_guid,
            include_unverified=include_unverified,
            pretty_print=True,
        )

        if success:
            logger.info(f"Successfully exported to {output_path}")
        else:
            logger.error(f"Failed to export to {output_path}")

        return success, stats

    def export_wireword_directory(
        self, output_dir: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Export WireWord format files to directory structure.
        Creates separate files for each level and subtype.

        Args:
            output_dir: Base output directory (e.g., lang_lt/generated).
                       If None, uses language-specific path from get_language_output_dir()

        Returns:
            Tuple of (success flag, export results dictionary)
        """
        # Use language-specific directory if not provided
        if output_dir is None:
            output_dir = self.get_language_output_dir()

        logger.info(
            f"Starting WireWord directory export for {SUPPORTED_LANGUAGES[self.language]}..."
        )
        logger.info(f"Output directory: {output_dir}/wireword/")

        success, results = self.exporter.export_wireword_directory(output_dir)

        if success:
            logger.info(f"Successfully exported to {output_dir}/wireword/")
            logger.info(f"  Files created: {len(results.get('files_created', []))}")
            logger.info(f"  Levels exported: {len(results.get('levels_exported', []))}")
            logger.info(f"  Subtypes exported: {len(results.get('subtypes_exported', []))}")

            # Also export sentences
            logger.info("Exporting sentences to wireword_sentences.json...")
            wireword_dir = os.path.join(output_dir, "wireword")
            sentences_path = os.path.join(wireword_dir, "wireword_sentences.json")
            sentence_success, sentence_count = self.export_wireword_sentences(
                output_path=sentences_path,
            )
            if sentence_success:
                logger.info(f"  Exported {sentence_count} sentences")
                results["sentences_exported"] = sentence_count
                # Add sentences file to files_created list
                if "files_created" not in results:
                    results["files_created"] = []
                results["files_created"].append(sentences_path)
            else:
                logger.warning("  Sentence export failed")
                results["sentences_exported"] = 0

            # TODO: Re-enable conversation export when we have conversations
            # Conversation export is disabled - we currently have no conversations
            results["conversations_exported"] = 0

            # Export category choice data (language-independent, goes to trakaido_wordlists root)
            logger.info("Exporting category choice data...")
            category_success, category_path = self.export_category_choice()
            results["category_choice_exported"] = category_success
            if category_success:
                logger.info(f"  Exported categorychoice.json to {category_path}")
            else:
                logger.warning("  Category choice export failed")
        else:
            logger.error(f"Failed to export to {output_dir}")

        return success, results

    def export_wireword_verbs(
        self,
        output_path: Optional[str] = None,
        difficulty_level: Optional[int] = None,
        pos_subtype: Optional[str] = None,
        limit: Optional[int] = None,
        include_without_guid: bool = False,
        include_unverified: bool = True,
    ) -> Tuple[bool, Optional[Any]]:
        """
        Export verbs to a single WireWord format JSON file.

        Args:
            output_path: Path to write the JSON file (if None, uses default)
            difficulty_level: Filter by specific difficulty level (optional)
            pos_subtype: Filter by specific verb subtype (optional)
            limit: Limit number of results (optional)
            include_without_guid: Include lemmas without GUIDs (default: False)
            include_unverified: Include unverified entries (default: True)

        Returns:
            Tuple of (success flag, export statistics)
        """
        # Use default path if not provided
        if output_path is None:
            lang_dir = self.get_language_output_dir()
            output_path = os.path.join(lang_dir, "wireword", "wireword_verbs.json")

        logger.info("Starting WireWord verbs export...")

        success, stats = self.exporter.export_verbs_to_wireword_format(
            output_path=output_path,
            difficulty_level=difficulty_level,
            pos_subtype=pos_subtype,
            limit=limit,
            include_without_guid=include_without_guid,
            include_unverified=include_unverified,
            pretty_print=True,
        )

        if success:
            logger.info(f"Successfully exported verbs to {output_path}")
        else:
            logger.error(f"Failed to export verbs to {output_path}")

        return success, stats

    def export_wireword_sentences(
        self,
        output_path: Optional[str] = None,
    ) -> Tuple[bool, Optional[int]]:
        """
        Export sentences to a single WireWord format JSON file.

        Excludes sentences that are part of conversations (those are exported
        separately in wireword_conversations.jsonl).

        Args:
            output_path: Path to write the JSON file (if None, uses default)

        Returns:
            Tuple of (success flag, sentence count)
        """
        # Use default path if not provided
        if output_path is None:
            lang_dir = self.get_language_output_dir()
            output_path = os.path.join(lang_dir, "wireword", "wireword_sentences.json")

        logger.info("Starting WireWord sentences export...")

        try:
            count = self.sentence_exporter.export_to_file(
                output_path=output_path,
                include_all_languages=False,
                exclude_conversation_sentences=True,
            )
            logger.info(f"Successfully exported {count} sentences to {output_path}")
            return True, count
        except Exception as e:
            logger.error(f"Failed to export sentences: {e}")
            return False, None

    def export_wireword_conversations(
        self,
        output_path: Optional[str] = None,
    ) -> Tuple[bool, Optional[int]]:
        """
        Export conversations to a WireWord format JSONL file.

        Args:
            output_path: Path to write the JSONL file (if None, uses default)

        Returns:
            Tuple of (success flag, conversation count)
        """
        # Use default path if not provided
        if output_path is None:
            lang_dir = self.get_language_output_dir()
            output_path = os.path.join(lang_dir, "wireword", "wireword_conversations.jsonl")

        logger.info("Starting WireWord conversations export...")

        try:
            count = self.conversation_exporter.export_to_file(
                output_path=output_path,
                include_all_languages=False,
            )
            logger.info(f"Successfully exported {count} conversations to {output_path}")
            return True, count
        except Exception as e:
            logger.error(f"Failed to export conversations: {e}")
            return False, None

    def export_category_choice(
        self,
        output_dir: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Export category choice data to the trakaido_wordlists directory.

        This copies the categorychoice.json file from data/ to data/trakaido_wordlists/.
        The file contains category definitions with names, descriptions, groups, and
        similar categories to avoid when choosing quiz decoys.

        Args:
            output_dir: Output directory (default: data/trakaido_wordlists/)

        Returns:
            Tuple of (success flag, output path)
        """
        # Source file is at data/categorychoice.json
        project_root = constants.PROJECT_ROOT
        source_path = os.path.join(project_root, "data", "categorychoice.json")

        # Default output is data/trakaido_wordlists/categorychoice.json
        if output_dir is None:
            output_dir = os.path.join(project_root, "data", "trakaido_wordlists")

        output_path = os.path.join(output_dir, "categorychoice.json")

        logger.info("Exporting category choice data...")

        try:
            # Check source file exists
            if not os.path.exists(source_path):
                logger.error(f"Source file not found: {source_path}")
                return False, None

            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)

            # Copy the file
            shutil.copy2(source_path, output_path)

            # Verify the copy by loading and checking
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                category_count = len(data.get("categories", []))

            logger.info(f"Successfully exported {category_count} categories to {output_path}")
            return True, output_path

        except Exception as e:
            logger.error(f"Failed to export category choice data: {e}")
            return False, None

    def run_export(
        self,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
        difficulty_level: Optional[int] = None,
        pos_type: Optional[str] = None,
        pos_subtype: Optional[str] = None,
        limit: Optional[int] = None,
        include_without_guid: bool = False,
        include_unverified: bool = True,
        export_mode: str = "directory",
        skip_country_overrides: bool = False,
        skip_family_relation_overrides: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the WireWord export with specified parameters.

        Args:
            output_path: Path for single-file export
            output_dir: Directory for directory-structured export
            difficulty_level: Filter by specific difficulty level (optional)
            pos_type: Filter by specific POS type (optional)
            pos_subtype: Filter by specific POS subtype (optional)
            limit: Limit number of results (optional)
            include_without_guid: Include lemmas without GUIDs (default: False)
            include_unverified: Include unverified entries (default: True)
            export_mode: Export mode ('single', 'directory', or 'both')
            skip_country_overrides: Skip applying country difficulty overrides (default: False)
            skip_family_relation_overrides: Skip applying family relation difficulty overrides (default: False)

        Returns:
            Dictionary with export results
        """
        start_time = datetime.now()

        # Apply country-related difficulty overrides before export
        if not skip_country_overrides:
            logger.info("Applying country word difficulty overrides...")
            country_override_results = self._apply_country_overrides()
        else:
            logger.info("Skipping country word overrides (--skip-country-overrides)")
            country_override_results = {"applied": False, "reason": "skipped"}

        # Apply family relation difficulty overrides before export
        if not skip_family_relation_overrides:
            logger.info("Applying family relation difficulty overrides...")
            family_override_results = self._apply_family_relation_overrides()
        else:
            logger.info("Skipping family relation overrides (--skip-family-relation-overrides)")
            family_override_results = {"applied": False, "reason": "skipped"}

        # Get database path from config
        db_path = (
            self.config.sqlite_path if self.config.backend_type == BackendType.SQLITE else None
        )
        results: Dict[str, Any] = {
            "timestamp": start_time.isoformat(),
            "database_path": db_path,
            "export_mode": export_mode,
            "country_overrides": country_override_results,
            "family_relation_overrides": family_override_results,
            "exports": {},
        }

        # Single-file export
        if export_mode in ["single", "both"]:
            if not output_path:
                logger.error("output_path is required for single-file export")
                results["exports"]["single"] = {
                    "success": False,
                    "error": "No output_path specified",
                }
            else:
                success, stats = self.export_wireword_single(
                    output_path=output_path,
                    difficulty_level=difficulty_level,
                    pos_type=pos_type,
                    pos_subtype=pos_subtype,
                    limit=limit,
                    include_without_guid=include_without_guid,
                    include_unverified=include_unverified,
                )
                results["exports"]["single"] = {
                    "success": success,
                    "stats": stats,
                    "path": output_path,
                }

        # Directory export
        if export_mode in ["directory", "both"]:
            success, export_results = self.export_wireword_directory(output_dir)
            # Get the actual directory used (in case output_dir was None and default was used)
            actual_dir = output_dir if output_dir else self.get_language_output_dir()
            results["exports"]["directory"] = {
                "success": success,
                "results": export_results,
                "directory": actual_dir,
            }

        # Always export verbs to separate file (regardless of export mode)
        logger.info("Exporting verbs to separate wireword_verbs.json file...")
        verb_success, verb_stats = self.export_wireword_verbs(
            output_path=None,  # Use default path
            include_without_guid=include_without_guid,
            include_unverified=include_unverified,
        )
        results["exports"]["verbs"] = {
            "success": verb_success,
            "stats": verb_stats,
            "note": "Verbs are always exported to separate wireword_verbs.json file",
        }

        # Always export sentences to separate file (regardless of export mode)
        logger.info("Exporting sentences to wireword_sentences.json file...")
        sentence_success, sentence_count = self.export_wireword_sentences(
            output_path=None,  # Use default path
        )
        results["exports"]["sentences"] = {
            "success": sentence_success,
            "count": sentence_count,
            "note": "Sentences are always exported to wireword_sentences.json file",
        }

        # TODO: Re-enable conversation export when we have conversations
        # Conversation export is disabled - we currently have no conversations
        results["exports"]["conversations"] = {
            "success": True,
            "count": 0,
            "note": "Conversation export disabled - no conversations available",
        }

        # Export category choice data (language-independent, goes to trakaido_wordlists root)
        logger.info("Exporting category choice data...")
        category_success, category_path = self.export_category_choice()
        results["exports"]["category_choice"] = {
            "success": category_success,
            "path": category_path,
            "note": "Category definitions with avoidDecoys for quiz generation",
        }

        # Note: Manifest is generated automatically by export_wireword_directory()
        # Check if it was created and report it
        if "directory" in results["exports"] and results["exports"]["directory"].get("success"):
            dir_results = results["exports"]["directory"].get("results", {})
            if dir_results.get("manifest_path"):
                results["exports"]["manifest"] = {
                    "success": True,
                    "path": dir_results["manifest_path"],
                    "note": "Manifest file describing all exported files with MD5 checksums",
                }

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["duration_seconds"] = duration

        # Print summary
        self._print_summary(results, start_time, duration)

        return results

    def _print_summary(
        self, results: Dict[str, Any], start_time: datetime, duration: float
    ) -> None:
        """Print a summary of the export results."""
        logger.info("=" * 80)
        logger.info("UNGURYS AGENT REPORT - WireWord Export")
        logger.info("=" * 80)
        variant_info = ""
        if self.language == "zh":
            variant_info = f" ({'Simplified' if self.simplified_chinese else 'Traditional'})"
        logger.info(
            f"Language: {SUPPORTED_LANGUAGES[self.language]}{variant_info} (lang_{self.language_suffix})"
        )
        logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Export Mode: {results['export_mode']}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("")

        # Country overrides
        if "country_overrides" in results:
            overrides = results["country_overrides"]
            logger.info("COUNTRY WORD OVERRIDES:")
            if overrides.get("applied"):
                logger.info("  Status: APPLIED")
                logger.info(f"  Words updated: {overrides.get('words_updated', 0)}")
            else:
                reason = overrides.get("reason", "unknown")
                logger.info(f"  Status: SKIPPED ({reason})")
            logger.info("")

        # Family relation overrides
        if "family_relation_overrides" in results:
            overrides = results["family_relation_overrides"]
            logger.info("FAMILY RELATION OVERRIDES:")
            if overrides.get("applied"):
                logger.info("  Status: APPLIED")
                logger.info(f"  Words excluded: {overrides.get('words_excluded', 0)}")
                logger.info(f"  Words included: {overrides.get('words_included', 0)}")
            else:
                reason = overrides.get("reason", "unknown")
                logger.info(f"  Status: SKIPPED ({reason})")
            logger.info("")

        # Single-file export
        if "single" in results["exports"]:
            single = results["exports"]["single"]
            logger.info(f"SINGLE-FILE EXPORT:")
            if single["success"]:
                logger.info(f"  Status: SUCCESS")
                logger.info(f"  Path: {single['path']}")
                if single.get("stats"):
                    stats = single["stats"]
                    logger.info(f"  Total entries: {stats.total_entries}")
                    logger.info(f"  Entries with GUIDs: {stats.entries_with_guids}")
            else:
                logger.info(f"  Status: FAILED")
                if "error" in single:
                    logger.info(f"  Error: {single['error']}")
            logger.info("")

        # Directory export
        if "directory" in results["exports"]:
            directory = results["exports"]["directory"]
            logger.info(f"DIRECTORY EXPORT:")
            if directory["success"]:
                logger.info(f"  Status: SUCCESS")
                logger.info(f"  Directory: {directory['directory']}/wireword/")
                if directory.get("results"):
                    res = directory["results"]
                    logger.info(f"  Files created: {len(res.get('files_created', []))}")
                    logger.info(f"  Levels exported: {len(res.get('levels_exported', []))}")
                    logger.info(f"  Subtypes exported: {len(res.get('subtypes_exported', []))}")
                    logger.info(f"  Total words: {res.get('total_words', 0)}")
            else:
                logger.info(f"  Status: FAILED")
                if "error" in directory:
                    logger.info(f"  Error: {directory['error']}")
            logger.info("")

        # Verb export (separate file)
        if "verbs" in results["exports"]:
            verbs = results["exports"]["verbs"]
            logger.info(f"VERB EXPORT (separate file):")
            if verbs["success"]:
                logger.info(f"  Status: SUCCESS")
                if verbs.get("stats"):
                    stats = verbs["stats"]
                    logger.info(f"  Total verb entries: {stats.total_entries}")
                    logger.info(f"  Entries with GUIDs: {stats.entries_with_guids}")
                logger.info(f"  File: wireword_verbs.json")
            else:
                logger.info(f"  Status: FAILED")
            logger.info("")

        # Sentence export (separate file)
        if "sentences" in results["exports"]:
            sentences = results["exports"]["sentences"]
            logger.info(f"SENTENCE EXPORT (separate file):")
            if sentences["success"]:
                logger.info(f"  Status: SUCCESS")
                logger.info(f"  Total sentences: {sentences.get('count', 0)}")
                logger.info(f"  File: wireword_sentences.json")
            else:
                logger.info(f"  Status: FAILED")
            logger.info("")

        # Conversation export (separate file)
        if "conversations" in results["exports"]:
            conversations = results["exports"]["conversations"]
            logger.info("CONVERSATION EXPORT (separate file):")
            if conversations["success"]:
                logger.info("  Status: SUCCESS")
                logger.info(f"  Total conversations: {conversations.get('count', 0)}")
                logger.info("  File: wireword_conversations.jsonl")
            else:
                logger.info("  Status: FAILED")
            logger.info("")

        # Manifest export
        if "manifest" in results["exports"]:
            manifest = results["exports"]["manifest"]
            logger.info("MANIFEST EXPORT:")
            if manifest["success"]:
                logger.info("  Status: SUCCESS")
                logger.info(f"  Path: {manifest.get('path', '')}")
                logger.info("  File: wireword_manifest.json")
            else:
                logger.info("  Status: FAILED")
            logger.info("")

        # Category choice export
        if "category_choice" in results["exports"]:
            category = results["exports"]["category_choice"]
            logger.info("CATEGORY CHOICE EXPORT:")
            if category["success"]:
                logger.info("  Status: SUCCESS")
                logger.info(f"  Path: {category.get('path', '')}")
                logger.info("  File: categorychoice.json")
            else:
                logger.info("  Status: FAILED")
            logger.info("")

        logger.info("=" * 80)


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(description="Ungurys - WireWord Export Agent")

    # Common arguments
    add_common_args(parser)
    add_backend_args(parser)

    # Language options
    language_help = f'Language code (default: lt). Supported: {", ".join(f"{k}={v}" for k, v in SUPPORTED_LANGUAGES.items())}, zh-Hant=Chinese (Traditional)'
    parser.add_argument(
        "--language", choices=["lt", "zh", "zh-Hant", "ko", "fr"], default="lt", help=language_help
    )
    parser.add_argument(
        "--traditional",
        action="store_true",
        help="For Chinese (zh): export Traditional characters instead of Simplified (exports to lang_zh_Hant/)",
    )

    # Export mode
    parser.add_argument(
        "--mode",
        choices=["single", "directory", "both"],
        default="single",
        help="Export mode: single file, directory structure, or both (default: single)",
    )

    # Output paths
    parser.add_argument(
        "--output",
        help="Output path for single-file export (default: data/trakaido_wordlists/lang_{language}/generated/wireword/wireword_nouns.json)",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for directory export (default: data/trakaido_wordlists/lang_{language}/generated/)",
    )

    # Filtering options
    parser.add_argument("--level", type=int, help="Filter by specific difficulty level")
    parser.add_argument("--pos-type", help="Filter by specific POS type")
    parser.add_argument("--pos-subtype", help="Filter by specific POS subtype")
    parser.add_argument("--limit", type=int, help="Limit number of results")

    # Include options
    parser.add_argument(
        "--include-without-guid",
        action="store_true",
        help="Include lemmas without GUIDs (default: False)",
    )
    parser.add_argument(
        "--include-unverified",
        action="store_true",
        default=True,
        help="Include unverified entries (default: True)",
    )
    parser.add_argument(
        "--include-unreviewed-audio",
        action="store_true",
        help="Include audio from staging that has not yet been reviewed. Changes audio path in manifest.",
    )
    parser.add_argument(
        "--skip-country-overrides",
        action="store_true",
        help="Skip applying country-specific difficulty overrides before export.",
    )
    parser.add_argument(
        "--skip-family-relation-overrides",
        action="store_true",
        help="Skip applying family relation difficulty overrides before export.",
    )
    parser.add_argument(
        "--source-language",
        default="en",
        help="Source language code (default: en). The language the learner already knows. "
        "Supported non-English sources: uk (Ukrainian), bn (Bengali), si (Sinhala).",
    )

    return parser


def main() -> None:
    """Main entry point for the ungurys agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Create configuration from args (always returns a valid config with defaults)
    config = get_data_source_config(args)

    # Handle Traditional Chinese flag
    language = args.language
    if args.traditional and args.language == "zh":
        language = "zh-Hant"

    # Create agent with config
    agent = UngurysAgent(
        config=config,
        language=language,
        include_unreviewed_audio=args.include_unreviewed_audio,
        source_language=args.source_language,
    )

    # Set default paths if not specified
    if args.mode in ["single", "both"] and not args.output:
        args.output = agent.get_default_single_file_path()
        logger.info(f"Using default output path: {args.output}")

    # If output_dir not specified for directory mode, it will use language-specific default
    if args.mode in ["directory", "both"] and not args.output_dir:
        args.output_dir = (
            None  # Will trigger use of get_language_output_dir() in export_wireword_directory
        )

    # Run export
    agent.run_export(
        output_path=args.output,
        output_dir=args.output_dir,
        difficulty_level=args.level,
        pos_type=args.pos_type,
        pos_subtype=args.pos_subtype,
        limit=args.limit,
        include_without_guid=args.include_without_guid,
        include_unverified=args.include_unverified,
        export_mode=args.mode,
        skip_country_overrides=args.skip_country_overrides,
        skip_family_relation_overrides=args.skip_family_relation_overrides,
    )


if __name__ == "__main__":
    main()
