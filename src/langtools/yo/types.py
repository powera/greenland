"""Yoruba-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Yoruba noun form results.

    Yoruba is an isolating language with no inflectional morphology on nouns.
    Nouns do not change form for singular/plural; plurality is typically
    expressed with àwọn (e.g. àwọn ọmọ "children") or context.  We store
    the base form and plural construction for pedagogical purposes.
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
    """Yoruba verb conjugation results.

    Yoruba verbs do not conjugate for person or number.  Tense and aspect
    are expressed through preverbal particles: ń (progressive), ti (perfect),
    máa/yóò (future).  Negation uses kò/kì.  We store the base form plus
    common tense constructions for pedagogical purposes.
    """

    word: str  # The dictionary form
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    PRESENT_FORMS = ["present"]
    PAST_FORMS = ["past"]
    FUTURE_FORMS = ["future"]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + FUTURE_FORMS
