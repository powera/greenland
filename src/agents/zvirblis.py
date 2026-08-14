#!/usr/bin/env python3
"""Compatibility wrapper for sentence translation commands."""

import sys
from pathlib import Path

GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from sentences.lemma_translation_cli import ZvirblisAgent, get_argument_parser, main

__all__ = ["ZvirblisAgent", "get_argument_parser", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
