#!/usr/bin/env python3
"""
Bebras - Sentence-Word Link Management Agent

This agent manages the relationship between sentences and vocabulary words:
1. Analyzes sentences to extract key vocabulary words
2. Links sentences to lemmas in the database
3. Resolves word disambiguation (e.g., "mouse" → animal vs. computer)
4. Adds translations for multiple target languages

"Bebras" means "beaver" in Lithuanian - industrious builder of connections!

Usage:
  # Process a single sentence
  python bebras.py --sentence "I eat a banana" --languages lt zh

  # Process sentences from a file
  python bebras.py --file sentences.txt --languages lt zh

  # Run the old database integrity checker
  python bebras.py --check-integrity
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

# Import new sentence-word link functionality
from wordfreq.agents.bebras.cli import (
    get_argument_parser as get_sentence_parser,
    main as sentence_main
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_argument_parser():
    """
    Return the main argument parser.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    # Check if we're running in integrity check mode
    if '--check-integrity' in sys.argv:
        # Import the old integrity checker
        from wordfreq.agents import bebras_old
        return bebras_old.get_argument_parser()
    else:
        # Use the new sentence-word link CLI
        return get_sentence_parser()


def main():
    """Main entry point for Bebras."""
    # Check if we're running in integrity check mode
    if '--check-integrity' in sys.argv:
        # Remove the flag and delegate to old integrity checker
        sys.argv.remove('--check-integrity')
        from wordfreq.agents import bebras_old
        return bebras_old.main()
    else:
        # Run the new sentence-word link functionality
        return sentence_main()


if __name__ == '__main__':
    sys.exit(main())
