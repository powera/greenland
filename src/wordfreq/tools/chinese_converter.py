#!/usr/bin/env python3
"""
Chinese character conversion utilities for wordfreq.

This module re-exports conversion functions from langtools.zh.converter
and provides database-aware helpers for getting Chinese translations.
"""

from typing import Any, Optional

from langtools.zh.converter import to_simplified, to_traditional
from wordfreq.storage.translation_helpers import get_translation

# Re-export for backwards compatibility
__all__ = ["to_simplified", "to_traditional", "get_chinese_translation"]


def get_chinese_translation(session: Any, lemma: Any, simplified: bool = False) -> Optional[str]:
    """
    Get Chinese translation from a lemma object.

    Args:
        session: Database session
        lemma: Lemma object
        simplified: If True, convert to Simplified Chinese; if False, return Traditional

    Returns:
        Chinese translation in requested form, or None if not available
    """
    traditional = get_translation(session, lemma, "zh")
    if not traditional:
        return None

    if simplified:
        return to_simplified(traditional)
    else:
        return traditional
