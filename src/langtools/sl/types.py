"""Slovenian-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


class SlovenianGender(Enum):
    """Slovenian grammatical gender."""

    MASCULINE = "m"
    FEMININE = "f"
    NEUTER = "n"


@dataclass
class NounDeclension:
    """Slovenian noun declension results.

    Slovenian nouns have singular and plural forms.
    Each noun has a fixed grammatical gender (masculine, feminine, or neuter).
    """

    word: str
    gender: Optional[SlovenianGender] = None
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
    """Slovenian verb conjugation results.

    Slovenian verbs conjugate by person and number across multiple tenses.
    """

    word: str  # The infinitive form
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Present (Sedanjik)
    PRESENT_FORMS = [
        "1s_present",
        "2s_present",
        "3s_present",
        "1p_present",
        "2p_present",
        "3p_present",
    ]
    # Past (Preteklik)
    PAST_FORMS = [
        "1s_past",
        "2s_past",
        "3s_past",
        "1p_past",
        "2p_past",
        "3p_past",
    ]
    # Future (Prihodnjik)
    FUTURE_FORMS = [
        "1s_future",
        "2s_future",
        "3s_future",
        "1p_future",
        "2p_future",
        "3p_future",
    ]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + FUTURE_FORMS
