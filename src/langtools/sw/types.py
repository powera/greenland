"""Swahili-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Swahili noun form results.

    Swahili is a Bantu language with a noun class system.  Nouns belong to
    one of several classes (e.g. m-/wa- for people, ki-/vi- for things)
    and singular/plural is marked by class-specific prefixes
    (e.g. mtoto/watoto, kitabu/vitabu).
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
    """Swahili verb conjugation results.

    Swahili verbs are agglutinative, built from a root with prefixes for
    subject, tense, and object (e.g. ni-na-soma "I am reading",
    a-li-pika "he/she cooked").  We store common tense constructions
    for pedagogical purposes.
    """

    word: str  # The infinitive/dictionary form (ku- prefix)
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    PRESENT_FORMS = ["present"]
    PAST_FORMS = ["past"]
    FUTURE_FORMS = ["future"]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + FUTURE_FORMS
