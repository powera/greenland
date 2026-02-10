"""Oromo-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Oromo noun form results.

    Oromo (Afaan Oromoo) nouns have grammatical gender (masculine/feminine)
    and form plurals with suffixes such as -oota, -wwan, -lee, or -an
    (e.g. nama/namoota "man/men", mana/maneen "house/houses").  The Qubee
    Latin alphabet is used for writing, with long vowels indicated by
    doubling (aa, ee, ii, oo, uu).
    """

    word: str
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
    """Oromo verb conjugation results.

    Oromo verbs conjugate for person, number, and tense.  The main tenses
    are past (simple and compound), present (habitual and progressive),
    and future.  Verbs are built from a stem with person/number suffixes
    and tense markers.
    """

    word: str  # The citation/dictionary form
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    PRESENT_FORMS = ["present"]
    PAST_FORMS = ["past"]
    FUTURE_FORMS = ["future"]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + FUTURE_FORMS
