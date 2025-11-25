#!/usr/bin/env python3
"""
Ungurys - WireWord Export Agent

This agent runs autonomously to export word data to WireWord API format.
It replaces the legacy "export wireword" functionality from trakaido/utils.py.

"Ungurys" means "eel" in Lithuanian - swimming data downstream to external systems!
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from wordfreq.trakaido.utils.export_manager import TrakaidoExporter

# Supported languages and their codes
SUPPORTED_LANGUAGES = {
    "lt": "Lithuanian",
    "zh": "Chinese",
    "ko": "Korean",
    "fr": "French"
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class UngurysAgent:
    """Agent for exporting word data to WireWord format."""

    def __init__(self, db_path: str = None, debug: bool = False, language: str = "lt",
                 simplified_chinese: bool = True):
        """
        Initialize the Ungurys agent.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
            language: Language code ('lt' for Lithuanian, 'zh' for Chinese, 'zh-Hant' for Traditional Chinese)
            simplified_chinese: For 'zh', whether to convert to Simplified (default: True)
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.simplified_chinese = simplified_chinese

        # Handle language variants
        if language == "zh-Hant":
            self.language = "zh"
            self.simplified_chinese = False
            self.language_suffix = "zh_Hant"
        else:
            self.language = language
            self.language_suffix = language

        if debug:
            logger.setLevel(logging.DEBUG)

        # Validate language
        if self.language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {self.language}. Supported: {', '.join(SUPPORTED_LANGUAGES.keys())}")

        # Initialize exporter with language parameter and Chinese variant
        self.exporter = TrakaidoExporter(
            db_path=self.db_path,
            debug=debug,
            language=self.language,
            simplified_chinese=self.simplified_chinese if self.language == "zh" else True
        )

        variant_info = ""
        if self.language == "zh":
            variant_info = f" ({'Simplified' if self.simplified_chinese else 'Traditional'})"
        logger.info(f"Initialized Ungurys agent for {SUPPORTED_LANGUAGES[self.language]}{variant_info} (lang_{self.language_suffix})")

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
        lang_dir = os.path.join(project_root, "data", "trakaido_wordlists", f"lang_{self.language_suffix}", "generated")

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
        include_unverified: bool = True
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
            pretty_print=True
        )

        if success:
            logger.info(f"Successfully exported to {output_path}")
        else:
            logger.error(f"Failed to export to {output_path}")

        return success, stats

    def export_wireword_directory(
        self,
        output_dir: Optional[str] = None
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

        logger.info(f"Starting WireWord directory export for {SUPPORTED_LANGUAGES[self.language]}...")
        logger.info(f"Output directory: {output_dir}/wireword/")

        success, results = self.exporter.export_wireword_directory(output_dir)

        if success:
            logger.info(f"Successfully exported to {output_dir}/wireword/")
            logger.info(f"  Files created: {len(results.get('files_created', []))}")
            logger.info(f"  Levels exported: {len(results.get('levels_exported', []))}")
            logger.info(f"  Subtypes exported: {len(results.get('subtypes_exported', []))}")
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
        include_unverified: bool = True
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
            pretty_print=True
        )

        if success:
            logger.info(f"Successfully exported verbs to {output_path}")
        else:
            logger.error(f"Failed to export verbs to {output_path}")

        return success, stats

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
        export_mode: str = "directory"
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
        results = {
            "timestamp": start_time.isoformat(),
            "database_path": self.db_path,
            "export_mode": export_mode,
            "exports": {}
        }

        # Single-file export
        if export_mode in ["single", "both"]:
            if not output_path:
                logger.error("output_path is required for single-file export")
                results["exports"]["single"] = {"success": False, "error": "No output_path specified"}
            else:
                success, stats = self.export_wireword_single(
                    output_path=output_path,
                    difficulty_level=difficulty_level,
                    pos_type=pos_type,
                    pos_subtype=pos_subtype,
                    limit=limit,
                    include_without_guid=include_without_guid,
                    include_unverified=include_unverified
                )
                results["exports"]["single"] = {
                    "success": success,
                    "stats": stats,
                    "path": output_path
                }

        # Directory export
        if export_mode in ["directory", "both"]:
            success, export_results = self.export_wireword_directory(output_dir)
            # Get the actual directory used (in case output_dir was None and default was used)
            actual_dir = output_dir if output_dir else self.get_language_output_dir()
            results["exports"]["directory"] = {
                "success": success,
                "results": export_results,
                "directory": actual_dir
            }

        # Always export verbs to separate file (regardless of export mode)
        logger.info("Exporting verbs to separate wireword_verbs.json file...")
        verb_success, verb_stats = self.export_wireword_verbs(
            output_path=None,  # Use default path
            include_without_guid=include_without_guid,
            include_unverified=include_unverified
        )
        results["exports"]["verbs"] = {
            "success": verb_success,
            "stats": verb_stats,
            "note": "Verbs are always exported to separate wireword_verbs.json file"
        }

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["duration_seconds"] = duration

        # Print summary
        self._print_summary(results, start_time, duration)

        return results

    def _print_summary(self, results: Dict, start_time: datetime, duration: float):
        """Print a summary of the export results."""
        logger.info("=" * 80)
        logger.info("UNGURYS AGENT REPORT - WireWord Export")
        logger.info("=" * 80)
        variant_info = ""
        if self.language == "zh":
            variant_info = f" ({'Simplified' if self.simplified_chinese else 'Traditional'})"
        logger.info(f"Language: {SUPPORTED_LANGUAGES[self.language]}{variant_info} (lang_{self.language_suffix})")
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

        logger.info("=" * 80)


