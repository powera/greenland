"""Store a person noun's male/female words in one language, and record the check.

The one writer for every path that answers the gender question: voras's word
translation (live, batched or regenerated) and the backfill_gender_variants
script.  An answer is either a pair -- male and female words, each with its
own grammatical gender -- or none, meaning one word with one grammatical
gender serves both.  Either way the ``gender_variant_status`` grammar fact
records that the language was checked; see storage.models.variant_form.

The words land in each variant's base slot.  Their other forms (plurals) are
generated separately, as for any variant.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from langtools.form_tasks import get_base_grammatical_form
from storage.crud.grammar_fact import add_grammar_fact, delete_grammar_fact
from storage.crud.uncertain_llm_result import LLMQuestion, confidence_gated
from storage.crud.variant_form import add_variant_form, delete_variant
from storage.models.grammar_fact import GrammarFact
from storage.models.guid_prefixes import is_human_subtype
from storage.models.schema import Lemma
from clients.types import SchemaProperty
from storage.config.grammar_fact_registry import GRAMMAR_FACT_DEFINITIONS
from storage.translation_helpers import LLM_FIELD_TO_LANG_CODE, MAX_LLM_LANGUAGES_PER_OPERATION
from storage.models.variant_form import (
    GENDER_VARIANT_FEMALE,
    GENDER_VARIANT_MALE,
    GENDER_VARIANT_STATUS_FACT,
    GENDER_VARIANT_STATUS_NONE,
    GENDER_VARIANT_STATUS_PAIR,
    VARIANT_KIND_GENDER,
    VariantForm,
)

logger = logging.getLogger(__name__)

# A gender variant is one referent's word, so "common" (either gender, one
# form) does not apply to it; the lemma's own grammatical_gender fact keeps that.
VARIANT_GRAMMATICAL_GENDERS: frozenset[str] = frozenset({"masculine", "feminine", "neuter"})

# Languages with no grammatical gender at all, whatever a model says.
UNGENDERED_LANGUAGES: frozenset[str] = frozenset({"en"})

# When a model leaves a male/female word's grammatical gender empty, in a
# masculine/feminine language the man's word is masculine and the woman's
# feminine (no pair goes against it; nouns like das Mädchen are referent_gender
# lemmas, not variants).  Elsewhere it is left unknown.
MASCULINE_FEMININE_LANGUAGES: frozenset[str] = frozenset(
    GRAMMAR_FACT_DEFINITIONS["grammatical_gender"].languages
)
DERIVED_VARIANT_GENDERS: Dict[str, str] = {"male": "masculine", "female": "feminine"}

# A person noun's schema is larger per language (the gender fields), so its
# requests carry fewer languages to stay under OpenAI's schema size limit.
PERSON_NOUN_LANGUAGES_PER_REQUEST = 6


def normalize_variant_grammatical_gender(
    language_code: str, grammatical_gender: Optional[str], variant_key: Optional[str] = None
) -> Optional[str]:
    """A recognised gender for a variant word, else None (unknown or ungendered).

    With no gender given, a *variant_key* in a masculine/feminine language
    yields masculine for male and feminine for female.
    """
    if language_code in UNGENDERED_LANGUAGES:
        return None
    value = (grammatical_gender or "").strip().lower()
    if value in VARIANT_GRAMMATICAL_GENDERS:
        return value
    if variant_key is not None and language_code in MASCULINE_FEMININE_LANGUAGES:
        return DERIVED_VARIANT_GENDERS.get(variant_key)
    return None


@dataclass(frozen=True)
class GenderVariantAnswer:
    """One language's answer: both words for a pair, neither for none."""

    male: str = ""
    female: str = ""
    male_grammatical_gender: Optional[str] = None
    female_grammatical_gender: Optional[str] = None

    def _same_word(self) -> bool:
        """The same word with the same grammatical gender: one word serves both."""
        return (
            self.male.strip() == self.female.strip()
            and (self.male_grammatical_gender or "").strip().lower()
            == (self.female_grammatical_gender or "").strip().lower()
        )

    @property
    def is_pair(self) -> bool:
        return bool(self.male.strip() and self.female.strip()) and not self._same_word()

    @property
    def is_none(self) -> bool:
        both_empty = not self.male.strip() and not self.female.strip()
        return both_empty or self._same_word()

    def describe(self) -> str:
        """The answer as text, for uncertain-result notes; never empty."""
        if self.is_none:
            return GENDER_VARIANT_STATUS_NONE
        return f"{self.male.strip() or '?'} / {self.female.strip() or '?'}"


# How a language names a man and a woman in a role; the model classifies first.
GENDER_PATTERN_FIELD = "gender_pattern"
# Different words: actor / actriz.  The answer carries both.
PATTERN_SEPARATE_WORDS = "separate_words"
# One word whose grammatical gender follows the person: el / la artista.  The
# pair is that word twice, masculine and feminine, built here rather than
# trusted to the model, which often left it empty.
PATTERN_COMMON_GENDER = "common_gender"
# One word with one grammatical gender for everyone: la persona, teacher.
PATTERN_ONE_WORD = "one_word"
GENDER_PATTERNS = (PATTERN_SEPARATE_WORDS, PATTERN_COMMON_GENDER, PATTERN_ONE_WORD)


