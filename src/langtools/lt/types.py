"""Lithuanian-specific type definitions for Wiktionary parsing."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Lithuanian noun declension results."""

    word: str
    number_type: NounNumberType
    forms: Dict[str, str]  # Maps form name to form value
    alternatives: Dict[str, List[str]] = field(default_factory=dict)  # Alternative forms
    raw_template: Optional[str] = None  # The original template text
    confidence: float = 1.0  # How confident we are in the results
    notes: Optional[str] = None

    # Expected form keys for nouns (7 cases)
    SINGULAR_FORMS = [
        "nominative_singular",
        "genitive_singular",
        "dative_singular",
        "accusative_singular",
        "instrumental_singular",
        "locative_singular",
        "vocative_singular",
    ]
    PLURAL_FORMS = [
        "nominative_plural",
        "genitive_plural",
        "dative_plural",
        "accusative_plural",
        "instrumental_plural",
        "locative_plural",
        "vocative_plural",
    ]
    ALL_FORMS = SINGULAR_FORMS + PLURAL_FORMS

    def has_singular(self) -> bool:
        """Check if this noun has singular forms."""
        return any(self.forms.get(form) for form in self.SINGULAR_FORMS if self.forms.get(form))

    def has_plural(self) -> bool:
        """Check if this noun has plural forms."""
        return any(self.forms.get(form) for form in self.PLURAL_FORMS if self.forms.get(form))


@dataclass
class VerbConjugation:
    """Lithuanian verb conjugation results."""

    word: str  # The infinitive form
    forms: Dict[str, str]  # Maps form name to form value
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for verbs (6 persons x 3 tenses = 18 forms)
    PRESENT_FORMS = [
        "1s_present",
        "2s_present",
        "3s_present",
        "1p_present",
        "2p_present",
        "3p_present",
    ]
    PAST_FORMS = [
        "1s_past",
        "2s_past",
        "3s_past",
        "1p_past",
        "2p_past",
        "3p_past",
    ]
    FUTURE_FORMS = [
        "1s_future",
        "2s_future",
        "3s_future",
        "1p_future",
        "2p_future",
        "3p_future",
    ]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + FUTURE_FORMS


@dataclass
class AdjectiveDeclension:
    """Lithuanian adjective declension results."""

    word: str
    forms: Dict[str, str]  # Maps form name to form value
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for adjectives (7 cases x 2 numbers x 2 genders = 28 forms)
    MASCULINE_SINGULAR_FORMS = [
        "nominative_singular_m",
        "genitive_singular_m",
        "dative_singular_m",
        "accusative_singular_m",
        "instrumental_singular_m",
        "locative_singular_m",
        "vocative_singular_m",
    ]
    FEMININE_SINGULAR_FORMS = [
        "nominative_singular_f",
        "genitive_singular_f",
        "dative_singular_f",
        "accusative_singular_f",
        "instrumental_singular_f",
        "locative_singular_f",
        "vocative_singular_f",
    ]
    MASCULINE_PLURAL_FORMS = [
        "nominative_plural_m",
        "genitive_plural_m",
        "dative_plural_m",
        "accusative_plural_m",
        "instrumental_plural_m",
        "locative_plural_m",
        "vocative_plural_m",
    ]
    FEMININE_PLURAL_FORMS = [
        "nominative_plural_f",
        "genitive_plural_f",
        "dative_plural_f",
        "accusative_plural_f",
        "instrumental_plural_f",
        "locative_plural_f",
        "vocative_plural_f",
    ]
    ALL_FORMS = (
        MASCULINE_SINGULAR_FORMS
        + FEMININE_SINGULAR_FORMS
        + MASCULINE_PLURAL_FORMS
        + FEMININE_PLURAL_FORMS
    )


@dataclass
class AdverbForms:
    """Lithuanian adverb form results."""

    word: str
    forms: Dict[str, str]  # Maps form name to form value
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for adverbs (comparative degrees)
    ALL_FORMS = ["positive", "comparative", "superlative"]
