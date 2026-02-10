"""Xhosa-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Xhosa noun form results.

    Xhosa is a Bantu language with a noun class system similar to Zulu.
    Nouns belong to classes identified by their prefixes, which determine
    singular/plural pairing (e.g. um-/aba- for class 1/2 people:
    umntu/abantu "person/people", i-/ii- for class 9/10:
    inja/iinja "dog/dogs").  Xhosa also features click consonants
    (c, q, x) in its phonology.
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
    """Xhosa verb conjugation results.

    Xhosa verbs are agglutinative, built from a root with prefixes for
    subject concord, tense, and object concord (e.g. ndi-ya-dl-a
    "I am eating", ba-za-ku-hamb-a "they will go").  The verb stem takes
    various extensions for applicative, causative, passive, etc.
    """

    word: str  # The infinitive/dictionary form (uku- prefix)
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    PRESENT_FORMS = ["present"]
    PAST_FORMS = ["past"]
    FUTURE_FORMS = ["future"]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + FUTURE_FORMS