def gender_schema_properties() -> Dict[str, SchemaProperty]:
    """The fields a person noun's answer carries in each language's object.

    No descriptions: the schema repeats these for every language, and the
    prompts explain them once.  Grammatical genders are asked so a common-gender
    noun (el / la artista) is told apart from one word with one gender.
    """
    return {
        GENDER_PATTERN_FIELD: SchemaProperty("string", enum=list(GENDER_PATTERNS)),
        "male": SchemaProperty("string"),
        "female": SchemaProperty("string"),
        "male_grammatical_gender": SchemaProperty("string"),
        "female_grammatical_gender": SchemaProperty("string"),
    }


# The per-language answer fields, alongside "translation" and "confidence".
ANSWER_FIELDS = (
    GENDER_PATTERN_FIELD,
    "male",
    "female",
    "male_grammatical_gender",
    "female_grammatical_gender",
)


def _answer_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def gender_answer_from_fields(
    fields: Dict[str, Any], ordinary_word: str = ""
) -> Optional[GenderVariantAnswer]:
    """The answer in one language's response object, or None if it has no gender fields.

    ``gender_pattern`` decides when present: ``one_word`` is none whatever the
    words say, and ``common_gender`` is the language's word twice, masculine
    and feminine -- the words given, or else *ordinary_word* (the lemma's word
    in that language).
    """
    if not any(name in fields for name in ANSWER_FIELDS):
        return None
    pattern = fields.get(GENDER_PATTERN_FIELD)
    if pattern == PATTERN_ONE_WORD:
        return GenderVariantAnswer()
    if pattern == PATTERN_COMMON_GENDER:
        word = (
            _answer_text(fields.get("male")).strip()
            or _answer_text(fields.get("female")).strip()
            or ordinary_word.strip()
        )
        return GenderVariantAnswer(word, word, "masculine", "feminine") if word else None
    return GenderVariantAnswer(
        male=_answer_text(fields.get("male")),
        female=_answer_text(fields.get("female")),
        male_grammatical_gender=_answer_text(fields.get("male_grammatical_gender")) or None,
        female_grammatical_gender=_answer_text(fields.get("female_grammatical_gender")) or None,
    )


def convert_llm_response_to_gender_answers(
    llm_response: Dict[str, Any],
) -> Dict[str, GenderVariantAnswer]:
    """Gender answers by language code, from a response keyed by LLM field names.

    Only languages whose object carries the gender fields appear: a response
    to a prompt that did not ask (a non-person lemma) yields nothing.
    """
    answers: Dict[str, GenderVariantAnswer] = {}
    for field_name, value in llm_response.items():
        lang_code = LLM_FIELD_TO_LANG_CODE.get(field_name)
        if lang_code is None or not isinstance(value, dict):
            continue
        answer = gender_answer_from_fields(value, _answer_text(value.get("translation")))
        if answer is not None:
            answers[lang_code] = answer
    return answers


def get_gender_variant_status(session: Session, lemma_id: int, language_code: str) -> Optional[str]:
    """``pair``, ``none``, or None when the language has not been checked."""
    fact = (
        session.query(GrammarFact)
        .filter(
            GrammarFact.lemma_id == lemma_id,
            GrammarFact.language_code == language_code,
            GrammarFact.fact_type == GENDER_VARIANT_STATUS_FACT,
        )
        .first()
    )
    return fact.fact_value if fact is not None else None


def _gender_variant_rows(session: Session, lemma_id: int, language_code: str) -> int:
    count: int = (
        session.query(VariantForm)
        .filter(
            VariantForm.lemma_id == lemma_id,
            VariantForm.language_code == language_code,
            VariantForm.variant_kind == VARIANT_KIND_GENDER,
        )
        .count()
    )
    return count


REFERENT_GENDER_FACT = "referent_gender"


def referent_gender(lemma: Lemma) -> Optional[str]:
    """``male``/``female`` for a noun that itself names a man or a woman, else None.

    The ``referent_gender`` lemma fact is the exception list: boy, mother and
    husband have their counterparts as separate lemmas (girl, father, wife),
    not as gender variants.
    """
    for fact in lemma.lemma_facts:
        if fact.fact_type == REFERENT_GENDER_FACT and fact.fact_value:
            return str(fact.fact_value)
    return None


def languages_per_request(lemma: Lemma) -> int:
    """How many languages one translation request for *lemma* may carry."""
    if asks_gender_variants(lemma):
        return PERSON_NOUN_LANGUAGES_PER_REQUEST
    return MAX_LLM_LANGUAGES_PER_OPERATION


