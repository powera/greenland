#!/usr/bin/env python3
"""
Ungurys - WireWord Export Agent

This agent runs autonomously to export word data to WireWord API format.
It replaces the legacy "export wireword" functionality from trakaido/utils.py.

"Ungurys" means "eel" in Lithuanian - swimming data downstream to external systems!
"""

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

# Supported languages: Tier 1, Tier 2, plus Japanese for WireWord exports.
SUPPORTED_LANGUAGES = {
    lang_code: LANGUAGE_NAMES[lang_code]
    for lang_code in TIER_1_LANGUAGES + TIER_2_LANGUAGES + ["ja"]
}

# Explicitly supported non-English source languages for WireWord export variants.
SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES = ("uk", "bn", "kn", "pl", "ro", "es", "fr", "zh")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

MIN_WIREWORD_SENTENCE_EXPORT_COUNT = 25


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

        supported_source_languages = {"en", *SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES}
        if self.source_language not in supported_source_languages:
            supported_source_display = ", ".join(sorted(supported_source_languages))
            raise ValueError(
                f"Unsupported source language: {self.source_language}. "
                f"Supported: {supported_source_display}"
            )

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

        if self.source_language == self.language:
            raise ValueError(f"Source language cannot equal target language ({self.language}).")

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

    def _get_cdn_language_code(self) -> str:
        """Return the language code used for CDN paths and the manifest."""
        if self.language == "zh" and not self.simplified_chinese:
            return "zh_Hant"
        return self.language

    def export_wireword_directory(
        self,
        output_dir: Optional[str] = None,
        cdn_upload: bool = False,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Export WireWord format files to directory structure.
        Creates one file per level range containing both nouns and verbs.

        Args:
            output_dir: Base output directory (e.g., lang_lt/generated).
                       If None, uses language-specific path from get_language_output_dir()
            cdn_upload: If True, upload non-manifest files to the
                trakaido-wireword CDN bucket and generate the manifest with
                cdn_base so filenames use MD5 hashes.

        Returns:
            Tuple of (success flag, export results dictionary)
        """
        from clients.wireword.cdn_uploader import WIREWORD_CDN_BASE

        # Use language-specific directory if not provided
        if output_dir is None:
            output_dir = self.get_language_output_dir()

        cdn_base: Optional[str] = WIREWORD_CDN_BASE if cdn_upload else None

        logger.info(
            f"Starting WireWord directory export for {SUPPORTED_LANGUAGES[self.language]}..."
        )
        logger.info(f"Output directory: {output_dir}/wireword/")

        success, results = self.exporter.export_wireword_directory(output_dir, cdn_base=cdn_base)

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

            # Upload non-manifest files to CDN
            if cdn_upload:
                logger.info("Uploading wireword files to CDN...")
                cdn_success, cdn_results = self._upload_to_cdn(wireword_dir)
                results["cdn_upload"] = {
                    "success": cdn_success,
                    "files_uploaded": len(cdn_results),
                }
                if cdn_success:
                    logger.info(f"  ✅ Uploaded {len(cdn_results)} files to CDN")
                else:
                    logger.warning("  ⚠️ Some CDN uploads failed")
        else:
            logger.error(f"Failed to export to {output_dir}")

        return success, results

    def _upload_to_cdn(self, wireword_dir: str) -> Tuple[bool, list[Dict[str, str]]]:
        """Upload non-manifest wireword files to the CDN bucket."""
        from clients.wireword.cdn_uploader import WirewordCdnUploader

        language_code = self._get_cdn_language_code()
        uploader = WirewordCdnUploader()
        return uploader.upload_wireword_directory(wireword_dir, language_code)

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
                min_sentences_to_export=MIN_WIREWORD_SENTENCE_EXPORT_COUNT,
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
        cdn_upload: bool = False,
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
            cdn_upload: Upload non-manifest files to CDN and use MD5 filenames in manifest (default: False)

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
            success, export_results = self.export_wireword_directory(
                output_dir, cdn_upload=cdn_upload
            )
            # Get the actual directory used (in case output_dir was None and default was used)
            actual_dir = output_dir if output_dir else self.get_language_output_dir()
            results["exports"]["directory"] = {
                "success": success,
                "results": export_results,
                "directory": actual_dir,
            }

        # Legacy: export separate verb/sentence files for single/both modes.
        # In directory mode these are already included in the level-range files
        # and the directory export handles sentences too.
        if export_mode in ["single", "both"]:
            logger.warning(
                "⚠️  Exporting legacy separate wireword_verbs.json "
                "(deprecated — use directory mode)"
            )
            verb_success, verb_stats = self.export_wireword_verbs(
                output_path=None,
                include_without_guid=include_without_guid,
                include_unverified=include_unverified,
            )
            results["exports"]["verbs"] = {
                "success": verb_success,
                "stats": verb_stats,
                "note": "Legacy separate verb file (deprecated)",
            }

            logger.info("Exporting sentences to wireword_sentences.json file...")
            sentence_success, sentence_count = self.export_wireword_sentences(
                output_path=None,
            )
            results["exports"]["sentences"] = {
                "success": sentence_success,
                "count": sentence_count,
                "note": "Sentences exported to wireword_sentences.json file",
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
                logger.info("  File: wireword_manifest_v2.json")
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
