"""Entry point for running Sarka agent as a module."""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.sarka.cli import main

if __name__ == "__main__":
    main()
