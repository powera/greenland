#!/usr/bin/env python3
"""
Buivolas - Sentence Creation Agent

Compatibility wrapper that imports the refactored buivolas package.
"""

import sys
from pathlib import Path

GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.buivolas.agent import BuivolasAgent
from agents.buivolas.cli import main

__all__ = ["BuivolasAgent", "main"]

if __name__ == "__main__":
    main()
