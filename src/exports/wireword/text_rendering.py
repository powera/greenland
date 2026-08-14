#!/usr/bin/env python3
"""
Text rendering and formatting utilities for wireword exports.

Provides reusable functions for formatting display names and text output.
"""

from typing import Any, Optional, cast

from storage.models.enum_translations import get_subtype_display_name


def format_subtype_display_name(subtype: Optional[str], source_language: str = "en") -> str:
    """
    Convert database subtype values to display-friendly names in *source_language*.

    Args:
        subtype: Raw subtype value from database
        source_language: Source-language code (e.g. 'en', 'de', 'es', 'fr', 'zh').
            Falls back to English when the language has no entry for the subtype.

    Returns:
        Display-friendly subtype name
    """
    return cast(str, get_subtype_display_name(subtype, source_language))


def resolve_group_label(
    subtype: Optional[str], interface_language: str, session: Any | None = None
) -> str:
    """
    Resolve localized group labels for Wireword exports.

    Args:
        subtype: Raw subtype value from database (e.g. "food", "tool_machine")
        interface_language: Interface language code used by Wireword.
            For current exports this should be the source language.
        session: Optional database/session handle for future translation lookup support.

    Returns:
        Localized group label string.
    """
    _ = session
    return format_subtype_display_name(subtype, interface_language)
