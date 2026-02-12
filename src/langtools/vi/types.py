"""Vietnamese-specific type definitions for linguistic forms.

Vietnamese is an isolating (analytic) language with no inflectional
morphology.  Nouns do not decline and verbs do not conjugate.  Tense
and aspect are expressed through separate particles (đã, đang, sẽ,
etc.) and word order rather than changes to the word itself.

Because there is no morphological variation, each part of speech has
only a single ``base`` form equal to the dictionary entry.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Vietnamese noun form results.

    Vietnamese nouns have no grammatical number, gender, or case
    inflection.  Classifiers (con, cái, etc.) are separate words.
    The single stored form is the dictionary headword.
    """

    word: str
    number_type: NounNumberType = NounNumberType.REGULAR
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    BASE_FORMS = ["base"]
    ALL_FORMS = BASE_FORMS

    def has_base(self) -> bool:
        """Check if this noun has a base form."""
        return any(self.forms.get(form) for form in self.BASE_FORMS)


@dataclass
class VerbForms:
    """Vietnamese verb form results.

    Vietnamese verbs do not conjugate.  Tense, aspect, and mood are
    expressed analytically (đã for past, đang for progressive, sẽ for
    future, etc.).  The single stored form is the bare verb.
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    BASE_FORMS = ["base"]
    ALL_FORMS = BASE_FORMS

    def has_base(self) -> bool:
        """Check if this verb has a base form."""
        return any(self.forms.get(form) for form in self.BASE_FORMS)
