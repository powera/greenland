#!/usr/bin/env python3
"""
Bebras - Sentence-Word Link Management, Integrity, and Verification Agent

This agent manages relationships between sentences and vocabulary words,
checks database integrity, and verifies translation correctness. All aspects
of ensuring the beaver's "solid structures" remain strong!

"Bebras" means "beaver" in Lithuanian - industrious builder of connections!

Usage:
  # Process a single sentence
  python bebras.py --sentence "I eat a banana" --languages lt zh

  # Process sentences from a file
  python bebras.py --file sentences.txt --languages lt zh

  # Check database integrity
  python bebras.py --check-integrity [--check all|orphaned|...]

  # Verify word translations
  python bebras.py --verify words --limit 100 --languages lt zh

  # Verify sentence translations
  python bebras.py --verify sentences --limit 50
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
from agents.bebras.cli import get_argument_parser as get_sentence_parser
from agents.bebras.cli import main as sentence_main

# Import integrity checker functionality
from agents.bebras.integrity import get_argument_parser as get_integrity_parser
from agents.bebras.integrity import main as integrity_main

# Import verification functionality
from agents.bebras.verification_cli import get_argument_parser as get_verify_parser
from agents.bebras.verification_cli import main as verify_main

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_argument_parser() -> argparse.ArgumentParser:
    """
    Return the main argument parser.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    # Check which mode we're running in
    if "--check-integrity" in sys.argv:
        return get_integrity_parser()
    elif "--verify" in sys.argv:
        return get_verify_parser()
    else:
        return get_sentence_parser()


def main() -> int:
    """Main entry point for Bebras."""
    # Check which mode we're running in
    if "--check-integrity" in sys.argv:
        # Remove the flag and delegate to integrity checker
        sys.argv.remove("--check-integrity")
        integrity_main()  # Returns None
        return 0
    elif "--verify" in sys.argv:
        # Remove the flag and delegate to verification
        sys.argv.remove("--verify")
        return verify_main() or 0
    else:
        # Run the sentence-word link functionality
        return sentence_main() or 0


if __name__ == "__main__":
    sys.exit(main())
