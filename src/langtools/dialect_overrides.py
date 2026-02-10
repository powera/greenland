#!/usr/bin/env python3
"""
Dialect override definitions for language variants.

This module provides a centralized registry of dialect variants (e.g., zh-tw,
es-mx, pt-br) and their relationships to parent languages.  It defines:

- Parent language mappings  (zh-tw -> zh, es-mx -> es, etc.)
- Display names with dialect qualifiers for use in LLM prompts
- Text transformation functions (e.g., simplified -> traditional Chinese)
- Sort-key language inheritance (dialects typically reuse the parent's sort key)
- TTS locale codes for speech synthesis

Import from this module rather than hardcoding dialect information locally.

Usage::

    from langtools.dialect_overrides import (
        is_dialect,
        get_parent_language,
        get_dialect_display_name,
        transform_to_dialect,
    )

    if is_dialect("zh-tw"):
        parent = get_parent_language("zh-tw")   # "zh"
        name   = get_dialect_display_name("zh-tw")  # "Chinese (Taiwan Traditional)"
        text   = transform_to_dialect("zh-tw", "简体字")  # -> "簡體字"
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text transformation helpers (lazy-loaded to avoid import-time failures)
# ---------------------------------------------------------------------------


def _zh_simplified_to_traditional(text: str) -> str:
    """Convert Simplified Chinese to Traditional Chinese."""
    from langtools.zh.converter import to_traditional

    return to_traditional(text)


def _zh_traditional_to_simplified(text: str) -> str:
    """Convert Traditional Chinese to Simplified Chinese."""
    from langtools.zh.converter import to_simplified

    return to_simplified(text)


# ---------------------------------------------------------------------------
# DialectOverride dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DialectOverride:
    """Configuration for a dialect variant of a language.

    Attributes:
        parent_lang: Base language code this dialect derives from (e.g. ``"zh"``).
        display_name: Short display name (e.g. ``"Chinese (Taiwan)"``).
        dialect_display_name: Longer name suitable for LLM prompts that
            clarifies the specific variant (e.g. ``"Chinese (Taiwan Traditional)"``).
        text_transform: Optional callable that converts text **from the parent
            language** into this dialect.  For example, zh-tw's transform
            converts Simplified Chinese to Traditional Chinese.  ``None`` means
            the parent text is used as-is.
        reverse_transform: Optional callable that converts text **from this
            dialect back to the parent** language.  For example, zh-tw's
            reverse converts Traditional Chinese to Simplified.  ``None``
            means no reverse conversion is available.
        sort_key_lang: Language code whose sort-key logic should be used.
            ``None`` means inherit from *parent_lang*.
        tts_locale: BCP-47 locale tag for text-to-speech engines
            (e.g. ``"zh-TW"``, ``"es-MX"``).  ``None`` means no specific
            TTS locale is defined.
        llm_prompt_note: Optional extra instruction to include in LLM prompts
            when generating or verifying content for this dialect.
    """

    parent_lang: str
    display_name: str
    dialect_display_name: str
    text_transform: Optional[Callable[[str], str]] = field(default=None, repr=False)
    reverse_transform: Optional[Callable[[str], str]] = field(default=None, repr=False)
    sort_key_lang: Optional[str] = None
    tts_locale: Optional[str] = None
    llm_prompt_note: Optional[str] = None


# ---------------------------------------------------------------------------
# Dialect registry
# ---------------------------------------------------------------------------

DIALECT_OVERRIDES: Dict[str, DialectOverride] = {
    # Chinese (Taiwan) - Traditional characters
    "zh-tw": DialectOverride(
        parent_lang="zh",
        display_name="Chinese (Taiwan)",
        dialect_display_name="Chinese (Taiwan Traditional)",
        text_transform=_zh_simplified_to_traditional,
        reverse_transform=_zh_traditional_to_simplified,
        sort_key_lang="zh",  # pinyin sort keys work for both variants
        tts_locale="zh-TW",
        llm_prompt_note=(
            "Use Traditional Chinese characters as used in Taiwan. "
            "Do NOT use Simplified Chinese characters."
        ),
    ),
    # Spanish (Mexico) - Latin American Spanish
    "es-mx": DialectOverride(
        parent_lang="es",
        display_name="Spanish (Mexico)",
        dialect_display_name="Spanish (Mexican)",
        text_transform=None,  # text is the same script
        reverse_transform=None,
        sort_key_lang="es",
        tts_locale="es-MX",
        llm_prompt_note=(
            "Use Mexican Spanish. Prefer 'ustedes' over 'vosotros'. "
            "Use Latin American vocabulary where it differs from Castilian Spanish."
        ),
    ),
    # Portuguese (Brazil) - Brazilian Portuguese
    "pt-br": DialectOverride(
        parent_lang="pt",
        display_name="Portuguese (Brazil)",
        dialect_display_name="Portuguese (Brazilian)",
        text_transform=None,  # text is the same script
        reverse_transform=None,
        sort_key_lang="pt",
        tts_locale="pt-BR",
        llm_prompt_note=(
            "Use Brazilian Portuguese. Prefer Brazilian vocabulary and spelling "
            "conventions where they differ from European Portuguese."
        ),
    ),
    # French (Canada) - Canadian French
    "fr-ca": DialectOverride(
        parent_lang="fr",
        display_name="French (Canada)",
        dialect_display_name="French (Canadian)",
        text_transform=None,
        reverse_transform=None,
        sort_key_lang="fr",
        tts_locale="fr-CA",
        llm_prompt_note=(
            "Use Canadian French (québécois standard). Prefer Canadian vocabulary "
            "where it differs from Metropolitan French."
        ),
    ),
    # English (UK) - British English
    "en-gb": DialectOverride(
        parent_lang="en",
        display_name="English (UK)",
        dialect_display_name="English (British)",
        text_transform=None,
        reverse_transform=None,
        sort_key_lang=None,  # English has no special sort key
        tts_locale="en-GB",
        llm_prompt_note=(
            "Use British English spelling (e.g. 'colour', 'favourite', "
            "'organise') and vocabulary."
        ),
    ),
}


# Pre-computed reverse index: parent_lang -> list of dialect codes
_PARENT_TO_DIALECTS: Dict[str, List[str]] = {}
for _dialect_code, _override in DIALECT_OVERRIDES.items():
    _PARENT_TO_DIALECTS.setdefault(_override.parent_lang, []).append(_dialect_code)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_dialect(lang_code: str) -> bool:
    """Return ``True`` if *lang_code* is a registered dialect variant."""
    return lang_code in DIALECT_OVERRIDES


def get_dialect_override(lang_code: str) -> Optional[DialectOverride]:
    """Return the :class:`DialectOverride` for *lang_code*, or ``None``."""
    return DIALECT_OVERRIDES.get(lang_code)


def get_parent_language(lang_code: str) -> str:
    """Return the parent language code for a dialect, or *lang_code* itself.

    >>> get_parent_language("zh-tw")
    'zh'
    >>> get_parent_language("fr")
    'fr'
    """
    override = DIALECT_OVERRIDES.get(lang_code)
    return override.parent_lang if override else lang_code


def get_dialect_display_name(lang_code: str) -> str:
    """Return a dialect-qualified display name suitable for LLM prompts.

    Falls back to the plain language name from
    ``storage.translation_helpers.LANGUAGE_NAMES`` for non-dialect codes,
    and finally to the raw *lang_code* if nothing is found.

    >>> get_dialect_display_name("zh-tw")
    'Chinese (Taiwan Traditional)'
    >>> get_dialect_display_name("zh")
    'Chinese (Mainland Simplified)'
    """
    override = DIALECT_OVERRIDES.get(lang_code)
    if override:
        return override.dialect_display_name

    # For parent languages that have dialects, return a qualified name
    # to distinguish from the dialect variants.
    return _PARENT_DISPLAY_NAMES.get(lang_code, _language_name_fallback(lang_code))


def get_dialects_for_language(parent_lang: str) -> List[str]:
    """Return all dialect codes that derive from *parent_lang*.

    >>> get_dialects_for_language("zh")
    ['zh-tw']
    >>> get_dialects_for_language("ko")
    []
    """
    return list(_PARENT_TO_DIALECTS.get(parent_lang, []))


def get_all_dialect_codes() -> List[str]:
    """Return all registered dialect codes.

    >>> sorted(get_all_dialect_codes())
    ['en-gb', 'es-mx', 'fr-ca', 'pt-br', 'zh-tw']
    """
    return list(DIALECT_OVERRIDES.keys())


def transform_to_dialect(lang_code: str, text: str) -> str:
    """Transform *text* from the parent language into the dialect variant.

    If *lang_code* has no text transform (or is not a dialect), the original
    text is returned unchanged.

    >>> transform_to_dialect("zh-tw", "简体字")  # simplified -> traditional
    '簡體字'
    >>> transform_to_dialect("es-mx", "hola")
    'hola'
    """
    override = DIALECT_OVERRIDES.get(lang_code)
    if override and override.text_transform:
        try:
            return override.text_transform(text)
        except Exception as exc:
            logger.warning("Failed to transform text for dialect %s: %s", lang_code, exc)
    return text


def transform_from_dialect(lang_code: str, text: str) -> str:
    """Transform *text* from a dialect variant back to the parent language.

    If *lang_code* has no reverse transform (or is not a dialect), the
    original text is returned unchanged.

    >>> transform_from_dialect("zh-tw", "簡體字")  # traditional -> simplified
    '简体字'
    >>> transform_from_dialect("es-mx", "hola")
    'hola'
    """
    override = DIALECT_OVERRIDES.get(lang_code)
    if override and override.reverse_transform:
        try:
            return override.reverse_transform(text)
        except Exception as exc:
            logger.warning(
                "Failed to reverse-transform text for dialect %s: %s",
                lang_code,
                exc,
            )
    return text


def get_sort_key_language(lang_code: str) -> str:
    """Return the language code whose sort-key logic should be used.

    Dialects typically inherit their parent's sort-key algorithm.

    >>> get_sort_key_language("zh-tw")
    'zh'
    >>> get_sort_key_language("es-mx")
    'es'
    >>> get_sort_key_language("fr")
    'fr'
    """
    override = DIALECT_OVERRIDES.get(lang_code)
    if override:
        return override.sort_key_lang or override.parent_lang
    return lang_code


def get_tts_locale(lang_code: str) -> Optional[str]:
    """Return the BCP-47 TTS locale for a dialect, or ``None``.

    >>> get_tts_locale("zh-tw")
    'zh-TW'
    >>> get_tts_locale("pt-br")
    'pt-BR'
    >>> get_tts_locale("fr") is None
    True
    """
    override = DIALECT_OVERRIDES.get(lang_code)
    return override.tts_locale if override else None


def get_llm_prompt_note(lang_code: str) -> Optional[str]:
    """Return an LLM prompt note for a dialect, or ``None``.

    >>> get_llm_prompt_note("zh-tw")
    'Use Traditional Chinese characters as used in Taiwan. Do NOT use Simplified Chinese characters.'
    >>> get_llm_prompt_note("fr") is None
    True
    """
    override = DIALECT_OVERRIDES.get(lang_code)
    return override.llm_prompt_note if override else None


# ---------------------------------------------------------------------------
# Qualified display names for parent languages that have dialect variants.
# These clarify which variant the "bare" code refers to.
# ---------------------------------------------------------------------------

_PARENT_DISPLAY_NAMES: Dict[str, str] = {
    "zh": "Chinese (Mainland Simplified)",
    "es": "Spanish (Castilian)",
    "pt": "Portuguese (European)",
    "fr": "French (Metropolitan)",
    "en": "English (American)",
}


def _language_name_fallback(lang_code: str) -> str:
    """Look up the language name from translation_helpers, or return the code."""
    try:
        from storage.translation_helpers import LANGUAGE_NAMES

        return LANGUAGE_NAMES.get(lang_code, lang_code)
    except ImportError:
        return lang_code