def asks_gender_variants(lemma: Lemma) -> bool:
    """Whether a lemma takes male/female variants: a person noun not on the exception list."""
    return is_human_subtype(lemma.pos_type, lemma.pos_subtype) and referent_gender(lemma) is None


def _variant_base_word(
    session: Session, lemma_id: int, language_code: str, variant_key: str
) -> Optional[str]:
    row = (
        session.query(VariantForm)
        .filter(
            VariantForm.lemma_id == lemma_id,
            VariantForm.language_code == language_code,
            VariantForm.variant_kind == VARIANT_KIND_GENDER,
            VariantForm.variant_key == variant_key,
            VariantForm.is_base_form.is_(True),
        )
        .first()
    )
    return row.variant_form_text if row is not None else None


def needs_gender_variant_check(session: Session, lemma: Lemma, language_code: str) -> bool:
    """Whether a person noun's language has neither a status nor variant rows.

    Rows without a status were written by hand, and are left for a person to
    mark rather than asked about again.
    """
    if not asks_gender_variants(lemma):
        return False
    if get_gender_variant_status(session, lemma.id, language_code) is not None:
        return False
    return _gender_variant_rows(session, lemma.id, language_code) == 0


def base_noun_slot(language_code: str) -> str:
    """The grammatical form a variant's base word is stored under.

    A language without a modelled noun paradigm still has a citation slot.
    """
    return get_base_grammatical_form(language_code, "noun") or f"noun/{language_code}_base"


@confidence_gated(
    question=lambda a: LLMQuestion(
        GENDER_VARIANT_STATUS_FACT, a["language_code"], lemma_id=a["lemma"].id
    ),
    value=lambda a: a["answer"].describe(),
)
def store_gender_variant_answer(
    session: Session,
    lemma: Lemma,
    language_code: str,
    answer: GenderVariantAnswer,
    source: str,
    replace_existing: bool = False,
    *,
    confidence: Optional[float] = None,
    min_confidence: Optional[float] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    """Write *answer* for one language; flushes, the caller commits.

    A language already checked, or holding hand-written variant rows, is left
    alone unless ``replace_existing``, which clears both first.  An answer
    with only one of the two words is refused: a pair is both, and "none" is
    neither.

    Returns:
        The status written (``pair`` or ``none``), or None if nothing was
        written (already checked, a one-sided answer, or below confidence).

    Raises:
        ValueError: The lemma is not a person noun, or itself names a man or a
            woman (``referent_gender``).
    """
    if not is_human_subtype(lemma.pos_type, lemma.pos_subtype):
        raise ValueError(f"{lemma.guid} is not a person noun; it has no gender variants")
    if referent_gender(lemma) is not None:
        raise ValueError(
            f"{lemma.guid} names a {referent_gender(lemma)} person; no gender variants"
        )
    # Decide pair or none on the genders this language can actually hold: a
    # common-gender answer in English (tailor / tailor) is one word, not a pair.
    answer = GenderVariantAnswer(
        answer.male,
        answer.female,
        normalize_variant_grammatical_gender(language_code, answer.male_grammatical_gender),
        normalize_variant_grammatical_gender(language_code, answer.female_grammatical_gender),
    )
    if not answer.is_pair and not answer.is_none:
        logger.warning(
            "One-sided gender answer for %s (%s): %s; not stored",
            lemma.guid,
            language_code,
            answer.describe(),
        )
        return None

    if replace_existing:
        new_words = {GENDER_VARIANT_MALE: answer.male, GENDER_VARIANT_FEMALE: answer.female}
        for key, new_word in new_words.items():
            # A variant keeping its word keeps its paradigm and recordings;
            # one whose word changed or went away is removed, and with it the
            # recordings under its audio keys (storage.variant_audio).
            current = _variant_base_word(session, lemma.id, language_code, key)
            if current is not None and answer.is_pair and current == new_word.strip():
                continue
            delete_variant(
                session, lemma, key, language_code, variant_kind=VARIANT_KIND_GENDER, source=source
            )
        delete_grammar_fact(session, lemma.id, language_code, GENDER_VARIANT_STATUS_FACT)
    elif not needs_gender_variant_check(session, lemma, language_code):
        return None

    status = GENDER_VARIANT_STATUS_NONE
    if answer.is_pair:
        slot = base_noun_slot(language_code)
        for key, text, grammatical_gender in (
            (GENDER_VARIANT_MALE, answer.male, answer.male_grammatical_gender),
            (GENDER_VARIANT_FEMALE, answer.female, answer.female_grammatical_gender),
        ):
            add_variant_form(
                session,
                lemma,
                text.strip(),
                language_code,
                key,
                slot,
                variant_kind=VARIANT_KIND_GENDER,
                is_base_form=True,
                grammatical_gender=normalize_variant_grammatical_gender(
                    language_code, grammatical_gender, key
                ),
                source=source,
            )
        status = GENDER_VARIANT_STATUS_PAIR
    add_grammar_fact(session, lemma.id, language_code, GENDER_VARIANT_STATUS_FACT, status)
    return status
