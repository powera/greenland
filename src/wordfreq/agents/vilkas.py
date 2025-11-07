#!/usr/bin/env python3
"""
Vilkas - Lithuanian Word Forms Checker Agent

This is a compatibility wrapper that imports from the refactored vilkas package.
The actual implementation is in wordfreq/agents/vilkas/

"Vilkas" means "wolf" in Lithuanian - a watchful guardian of the word database.
"""

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from wordfreq.agents.vilkas.agent import VilkasAgent
from wordfreq.agents.vilkas.cli import main

__all__ = ['VilkasAgent', 'main']

if __name__ == '__main__':
    main()
