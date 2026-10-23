#!/usr/bin/env python3
"""Lape2 entry point; the original Lape remains available separately."""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.lape2.cli import main

if __name__ == "__main__":
    sys.exit(main())
