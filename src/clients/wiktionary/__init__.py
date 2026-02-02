"""
Wiktionary client for fetching linguistic data.

This module provides access to Wiktionary's API for fetching grammatical forms
of words in various languages.

For language-specific parsers, see:
  - langtools.lt.wiktionary for Lithuanian
  - langtools.de.wiktionary for German

Example usage:
    from clients.wiktionary import WiktionaryClient

    # Using the base client
    client = WiktionaryClient()
    wikitext = client.fetch_page_wikitext("vilkas")
    lt_section = client.extract_language_section(wikitext, "Lithuanian")

    # For language-specific parsing, use the langtools modules:
    from langtools.lt.wiktionary import LithuanianParser
    parser = LithuanianParser()
    declensions, success = parser.get_noun_declensions("vilkas")
"""

from clients.wiktionary.client import WiktionaryClient
from clients.wiktionary.types import (
    FormResult,
    NounNumberType,
    PartOfSpeech,
    WiktionaryResult,
)
from clients.wiktionary.utils import (
    clean_form_generic,
    extract_alternative_forms,
    extract_primary_form,
    is_placeholder_text,
    normalize_text,
)

__all__ = [
    # Client classes
    "WiktionaryClient",
    # Type classes
    "FormResult",
    "NounNumberType",
    "PartOfSpeech",
    "WiktionaryResult",
    # Utility functions
    "clean_form_generic",
    "extract_alternative_forms",
    "extract_primary_form",
    "is_placeholder_text",
    "normalize_text",
]
