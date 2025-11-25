#!/usr/bin/env python3
"""
Šernas - Synonym and Alternative Form Generator Agent

This is a compatibility wrapper that imports from the refactored šernas package.
The actual implementation is in agents/sernas/

"Šernas" means "boar" in Lithuanian - persistent in finding similar things.

Generates synonyms and alternative forms across multiple languages including English,
Lithuanian, Chinese, Korean, French, Spanish, German, Portuguese, Swahili, and Vietnamese.
"""

# Add src directory to path
import sys
from pathlib import Path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.sernas.agent import SernasAgent
from agents.sernas.cli import main

__all__ = ["SernasAgent", "main"]

if __name__ == "__main__":
    main()
