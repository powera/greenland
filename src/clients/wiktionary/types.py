"""Generic type definitions for the Wiktionary client.

Language-specific types are in langtools/<lang>/types.py
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class PartOfSpeech(Enum):
    """Parts of speech supported by Wiktionary parsing."""

    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"


class NounNumberType(Enum):
    """Number type classification for nouns."""

    REGULAR = "regular"  # Has both singular and plural forms
    PLURALE_TANTUM = "plurale_tantum"  # Only plural forms exist
    SINGULARE_TANTUM = "singulare_tantum"  # Only singular forms exist


@dataclass
class FormResult:
    """Result of looking up a single grammatical form."""

    form: str  # The form key (e.g., "nominative_singular")
    value: str  # The actual word form
    alternatives: List[str] = field(default_factory=list)  # Alternative forms


@dataclass
class WiktionaryResult:
    """Generic result from a Wiktionary lookup."""

    word: str
    language_code: str
    pos: PartOfSpeech
    forms: Dict[str, str]
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None
    raw_wikitext: Optional[str] = None
    raw_template: Optional[str] = None
