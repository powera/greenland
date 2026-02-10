"""Shona-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Shona noun form results.

    Shona is a Bantu language with a noun class system.  Nouns belong to
    one of several classes identified by their prefixes, which determine
    singular/plural pairing (e.g. mu-/va- for class 1/2 people:
    munhu/vanhu "person/people", chi-/zvi- for class 7/8:
    chitoro/zvitoro "shop/shops").
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
    """Shona verb conjugation results.

    Shona verbs are agglutinative, built from a root with prefixes for
    subject concord, tense markers, and object concord (e.g. ndi-no-dya
    "I eat", va-ka-end-a "they went").  The verb stem takes extensions
    for applicative (-ira), causative (-isa), passive (-wa), etc.
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
