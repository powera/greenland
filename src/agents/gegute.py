#!/usr/bin/env python3
"""
Gegute - Idiom Generation and Equivalent Management Agent

This is a compatibility wrapper that imports from the gegute package.
The actual implementation is in agents/gegute/

"Gegute" means "cuckoo" in Lithuanian - a bird that places its charges in
other birds' nests, as an idiom places one language's meaning inside
another's words.
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.gegute.agent import GeguteAgent
from agents.gegute.cli import main

__all__ = ["GeguteAgent", "main"]

if __name__ == "__main__":
    sys.exit(main())
