"""
Trakaido utilities package for word management and export functionality.

This package provides modular components for:
- Word management operations
- Export functionality  
- Command-line interface
- Text rendering and formatting
"""

from .cli import main
from .export_manager import TrakaidoExporter
from .word_manager import WordManager

__all__ = ["WordManager", "TrakaidoExporter", "main"]
