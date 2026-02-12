"""Korean-specific type definitions for linguistic forms.

Korean nouns do not inflect (particles attach as separate morphemes),
but verbs and adjectives genuinely conjugate.  Korean speech levels are
central to the language; we store the 해요체 (polite informal) forms
which are the most practical for learners:

* **polite_present:** 해요체 present (먹어요)
* **polite_past:** 해요체 past (먹었어요)
* **polite_future:** 해요체 future (먹을 거예요)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Korean noun form results.

    Korean nouns have no grammatical number or gender inflection.
    Case and topic are marked by postpositional particles (은/는, 이/가,
    을/를, etc.) which are separate morphemes.  The single stored form
    is the dictionary headword.
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
class VerbConjugation:
    """Korean verb conjugation results.

    Korean verbs conjugate for tense, aspect, mood, and speech level.
    We store the three 해요체 (polite informal) tense forms, which are
    the most practical for learners:

    * polite_present – 해요체 present (e.g. 먹어요)
    * polite_past    – 해요체 past (e.g. 먹었어요)
    * polite_future  – 해요체 future (e.g. 먹을 거예요)

    Verb types:
    * Regular: follow standard 해요체 vowel-harmony rules
    * ㄹ-irregular, ㅂ-irregular, ㄷ-irregular, etc.
    * 하다 verbs: compound verbs ending in 하다
    """

    word: str  # dictionary form (사전형, ending in -다)
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    PRESENT_FORMS = ["polite_present"]
    PAST_FORMS = ["polite_past"]
    FUTURE_FORMS = ["polite_future"]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + FUTURE_FORMS
