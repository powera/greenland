#!/usr/bin/env python3
"""Ungurys compatibility wrapper.

This wrapper keeps `python src/agents/ungurys.py` working while
the implementation lives in `exports/wireword/`.
"""

import sys
from pathlib import Path

GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from exports.wireword.service import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES,
    WirewordExportService,
)
from exports.wireword.cli import get_argument_parser, main

UngurysAgent = WirewordExportService

__all__ = [
    "SUPPORTED_LANGUAGES",
    "SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES",
    "UngurysAgent",
    "get_argument_parser",
    "main",
]

if __name__ == "__main__":
    main()
