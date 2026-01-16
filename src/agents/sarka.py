#!/usr/bin/env python3
"""
Sarka - Conversation Generator Agent

This agent generates simple conversations for the Trakaido language-learning app.
It creates dialogs using LLM prompts with curated keywords (colors, body parts,
emotions, occupations) to generate natural-sounding exchanges between two speakers.

"Sarka" means "magpie" in Lithuanian - known for being talkative and social.

Usage:
    PYTHONPATH=src python src/agents/sarka.py --generate
    PYTHONPATH=src python src/agents/sarka.py --generate --count 10
    PYTHONPATH=src python src/agents/sarka.py --view 123
"""

import sys
from pathlib import Path

GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.sarka.agent import SarkaAgent
from agents.sarka.cli import main

__all__ = ["SarkaAgent", "main"]

if __name__ == "__main__":
    main()
