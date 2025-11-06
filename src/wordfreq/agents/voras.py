#!/usr/bin/env python3
"""
Voras - Multi-lingual Translation Validator and Populator

This is a compatibility wrapper that imports from the refactored voras package.
The actual implementation is in wordfreq/agents/voras/

"Voras" means "spider" in Lithuanian - weaving together the web of translations!
"""

import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from wordfreq.agents.voras.agent import VorasAgent
from wordfreq.agents.voras.cli import main

__all__ = ['VorasAgent', 'main']

if __name__ == '__main__':
    main()
