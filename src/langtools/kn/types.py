"""Kannada-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


class KannadaGender(Enum):
    """Kannada grammatical gender."""

    MASCULINE = "masculine"  # ಪುಲ್ಲಿಂಗ
    FEMININE = "feminine"  # ಸ್ತ್ರೀಲಿಂಗ
    NEUTER = "neuter"  # ನಪುಂಸಕಲಿಂಗ


@dataclass
class NounDeclension:
    """Kannada noun declension results.

    Kannada nouns decline across 8 cases (vibhakti) and 2 numbers.
    Each noun has a fixed grammatical gender (masculine, feminine, or neuter).
    """

    word: str
    number_type: NounNumberType = NounNumberType.REGULAR
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for nouns (8 cases)
    SINGULAR_FORMS = [
        "nominative_singular",
        "accusative_singular",
        "instrumental_singular",
        "dative_singular",
        "ablative_singular",
        "genitive_singular",
        "locative_singular",
        "vocative_singular",
    ]
    PLURAL_FORMS = [
        "nominative_plural",
        "accusative_plural",
        "instrumental_plural",
        "dative_plural",
        "ablative_plural",
        "genitive_plural",
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
    """Kannada verb conjugation results.

    Kannada verbs conjugate by person, number, and gender (in 3rd person).
    For simplicity we use the standard 6-person schema.
    """

    word: str  # The dictionary form
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Present tense (ವರ್ತಮಾನಕಾಲ)
    PRESENT_FORMS = [
        "1s_present",
        "2s_present",
        "3s_present",
        "1p_present",
        "2p_present",
        "3p_present",
    ]
    # Past tense (ಭೂತಕಾಲ)
    PAST_FORMS = [
        "1s_past",
        "2s_past",
        "3s_past",
        "1p_past",
        "2p_past",
        "3p_past",
    ]
    # Future tense (ಭವಿಷ್ಯತ್ಕಾಲ)
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
class AdjectiveForms:
    """Kannada adjective form results.

    Kannada adjectives do not decline for case/number/gender.
    They have three comparative degrees: positive, comparative, superlative.
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for adjectives (comparative degrees)
    ALL_FORMS = ["positive", "comparative", "superlative"]


@dataclass
class AdverbForms:
    """Kannada adverb form results."""

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for adverbs (comparative degrees)
    ALL_FORMS = ["positive", "comparative", "superlative"]
