#!/usr/bin/env python3
"""
Genys - Document Parser and Pending Import Stager

Compatibility wrapper for agents/genys package.
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.genys.agent import GenysAgent
from agents.genys.cli import main

__all__ = ["GenysAgent", "main"]

if __name__ == "__main__":
    main()
