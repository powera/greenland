#!/usr/bin/env python3
"""
Lokys - English Lemma Validation Agent

This is a compatibility wrapper that imports from the refactored lokys package.
The actual implementation is in agents/lokys/

"Lokys" means "bear" in Lithuanian - thorough and careful in checking quality.

This agent validates English lemma forms, definitions, and other properties.
"""

# Add src directory to path
import sys
from pathlib import Path

GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.lokys.agent import LokysAgent
from agents.lokys.cli import main

__all__ = ["LokysAgent", "main"]

if __name__ == "__main__":
    main()
