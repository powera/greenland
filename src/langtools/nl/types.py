"""Dutch-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


class DutchGender(Enum):
    """Dutch grammatical gender."""

    COMMON = "c"  # de-words (common gender)
    NEUTER = "n"  # het-words (neuter gender)


@dataclass
class NounDeclension:
    """Dutch noun declension results.

    Dutch nouns have singular and plural forms (no case system).
    Gender is indicated by the article (de/het).
    """

    word: str
    gender: Optional[DutchGender] = None
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
    """Dutch verb conjugation results.

    Dutch verbs conjugate by person in present and past tenses.
    """

    word: str  # The infinitive form
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Present (Onvoltooid tegenwoordige tijd)
    PRESENT_FORMS = [
        "1s_present",
        "2s_present",
        "3s_present",
        "1p_present",
        "2p_present",
        "3p_present",
    ]
    # Past (Onvoltooid verleden tijd)
    PAST_FORMS = [
        "1s_past",
        "2s_past",
        "3s_past",
        "1p_past",
        "2p_past",
        "3p_past",
    ]
    # Future (zal/zullen + infinitive)
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
    """Dutch adjective declension results.

    Dutch adjectives agree in gender and number.
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
