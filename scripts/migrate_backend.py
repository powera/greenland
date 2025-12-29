#!/usr/bin/env python3
"""
DEPRECATED: This script has moved to src/wordfreq/storage/migrate.py

This wrapper exists for backward compatibility.
Please update your scripts to use the new location:
  python -m wordfreq.storage.migrate [args]
or:
  PYTHONPATH=src python src/wordfreq/storage/migrate.py [args]
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import and run the new location
from wordfreq.storage.migrate import main

if __name__ == "__main__":
    print("WARNING: scripts/migrate_backend.py is deprecated.", file=sys.stderr)
    print("Please use: python -m wordfreq.storage.migrate", file=sys.stderr)
    print("", file=sys.stderr)
    main()
