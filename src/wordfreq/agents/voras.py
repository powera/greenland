#!/usr/bin/env python3
"""
Voras - Multi-lingual Translation Validator and Populator

This is a compatibility wrapper that imports from the refactored voras package.
The actual implementation is in wordfreq/agents/voras/

"Voras" means "spider" in Lithuanian - weaving together the web of translations!
"""

from wordfreq.agents.voras.agent import VorasAgent
from wordfreq.agents.voras.cli import main

__all__ = ['VorasAgent', 'main']

if __name__ == '__main__':
    main()
