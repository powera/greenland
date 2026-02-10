"""Romanian-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


class RomanianGender(Enum):
    """Romanian grammatical gender."""

    MASCULINE = "m"  # un/unui
    FEMININE = "f"  # o/unei
    NEUTER = "n"  # un/unui (singular like masculine, plural like feminine)


@dataclass
class NounDeclension:
    """Romanian noun declension results.

    Romanian nouns have singular and plural forms with definite article suffixes.
    Romanian has three genders: masculine, feminine, and neuter.
    Neuter nouns behave as masculine in singular and feminine in plural.
    """

    word: str
    gender: Optional[RomanianGender] = None
    number_type: NounNumberType = NounNumberType.REGULAR
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    SINGULAR_FORMS = ["singular"]
    PLURAL_FORMS = ["plural"]
    ALL_FORMS = SINGULAR_FORMS + PLURAL_FORMS

    def has_singular(self) -> bool:
        """Check if this noun has singular forms."""
        return any(self.forms.get(form) for form in self.SINGULAR_FORMS)

    def has_plural(self) -> bool:
        """Check if this noun has plural forms."""
        return any(self.forms.get(form) for form in self.PLURAL_FORMS)


@dataclass
class VerbConjugation:
    """Romanian verb conjugation results.

    Romanian verbs conjugate by person and number across multiple tenses.
    """

    word: str  # The infinitive form
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Present indicative (Prezent)
    PRESENT_FORMS = [
        "1s_present",
        "2s_present",
        "3s_present",
        "1p_present",
        "2p_present",
        "3p_present",
    ]
    # Perfect compound (Perfect compus)
    PAST_FORMS = [
        "1s_past",
        "2s_past",
        "3s_past",
        "1p_past",
        "2p_past",
        "3p_past",
    ]
    # Future (Viitor)
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
    """Romanian adjective declension results.

    Romanian adjectives agree in gender and number (4 forms).
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
