"""Entry point for running ungurys as a module with `python -m agents.ungurys`."""

import sys

from exports.wireword.cli import main

if __name__ == "__main__":
    sys.exit(main())
