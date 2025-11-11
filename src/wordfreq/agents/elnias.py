#!/usr/bin/env python3
"""
Elnias - Bootstrap Export Agent

This agent runs autonomously to export word data in a minimal "bootstrap" format.
The output contains just enough information to bootstrap a system: word in 2 languages,
GUID, categorization, and trakaido level.

No synonyms, alternative forms, or other enrichment data are included.

"Elnias" means "deer" in Lithuanian - nimble and light, like this minimal export format!
"""

import argparse
import logging
import os
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, List

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from wordfreq.trakaido.utils.export_manager import TrakaidoExporter

# Supported languages and their codes
SUPPORTED_LANGUAGES = {
    'lt': 'Lithuanian',
    'zh': 'Chinese',
    'ko': 'Korean',
    'fr': 'French'
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ElniasAgent:
    """Agent for exporting word data in minimal bootstrap format."""

    def __init__(self, db_path: str = None, debug: bool = False, language: str = 'lt',
                 simplified_chinese: bool = True):
        """
        Initialize the Elnias agent.

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
        if language == 'zh-Hant':
            self.language = 'zh'
            self.simplified_chinese = False
            self.language_suffix = 'zh_Hant'
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
            simplified_chinese=self.simplified_chinese if self.language == 'zh' else True
        )

        variant_info = ""
        if self.language == 'zh':
            variant_info = f" ({'Simplified' if self.simplified_chinese else 'Traditional'})"
        logger.info(f"Initialized Elnias agent for {SUPPORTED_LANGUAGES[self.language]}{variant_info} (lang_{self.language_suffix})")

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

        # Build path: data/trakaido_wordlists/lang_{code}/generated/
        output_dir = os.path.join(
            project_root,
            'data',
            'trakaido_wordlists',
            f'lang_{self.language_suffix}',
            'generated'
        )

        return output_dir

    def get_default_output_path(self) -> str:
        """
        Get the default output file path for bootstrap export.

        Returns:
            Path to bootstrap.json in the language's generated directory
        """
        output_dir = self.get_language_output_dir()
        return os.path.join(output_dir, 'bootstrap.json')

    def export_bootstrap(
        self,
        output_path: Optional[str] = None,
        include_unverified: bool = False
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

        # Query all non-verb words with translations
        # Note: verbs are excluded because of wild differences in conjugation between languages
        export_data = self.exporter.query_trakaido_data(
            session=self.exporter.get_session(),
            include_without_guid=False,  # Only include words with GUIDs for bootstrap
            include_unverified=include_unverified
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
                "subtype": entry["subtype"]
            }
            bootstrap_data.append(bootstrap_entry)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Write JSON file with pretty formatting
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(bootstrap_data, f, ensure_ascii=False, indent=2)

        file_size = os.path.getsize(output_path)
        logger.info(f"Successfully wrote {len(bootstrap_data)} entries to {output_path}")
        logger.info(f"File size: {file_size:,} bytes")

        return {
            'success': True,
            'output_path': output_path,
            'entry_count': len(bootstrap_data),
            'file_size': file_size,
            'language': language_name,
            'language_code': self.language_suffix,
            'include_unverified': include_unverified
        }

    def run_export(
        self,
        output_path: Optional[str] = None,
        include_unverified: bool = False
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
            logger.info("ELNIAS - Bootstrap Export Agent")
            logger.info("=" * 60)

            result = self.export_bootstrap(
                output_path=output_path,
                include_unverified=include_unverified
            )

            logger.info("=" * 60)
            logger.info("Export completed successfully!")
            logger.info("=" * 60)

            return result

        except Exception as e:
            logger.error(f"Export failed: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }


def main():
    """Main entry point for command-line execution."""
    parser = argparse.ArgumentParser(
        description='Elnias - Bootstrap Export Agent',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export Lithuanian bootstrap data (default)
  python3 elnias.py

  # Export Chinese (Simplified) bootstrap data
  python3 elnias.py --language zh

  # Export Chinese (Traditional) bootstrap data
  python3 elnias.py --language zh-Hant

  # Export Korean bootstrap data
  python3 elnias.py --language ko

  # Export to custom path
  python3 elnias.py --output /path/to/bootstrap.json

  # Include unverified entries
  python3 elnias.py --include-unverified

  # Debug mode
  python3 elnias.py --debug
        """
    )

    parser.add_argument(
        '--db-path',
        type=str,
        help='Path to the database file (default: from constants.WORDFREQ_DB_PATH)'
    )

    parser.add_argument(
        '--language',
        type=str,
        default='lt',
        choices=['lt', 'zh', 'zh-Hant', 'ko', 'fr'],
        help='Target language code (default: lt)'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output file path (default: data/trakaido_wordlists/lang_{code}/generated/bootstrap.json)'
    )

    parser.add_argument(
        '--include-unverified',
        action='store_true',
        help='Include unverified entries in export'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    # Handle Traditional Chinese flag
    simplified_chinese = True
    if args.language == 'zh-Hant':
        simplified_chinese = False

    # Create agent
    agent = ElniasAgent(
        db_path=args.db_path,
        debug=args.debug,
        language=args.language,
        simplified_chinese=simplified_chinese
    )

    # Run export
    result = agent.run_export(
        output_path=args.output,
        include_unverified=args.include_unverified
    )

    # Exit with appropriate code
    sys.exit(0 if result.get('success', False) else 1)


if __name__ == '__main__':
    main()
