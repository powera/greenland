#!/usr/bin/env python3
"""Compatibility wrapper for the bootstrap exporter."""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from exports.bootstrap.exporter import (
    BootstrapExporter,
    ElniasAgent,
    SUPPORTED_LANGUAGES,
    get_argument_parser,
    main,
)

__all__ = [
    "BootstrapExporter",
    "ElniasAgent",
    "SUPPORTED_LANGUAGES",
    "get_argument_parser",
    "main",
]


if __name__ == "__main__":
    main()
