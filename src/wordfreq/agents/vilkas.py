#!/usr/bin/env python3
"""
Vilkas - Lithuanian Word Forms Checker Agent

This is a compatibility wrapper that imports from the refactored vilkas package.
The actual implementation is in wordfreq/agents/vilkas/

"Vilkas" means "wolf" in Lithuanian - a watchful guardian of the word database.
"""

from wordfreq.agents.vilkas.agent import VilkasAgent
from wordfreq.agents.vilkas.cli import main

__all__ = ['VilkasAgent', 'main']

if __name__ == '__main__':
    main()
