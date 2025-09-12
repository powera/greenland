#!/usr/bin/env python3
"""
Legacy wrapper for trakaido utilities.

This module has been split into multiple files in wordfreq.trakaido.utils package.
Import from the specific modules instead.
"""

# Re-export main components for backward compatibility
from .utils.word_manager import WordManager
from .utils.export_manager import TrakaidoExporter
from .utils.cli import main

__all__ = ['WordManager', 'TrakaidoExporter', 'main']

# Provide a command-line entry point
if __name__ == '__main__':
    main()