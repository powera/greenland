"""Chinese-specific type definitions for linguistic forms.

Chinese is an isolating (analytic) language with no inflectional morphology.
Nouns do not decline.  Grammatical relationships are expressed through word
order, particles, and separate function words.

Nouns have only a single ``base`` form.  Verbs store the bare form plus
three common aspect patterns that are essential for learners:

* **perfective** (了): completed action (买了 "bought")
* **experiential** (过): have done before (买过 "have bought before")
* **progressive** (在): currently in progress (在买 "is buying")
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Chinese noun form results.

    Chinese nouns have no grammatical number, gender, or case inflection.
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
    """Chinese verb form results.

    Chinese verbs do not conjugate morphologically, but aspect is marked
    analytically with particles.  We store the bare verb plus three common
    aspect patterns:

    * base        – bare verb (买)
    * perfective  – verb + 了 (买了) — completed action
    * experiential – verb + 过 (买过) — have done before
    * progressive – 在 + verb (在买) — currently doing
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    BASE_FORMS = ["base"]
    ASPECT_FORMS = ["perfective", "experiential", "progressive"]
    ALL_FORMS = BASE_FORMS + ASPECT_FORMS

    def has_base(self) -> bool:
        """Check if this verb has a base form."""
        return any(self.forms.get(form) for form in self.BASE_FORMS)
