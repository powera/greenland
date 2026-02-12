"""Swedish-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


class SwedishGender(Enum):
    """Swedish grammatical gender."""

    COMMON = "c"  # en-words (utrum)
    NEUTER = "n"  # ett-words (neutrum)


@dataclass
class NounDeclension:
    """Swedish noun declension results.

    Swedish nouns have singular and plural forms (no case system in modern Swedish).
    Gender is indicated by the indefinite article (en/ett).
    """

    word: str
    gender: Optional[SwedishGender] = None
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
    """Swedish verb conjugation results.

    Swedish verbs do not conjugate by person — all persons use the same form
    per tense.  We store one form per tense rather than repeating it six times.
    """

    word: str  # The infinitive form
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Present (Presens) — e.g. "talar", "springer"
    PRESENT_FORMS = ["present"]
    # Past (Preteritum) — e.g. "talade", "sprang"
    PAST_FORMS = ["past"]
    # Future (Futurum) — e.g. "ska tala", "ska springa"
    FUTURE_FORMS = ["future"]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + FUTURE_FORMS
