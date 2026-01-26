#!/usr/bin/env python3
"""
Ungurys - WireWord Export Agent

This agent runs autonomously to export word data to WireWord API format.
It replaces the legacy "export wireword" functionality from trakaido/utils.py.

"Ungurys" means "eel" in Lithuanian - swimming data downstream to external systems!
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.translation_helpers import (
    LANGUAGE_NAMES,
    TIER_1_LANGUAGES,
    TIER_2_LANGUAGES,
)
from wordfreq.trakaido.utils.export_manager import TrakaidoExporter
from wireword.export_wireword_conversations import WirewordConversationExporter
from wireword.export_wireword_sentences import WirewordSentenceExporter

# Voice character names per language (for manifest available_voices)
# Maps language code to list of (path_name, display_name) tuples
LANGUAGE_VOICE_NAMES: Dict[str, List[Tuple[str, str]]] = {
    "lt": [("ruta", "Rūta"), ("jonas", "Jonas")],
    "zh": [("meiling", "Meiling"), ("zhiyuan", "Zhiyuan")],
    "fr": [("marie", "Marie"), ("pierre", "Pierre")],
    "ko": [("yuna", "Yuna"), ("minho", "Minho")],  # Placeholder names for Korean
}

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
    ):
        """
        Initialize the Ungurys agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
            language: Language code ('lt' for Lithuanian, 'zh' for Chinese, 'zh-Hant' for Traditional Chinese)
            simplified_chinese: For 'zh', whether to convert to Simplified (default: True)
        """
        self.config = config
        self.debug = config.debug
        self.simplified_chinese = simplified_chinese

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
        )

        # Initialize sentence exporter with Chinese variant support
        self.sentence_exporter = WirewordSentenceExporter(
            config=config,
            debug=self.debug,
            language=self.language,
            simplified_chinese=self.simplified_chinese if self.language == "zh" else True,
        )

        # Initialize conversation exporter with Chinese variant support
        self.conversation_exporter = WirewordConversationExporter(
            config=config,
            debug=self.debug,
            language=self.language,
            simplified_chinese=self.simplified_chinese if self.language == "zh" else True,
        )

        variant_info = ""
        if self.language == "zh":
            variant_info = f" ({'Simplified' if self.simplified_chinese else 'Traditional'})"
        logger.info(
            f"Initialized Ungurys agent for {SUPPORTED_LANGUAGES[self.language]}{variant_info} (lang_{self.language_suffix})"
        )

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

            # Also export conversations
            logger.info("Exporting conversations to wireword_conversations.jsonl...")
            conversations_path = os.path.join(wireword_dir, "wireword_conversations.jsonl")
            conv_success, conv_count = self.export_wireword_conversations(
                output_path=conversations_path,
            )
            if conv_success:
                logger.info(f"  Exported {conv_count} conversations")
                results["conversations_exported"] = conv_count
                results["files_created"].append(conversations_path)
            else:
                logger.warning("  Conversation export failed")
                results["conversations_exported"] = 0
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

    def _calculate_file_md5(self, filepath: str) -> str:
        """Calculate MD5 hash of a file's contents."""
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def _get_file_stats(self, filepath: str) -> Dict[str, Any]:
        """Get statistics from a wireword JSON file (word count, levels, groups)."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                return {}

            levels: set[int] = set()
            groups: set[str] = set()

            for item in data:
                if isinstance(item, dict):
                    if "level" in item and item["level"] is not None:
                        levels.add(item["level"])
                    if "group" in item and item["group"]:
                        groups.add(item["group"])

            return {
                "count": len(data),
                "levels": sorted(levels),
                "groups": sorted(groups),
            }
        except (json.JSONDecodeError, IOError):
            return {}

    def _get_sentence_file_stats(self, filepath: str) -> Dict[str, Any]:
        """Get statistics from a wireword sentences JSON file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                return {}

            min_level: Optional[int] = None
            max_level: Optional[int] = None

            for item in data:
                if isinstance(item, dict) and "minimum_level" in item:
                    level = item["minimum_level"]
                    if level is not None:
                        if min_level is None or level < min_level:
                            min_level = level
                        if max_level is None or level > max_level:
                            max_level = level

            return {
                "count": len(data),
                "min_level": min_level,
                "max_level": max_level,
            }
        except (json.JSONDecodeError, IOError):
            return {}

    def generate_manifest(
        self,
        output_dir: Optional[str] = None,
        export_results: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        Generate wireword_manifest.json for the exported files.

        Args:
            output_dir: Base output directory (e.g., lang_lt/generated).
                       If None, uses language-specific path from get_language_output_dir()
            export_results: Results from run_export containing file paths and stats

        Returns:
            Tuple of (success flag, manifest path)
        """
        if output_dir is None:
            output_dir = self.get_language_output_dir()

        wireword_dir = os.path.join(output_dir, "wireword")
        manifest_path = os.path.join(wireword_dir, "wireword_manifest.json")

        # Determine language name and code
        language_name = SUPPORTED_LANGUAGES[self.language].lower()
        if self.language == "zh" and not self.simplified_chinese:
            language_name = "chinese_traditional"

        # Use the language_suffix for the directory name pattern
        language_code = self.language_suffix

        # Get available voices for this language
        voice_names = LANGUAGE_VOICE_NAMES.get(self.language, [])
        available_voices = [v[0] for v in voice_names]  # path_name versions
        default_voice = available_voices[0] if available_voices else None

        # Build manifest structure
        manifest: Dict[str, Any] = {
            "version": 1,
            "language": language_name,
            "language_code": language_code,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "config": {
                "audio_prefix": "/prod",
                "available_voices": available_voices,
                "default_voice": default_voice,
            },
            "word_files": [],
            "sentence_files": [],
            "auxiliary_files": [],
        }

        # Process word files
        word_files_info = [
            ("nouns", "wireword_nouns.json", "Nouns", "Words (nouns, adjectives, etc.)"),
            ("verbs", "wireword_verbs.json", "Verbs", "Verbs with conjugations"),
        ]

        for file_id, filename, display_name, description in word_files_info:
            filepath = os.path.join(wireword_dir, filename)
            if os.path.exists(filepath):
                file_stats = self._get_file_stats(filepath)
                file_entry: Dict[str, Any] = {
                    "id": file_id,
                    "filename": filename,
                    "display_name": display_name,
                    "description": description,
                    "type": "words",
                    "md5": self._calculate_file_md5(filepath),
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "required": True,
                }
                if file_stats.get("count"):
                    file_entry["word_count"] = file_stats["count"]
                if file_stats.get("levels"):
                    file_entry["levels"] = file_stats["levels"]
                if file_stats.get("groups"):
                    file_entry["groups"] = file_stats["groups"]

                manifest["word_files"].append(file_entry)

        # Process sentence files
        sentences_path = os.path.join(wireword_dir, "wireword_sentences.json")
        if os.path.exists(sentences_path):
            sentence_stats = self._get_sentence_file_stats(sentences_path)
            sentence_entry: Dict[str, Any] = {
                "id": "sentences",
                "filename": "wireword_sentences.json",
                "display_name": "Practice Sentences",
                "description": "Sentences for context-based learning",
                "type": "sentences",
                "md5": self._calculate_file_md5(sentences_path),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "required": False,
            }
            if sentence_stats.get("count"):
                sentence_entry["sentence_count"] = sentence_stats["count"]
            if sentence_stats.get("min_level") is not None:
                sentence_entry["min_level"] = sentence_stats["min_level"]
            if sentence_stats.get("max_level") is not None:
                sentence_entry["max_level"] = sentence_stats["max_level"]

            manifest["sentence_files"].append(sentence_entry)

        # Process conversations file (JSONL format - auxiliary file)
        conversations_path = os.path.join(wireword_dir, "wireword_conversations.jsonl")
        if os.path.exists(conversations_path):
            # Count lines in JSONL file
            try:
                with open(conversations_path, "r", encoding="utf-8") as f:
                    conversation_count = sum(1 for line in f if line.strip())
            except IOError:
                conversation_count = 0

            conversation_entry: Dict[str, Any] = {
                "id": "conversations",
                "filename": "wireword_conversations.jsonl",
                "display_name": "Conversations",
                "description": "Practice conversations for dialogue-based learning",
                "type": "conversations",
                "md5": self._calculate_file_md5(conversations_path),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "required": False,
                "conversation_count": conversation_count,
            }
            manifest["auxiliary_files"].append(conversation_entry)

        # Write manifest file
        try:
            os.makedirs(wireword_dir, exist_ok=True)
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            logger.info(f"Generated manifest: {manifest_path}")
            return True, manifest_path
        except IOError as e:
            logger.error(f"Failed to write manifest: {e}")
            return False, ""

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

        Returns:
            Dictionary with export results
        """
        start_time = datetime.now()
        # Get database path from config
        db_path = (
            self.config.sqlite_path if self.config.backend_type == BackendType.SQLITE else None
        )
        results: Dict[str, Any] = {
            "timestamp": start_time.isoformat(),
            "database_path": db_path,
            "export_mode": export_mode,
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

        # Always export conversations to separate file (regardless of export mode)
        logger.info("Exporting conversations to wireword_conversations.jsonl file...")
        conv_success, conv_count = self.export_wireword_conversations(
            output_path=None,  # Use default path
        )
        results["exports"]["conversations"] = {
            "success": conv_success,
            "count": conv_count,
            "note": "Conversations are always exported to wireword_conversations.jsonl file",
        }

        # Generate manifest file
        actual_dir = output_dir if output_dir else self.get_language_output_dir()
        logger.info("Generating wireword_manifest.json...")
        manifest_success, manifest_path = self.generate_manifest(
            output_dir=actual_dir,
            export_results=results,
        )
        results["exports"]["manifest"] = {
            "success": manifest_success,
            "path": manifest_path,
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
    agent = UngurysAgent(config=config, language=language)

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
    )


if __name__ == "__main__":
    main()
