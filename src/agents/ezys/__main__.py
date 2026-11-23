"""Run Ežys with PYTHONPATH=src python -m agents.ezys."""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.ezys.cli import main

if __name__ == "__main__":
    sys.exit(main())
