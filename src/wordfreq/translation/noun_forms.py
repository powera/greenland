
#!/usr/bin/env python3
"""
Lithuanian noun forms generation and management.

This module handles the generation of Lithuanian noun declensions,
focusing on nominative plural forms for the wireword export system.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

@dataclass
class LithuanianNounForms:
    """Structure for Lithuanian noun forms."""
    singular_nominative: str  # Base form (vilkas)
    plural_nominative: Optional[str] = None  # vilkai
    singular_accusative: Optional[str] = None  # vilką
    plural_accusative: Optional[str] = None  # vilkus

def get_lithuanian_noun_forms(word: str, client=None, lemma_id: Optional[int] = None) -> Tuple[Dict[str, str], bool]:
    """
    Get Lithuanian noun declensions using LLM generation.

    This is the unified API entry point that matches the interface expected
    by the generate tool. This implementation uses an LLM to generate all 14
    declension forms.

    Args:
        word: The Lithuanian word to decline
        client: LinguisticClient instance (required for LLM-based generation)
        lemma_id: Optional lemma ID for database context

    Returns:
        Tuple of (dictionary mapping case names to forms, success flag)
        Forms use keys like: nominative_singular, genitive_plural, etc.
    """
    if client is None:
        raise ValueError("client parameter is required for LLM-based noun forms generation")

    # Use the client's query_lithuanian_noun_declensions method
    if lemma_id is not None:
        return client.query_lithuanian_noun_declensions(lemma_id)
    else:
        # If no lemma_id, we can't use the client method directly
        # This is a limitation of the current implementation
        raise ValueError("lemma_id is required for LLM-based noun forms generation")
