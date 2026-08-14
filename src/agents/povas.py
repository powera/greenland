#!/usr/bin/env python3
"""Compatibility wrapper for POS subtype report generation."""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from exports.pos_reports.generator import (
    POSSubtypeReportGenerator,
    PovasAgent,
    get_argument_parser,
    main,
)

__all__ = [
    "POSSubtypeReportGenerator",
    "PovasAgent",
    "get_argument_parser",
    "main",
]


if __name__ == "__main__":
    main()