def main():
    """Main entry point for the ungurys agent."""
    parser = argparse.ArgumentParser(
        description="Ungurys - WireWord Export Agent"
    )
    parser.add_argument("--db-path", help="Database path (uses default if not specified)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    # Language options
    language_help = f'Language code (default: lt). Supported: {", ".join(f"{k}={v}" for k, v in SUPPORTED_LANGUAGES.items())}, zh-Hant=Chinese (Traditional)'
    parser.add_argument("--language", choices=["lt", "zh", "zh-Hant", "ko", "fr"], default="lt",
                       help=language_help)
    parser.add_argument("--traditional", action="store_true",
                       help="For Chinese (zh): export Traditional characters instead of Simplified (exports to lang_zh_Hant/)")

    # Export mode
    parser.add_argument("--mode", choices=["single", "directory", "both"], default="single",
                       help="Export mode: single file, directory structure, or both (default: single)")

    # Output paths
    parser.add_argument("--output", help="Output path for single-file export (default: data/trakaido_wordlists/lang_{language}/generated/wireword/wireword_nouns.json)")
    parser.add_argument("--output-dir", help="Output directory for directory export (default: data/trakaido_wordlists/lang_{language}/generated/)")

    # Filtering options
    parser.add_argument("--level", type=int, help="Filter by specific difficulty level")
    parser.add_argument("--pos-type", help="Filter by specific POS type")
    parser.add_argument("--pos-subtype", help="Filter by specific POS subtype")
    parser.add_argument("--limit", type=int, help="Limit number of results")

    # Include options
    parser.add_argument("--include-without-guid", action="store_true",
                       help="Include lemmas without GUIDs (default: False)")
    parser.add_argument("--include-unverified", action="store_true", default=True,
                       help="Include unverified entries (default: True)")

    args = parser.parse_args()

    # Handle Traditional Chinese flag
    language = args.language
    if args.traditional and args.language == "zh":
        language = "zh-Hant"

    # Create agent
    agent = UngurysAgent(db_path=args.db_path, debug=args.debug, language=language)

    # Set default paths if not specified
    if args.mode in ["single", "both"] and not args.output:
        args.output = agent.get_default_single_file_path()
        logger.info(f"Using default output path: {args.output}")

    # If output_dir not specified for directory mode, it will use language-specific default
    if args.mode in ["directory", "both"] and not args.output_dir:
        args.output_dir = None  # Will trigger use of get_language_output_dir() in export_wireword_directory

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
        export_mode=args.mode
    )


if __name__ == "__main__":
    main()
