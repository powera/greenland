"""
Entry point for running bebras as a module with 'python -m agents.bebras'.
"""

import sys
from pathlib import Path

# Ensure src/ is in the path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.bebras.cli import main

if __name__ == "__main__":
    main()
