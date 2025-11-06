#!/usr/bin/env python3
"""
Dramblys - Missing Words Detection Agent

This is a compatibility wrapper that imports from the refactored dramblys package.
The actual implementation is in wordfreq/agents/dramblys/

"Dramblys" means "elephant" in Lithuanian - never forgets what's missing!
"""

from wordfreq.agents.dramblys.agent import DramblysAgent
from wordfreq.agents.dramblys.cli import main

__all__ = ['DramblysAgent', 'main']

if __name__ == '__main__':
    main()
