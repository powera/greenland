#!/usr/bin/env python3
"""
Bebras - Sentence-Word Link Management and Database Integrity Agent

This agent manages relationships between sentences and vocabulary words,
and checks database integrity. Both are aspects of ensuring the beaver's
"solid structures" remain strong!

"Bebras" means "beaver" in Lithuanian - industrious builder of connections!

Usage:
  # Process a single sentence
  python bebras.py --sentence "I eat a banana" --languages lt zh

  # Process sentences from a file
  python bebras.py --file sentences.txt --languages lt zh

  # Check database integrity
  python bebras.py --check-integrity [--check all|orphaned|...]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

# Import sentence-word link functionality
from agents.bebras.cli import (
    get_argument_parser as get_sentence_parser,
    main as sentence_main
)

# Import integrity checker functionality
from agents.bebras.integrity import (
    get_argument_parser as get_integrity_parser,
    main as integrity_main
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
        return get_integrity_parser()
    else:
        return get_sentence_parser()


def main():
    """Main entry point for Bebras."""
    # Check if we're running in integrity check mode
    if '--check-integrity' in sys.argv:
        # Remove the flag and delegate to integrity checker
        sys.argv.remove('--check-integrity')
        return integrity_main()
    else:
        # Run the sentence-word link functionality
        return sentence_main()


if __name__ == '__main__':
    sys.exit(main())
