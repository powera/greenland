
#!/usr/bin/env python3
"""
Legacy wrapper for trakaido export utilities.

This module has been moved to wordfreq.trakaido.utils.export_manager.
Import from there instead.
"""

# Re-export for backward compatibility
from .utils.export_manager import (
    TrakaidoExporter,
    export_trakaido_data,
    write_json_file,
    get_english_word_from_lemma,
    format_subtype_display_name
)

__all__ = [
    'TrakaidoExporter',
    'export_trakaido_data', 
    'write_json_file',
    'get_english_word_from_lemma',
    'format_subtype_display_name'
]
