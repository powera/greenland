"""
Entry point for running voras as a module with 'python -m agents.voras'.
"""

import sys
from pathlib import Path

# Ensure src/ is in the path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.voras.cli import main

if __name__ == "__main__":
    main()
