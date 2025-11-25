#!/usr/bin/env python3
"""
Vilkas - Multi-language Word Forms Checker Agent

This is a compatibility wrapper that imports from the refactored vilkas package.
The actual implementation is in agents/vilkas/

"Vilkas" means "wolf" in Lithuanian - a watchful guardian of the word database.

Supports word form generation across multiple languages including Lithuanian, French,
German, Spanish, Portuguese, and English.
"""

# Add src directory to path
import sys
from pathlib import Path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.vilkas.agent import VilkasAgent
from agents.vilkas.cli import main

__all__ = ["VilkasAgent", "main"]

if __name__ == "__main__":
    main()
