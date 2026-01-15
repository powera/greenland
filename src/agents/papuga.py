#!/usr/bin/env python3
"""
Papuga - Pronunciation Validation and Generation Agent

⚠️  IMPORTANT: This agent has a custom Barsukas API in src/barsukas/routes/agents.py
    If you modify the public interface of this agent, you MUST update:
    - /agents/check-pronunciations/<lemma_id> endpoint
    - /agents/generate-pronunciations/<lemma_id> endpoint
    Keep the API contract in sync to prevent runtime errors!

This is a thin wrapper that imports from the agents.papuga package.
The actual implementation is in agents/papuga/agent.py and agents/papuga/cli.py.

"Papuga" means "parrot" in Lithuanian - repeating sounds with perfect accuracy!
"""

import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

# Re-export for backwards compatibility
from agents.papuga.agent import PapugaAgent
from agents.papuga.cli import enqueue_papuga_work, get_argument_parser, main

__all__ = ["PapugaAgent", "get_argument_parser", "enqueue_papuga_work", "main"]

if __name__ == "__main__":
    main()
