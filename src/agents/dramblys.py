#!/usr/bin/env python3
"""
Dramblys - Missing Words Detection Agent

This is a compatibility wrapper that imports from the refactored dramblys package.
The actual implementation is in agents/dramblys/

"Dramblys" means "elephant" in Lithuanian - never forgets what's missing!
"""

import sys
from pathlib import Path
if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.dramblys.agent import DramblysAgent
from agents.dramblys.cli import main

__all__ = ["DramblysAgent", "main"]

if __name__ == "__main__":
    main()
