"""Polish-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


class PolishGender(Enum):
    """Polish grammatical gender."""

    MASCULINE = "m"  # ten
    FEMININE = "f"  # ta
    NEUTER = "n"  # to


@dataclass
class NounDeclension:
    """Polish noun declension results.

    Polish nouns decline through 7 cases in singular and plural,
    like Lithuanian. Each noun has a fixed grammatical gender.
    """

    word: str
    gender: Optional[PolishGender] = None
    number_type: NounNumberType = NounNumberType.REGULAR
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

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
        return any(self.forms.get(form) for form in self.SINGULAR_FORMS)

    def has_plural(self) -> bool:
        """Check if this noun has plural forms."""
        return any(self.forms.get(form) for form in self.PLURAL_FORMS)


@dataclass
class VerbConjugation:
    """Polish verb conjugation results.

    Polish verbs conjugate by person and number across multiple tenses.
    """

    word: str  # The infinitive form
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Present tense (czas teraźniejszy)
    PRESENT_FORMS = [
        "1s_present",
        "2s_present",
        "3s_present",
        "1p_present",
        "2p_present",
        "3p_present",
    ]
    # Past tense (czas przeszły)
    PAST_FORMS = [
        "1s_past",
        "2s_past",
        "3s_past",
        "1p_past",
        "2p_past",
        "3p_past",
    ]
    # Future tense (czas przyszły)
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
    """Polish adjective declension results.

    Polish adjectives agree in gender and number (4 simplified forms).
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    AGREEMENT_FORMS = [
        "singular_m",
        "singular_f",
        "plural_m",
        "plural_f",
    ]
    ALL_FORMS = AGREEMENT_FORMS
