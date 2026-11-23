#!/usr/bin/env python3
"""Ežys entry point: native definitions for lemma translations.

"Ežys" means "hedgehog" in Lithuanian.
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.ezys.cli import main

if __name__ == "__main__":
    sys.exit(main())
