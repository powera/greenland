#!/usr/bin/env python3
"""
Legacy wrapper for trakaido utilities.

This module has been split into multiple files in wordfreq.trakaido.utils package.
Import from the specific modules instead.
"""

import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from wordfreq.trakaido.utils.cli import main
from wordfreq.trakaido.utils.export_manager import TrakaidoExporter

# Re-export main components for backward compatibility
from wordfreq.trakaido.utils.word_manager import WordManager

__all__ = ["WordManager", "TrakaidoExporter", "main"]

# Provide a command-line entry point
if __name__ == "__main__":
    main()
