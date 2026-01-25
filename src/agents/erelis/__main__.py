#!/usr/bin/env python3
"""Entry point for running erelis as a module."""

import sys
from pathlib import Path

# Add src to path if needed
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.erelis.cli import main

if __name__ == "__main__":
    sys.exit(main())
