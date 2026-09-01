#!/usr/bin/env python3
"""
Bootstrap export generation.

This agent runs autonomously to export word data in a minimal "bootstrap" format.
The output contains just enough information to bootstrap a system: word in 2 languages,
GUID, categorization, and trakaido level.

No synonyms, alternative forms, or other enrichment data are included.

"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_output_args,
    get_data_source_config,
)
from langtools.dialect_overrides import normalize_language_code
from storage.backend.config import BackendType, DataSourceConfig
from exports.wireword.export_manager import TrakaidoExporter

# Supported languages and their codes
SUPPORTED_LANGUAGES = {
    "lt": "Lithuanian",
    "zh": "Chinese",
    "zh-tw": "Chinese (Taiwan)",
    "ko": "Korean",
    "fr": "French",
}

# Spellings accepted but not advertised; normalize_language_code folds each to a
# supported code (zh-Hant and zh_TW both mean zh-tw).
DEPRECATED_LANGUAGE_ALIASES = ["zh-Hant", "zh_TW"]

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BootstrapExporter:
    """Export word data in the minimal bootstrap format."""

    def __init__(
        self,
        config: DataSourceConfig,
        language: str = "lt",
    ):
        """
        Initialize the Elnias agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
            language: Language code ('lt' for Lithuanian, 'zh' for Chinese, 'zh-tw' for
                Taiwan Traditional Chinese).  Taken through normalize_language_code, so
                the older 'zh-Hant' spelling (and 'zh_TW') resolves to 'zh-tw'.
        """
        self.config = config
        self.debug = config.debug

        # zh-tw is an ordinary language here: its own translation rows and its
        # own output directory, with no fallback to zh's text.
        self.language = normalize_language_code(language)
        self.language_suffix = self.language

        if self.debug:
            logger.setLevel(logging.DEBUG)

        # Validate language
        if self.language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language: {self.language}. Supported: {', '.join(SUPPORTED_LANGUAGES.keys())}"
            )

        # Initialize exporter with language parameter
        self.exporter = TrakaidoExporter(
            config=config,
            debug=self.debug,
            language=self.language,
        )

        logger.info(
            f"Initialized Elnias agent for {SUPPORTED_LANGUAGES[self.language]} "
            f"(lang_{self.language_suffix})"
        )

    def get_language_output_dir(self) -> str:
        """
        Get the output directory path for the current language.

        Returns:
            Path to data/trakaido_wordlists/lang_{code}/generated/
            For Taiwan Traditional Chinese: lang_zh-tw/generated/
            For Mainland Simplified Chinese: lang_zh/generated/
        """
        # Get project root (greenland directory)
        project_root = constants.PROJECT_ROOT

        # Build path: data/trakaido_wordlists/lang_{code}/generated/
        output_dir = os.path.join(
            project_root, "data", "trakaido_wordlists", f"lang_{self.language_suffix}", "generated"
        )

        return output_dir

    def get_default_output_path(self) -> str:
        """
        Get the default output file path for bootstrap export.

        Returns:
            Path to bootstrap.json in the language's generated directory
        """
        output_dir = self.get_language_output_dir()
        return os.path.join(output_dir, "bootstrap.json")

    def export_bootstrap(
        self, output_path: Optional[str] = None, include_unverified: bool = False
    ) -> Dict[str, Any]:
        """
        Export word data in minimal bootstrap format.

        The bootstrap format includes:
        - English: English word
        - {Language}: Target language translation (e.g., "Lithuanian")
        - GUID: Word identifier
        - trakaido_level: Difficulty level (NOTE: might be removable in future)
        - POS: Part of speech (noun, adjective, etc. - verbs excluded)
        - subtype: POS subtype categorization

        Args:
            output_path: Output file path (uses default if None)
            include_unverified: Include unverified entries (default: False)

        Returns:
            Dictionary with export statistics and file path
        """
        if output_path is None:
            output_path = self.get_default_output_path()

        logger.info(f"Starting bootstrap export to: {output_path}")
        logger.info(f"Language: {SUPPORTED_LANGUAGES[self.language]}")
        logger.info(f"Include unverified: {include_unverified}")

        # Query all words with translations (including verbs)
        # Note: Bootstrap format only includes base forms, so verb conjugation complexity doesn't apply
        export_data = self.exporter.query_trakaido_data(
            session=self.exporter.get_session(),
            include_without_guid=False,  # Only include words with GUIDs for bootstrap
            include_unverified=include_unverified,
            exclude_verbs=False,  # Include verbs in bootstrap export
        )

        logger.info(f"Found {len(export_data)} entries for export")

        # Transform to bootstrap format with language-specific key names
        language_name = SUPPORTED_LANGUAGES[self.language]
        bootstrap_data = []

        for entry in export_data:
            bootstrap_entry = {
                "English": entry["English"],
                language_name: entry["Target"],  # Use language name instead of "Target"
                "GUID": entry["GUID"],
                # NOTE: trakaido_level is included for now but might be removable in the future
                "trakaido_level": entry["trakaido_level"],
                "POS": entry["POS"],
                "subtype": entry["subtype"],
            }
            bootstrap_data.append(bootstrap_entry)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Write JSON file with pretty formatting
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(bootstrap_data, f, ensure_ascii=False, indent=2)

        file_size = os.path.getsize(output_path)
        logger.info(f"Successfully wrote {len(bootstrap_data)} entries to {output_path}")
        logger.info(f"File size: {file_size:,} bytes")

        return {
            "success": True,
            "output_path": output_path,
            "entry_count": len(bootstrap_data),
            "file_size": file_size,
            "language": language_name,
            "language_code": self.language_suffix,
            "include_unverified": include_unverified,
        }

    def run_export(
        self, output_path: Optional[str] = None, include_unverified: bool = False
    ) -> Dict[str, Any]:
        """
        Main entry point for running the export.

        Args:
            output_path: Output file path (uses default if None)
            include_unverified: Include unverified entries (default: False)

        Returns:
            Dictionary with export results
        """
        try:
            logger.info("=" * 60)
            logger.info("Bootstrap export")
            logger.info("=" * 60)

            result = self.export_bootstrap(
                output_path=output_path, include_unverified=include_unverified
            )

            logger.info("=" * 60)
            logger.info("Export completed successfully!")
            logger.info("=" * 60)

            return result

        except Exception as e:
            logger.error(f"Export failed: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Elnias - Bootstrap Export Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export Lithuanian bootstrap data (default)
  python3 elnias.py

  # Export Chinese (Simplified) bootstrap data
  python3 elnias.py --language zh

  # Export Chinese (Taiwan, Traditional) bootstrap data
  python3 elnias.py --language zh-tw

  # Export Korean bootstrap data
  python3 elnias.py --language ko

  # Export to custom path
  python3 elnias.py --output /path/to/bootstrap.json

  # Include unverified entries
  python3 elnias.py --include-unverified

  # Debug mode
  python3 elnias.py --debug
        """,
    )

    # Common arguments
    add_common_args(parser)
    add_output_args(parser)
    add_backend_args(parser)

    # Elnias-specific arguments
    parser.add_argument(
        "--language",
        type=str,
        default="lt",
        choices=sorted(SUPPORTED_LANGUAGES.keys()) + DEPRECATED_LANGUAGE_ALIASES,
        help="Target language code (default: lt)",
    )

    parser.add_argument(
        "--include-unverified", action="store_true", help="Include unverified entries in export"
    )

    return parser


ElniasAgent = BootstrapExporter


def main() -> None:
    """Main entry point for command-line execution."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Create configuration from args (always returns a valid config with defaults)
    config = get_data_source_config(args)

    # Create agent with config (BootstrapExporter normalizes the language code)
    agent = BootstrapExporter(
        config=config,
        language=args.language,
    )

    # Run export
    result = agent.run_export(output_path=args.output, include_unverified=args.include_unverified)

    # Exit with appropriate code
    sys.exit(0 if result.get("success", False) else 1)


if __name__ == "__main__":
    main()
