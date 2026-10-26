"""The paradigms of person nouns' male/female variant words (plurals, cases).

storage.crud.gender_variant stores each gender variant's base word; this fills
in its other forms, the way vilkas fills in a lemma's own.  The lemma's own
generators are not reused: they read facts about the lemma's default word (an
irregular plural, Lithuanian gender), which do not describe "actriz".  English
is built mechanically; every other language asks the generic forms prompt
(langtools.llm_forms_base.query_forms) about the variant's word.

Run through ``GENDER_VARIANT_FORMS_JOB`` (``vilkas --gender-variants``).
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from langtools.en.inflection import build_noun_forms
from storage.crud.grammar_fact import get_grammar_fact_value
from storage.crud.uncertain_llm_result import LLMQuestion, confidence_gated
from storage.crud.variant_form import add_variant_form
from storage.models.guid_prefixes import is_human_subtype
from storage.models.schema import Lemma
from storage.models.variant_form import VARIANT_KIND_GENDER, VariantForm
from words.forms.config import FormGenerationConfig
from words.forms.tasks import FORM_GENERATION_TASKS, get_task_key

logger = logging.getLogger(__name__)

SOURCE = "vilkas/gender-variants"


def variant_forms_topic(variant_key: str) -> str:
    """The uncertain-result topic for one variant's paradigm, apart from the lemma's ``forms``."""
    return f"forms/gender/{variant_key}"


def noun_form_config(language_code: str) -> Optional[FormGenerationConfig]:
    """The noun form task's config for a language, or None if it has none."""
    try:
        return FORM_GENERATION_TASKS[get_task_key(language_code, "noun")].config
    except KeyError:
        return None


def _variant_rows(
    session: Session, lemma_id: int, language_code: str, variant_key: str
) -> List[VariantForm]:
    rows: List[VariantForm] = (
        session.query(VariantForm)
        .filter(
            VariantForm.lemma_id == lemma_id,
            VariantForm.language_code == language_code,
            VariantForm.variant_kind == VARIANT_KIND_GENDER,
            VariantForm.variant_key == variant_key,
        )
        .all()
    )
    return rows


def variant_base_row(
    session: Session, lemma_id: int, language_code: str, variant_key: str
) -> Optional[VariantForm]:
    """The variant's base-word row, or None if it has none."""
    return next(
        (
            row
            for row in _variant_rows(session, lemma_id, language_code, variant_key)
            if row.is_base_form
        ),
        None,
    )


def variant_forms_complete(
    session: Session, lemma_id: int, variant_key: str, form_config: FormGenerationConfig
) -> bool:
    """Whether the variant has the task's threshold of its forms, and more than its base word.

    A task's threshold can be 1 (English), which a lemma's own singular meets;
    a variant always starts with its base word, so that alone is not a paradigm.
    """
    expected = {form.value for form in form_config.form_mapping.values()}
    present = {
        row.grammatical_form
        for row in _variant_rows(session, lemma_id, form_config.language_code, variant_key)
    }
    return len(present & expected) >= max(form_config.min_forms_threshold, 2)


def gender_variant_form_states(
    session: Session,
    lemmas: Sequence[Lemma],
    languages: Sequence[str],
    retry_uncertain: bool = False,
) -> List[Dict[str, Any]]:
    """One item per person-noun variant whose paradigm is incomplete."""
    states: List[Dict[str, Any]] = []
    for lemma in lemmas:
        if not is_human_subtype(lemma.pos_type, lemma.pos_subtype):
            continue
        keys_by_language: Dict[str, set[str]] = {}
        for row in session.query(VariantForm).filter(
            VariantForm.lemma_id == lemma.id,
            VariantForm.variant_kind == VARIANT_KIND_GENDER,
            VariantForm.language_code.in_(list(languages)),
            VariantForm.is_base_form.is_(True),
        ):
            keys_by_language.setdefault(row.language_code, set()).add(row.variant_key)
        for language_code in languages:
            form_config = noun_form_config(language_code)
            if form_config is None:
                continue
            for variant_key in sorted(keys_by_language.get(language_code, ())):
                if variant_forms_complete(session, lemma.id, variant_key, form_config):
                    continue
                if not retry_uncertain and store_variant_forms.is_uncertain(
                    session, lemma=lemma, variant_key=variant_key, form_config=form_config
                ):
                    continue
                states.append(
                    {
                        "lemma_id": lemma.id,
                        "language_code": language_code,
                        "variant_key": variant_key,
                    }
                )
    return states


# Final words whose English plural the spelling rules get wrong (fishermans,
# childs), or get right only by luck (German/Germans vs Englishman/Englishmen).
IRREGULAR_PLURAL_HEADS = ("man", "child", "person", "wife", "life", "self")


def _may_have_irregular_plural(word: str) -> bool:
    head = word.strip().lower().split()[-1] if word.strip() else ""
    return any(head.endswith(ending) for ending in IRREGULAR_PLURAL_HEADS)


def mechanical_variant_forms(
    session: Session, lemma: Lemma, language_code: str, word: str
) -> Optional[Dict[str, str]]:
    """A paradigm built without a model, or None to ask one.

    English only, and only for a word the spelling rules can be trusted with.
    build_noun_forms is exact only given the word's own irregular plural, which
    is a stored fact about the lemma's default word ("fishermen"), not about
    its counterpart ("fisherwoman").  So a counterpart that may be irregular,
    or one whose lemma's own plural is irregular, goes to the model, whose
    answer is gated on confidence.  Countability is a property of the concept,
    so the lemma's is used.
    """
    if language_code != "en" or _may_have_irregular_plural(word):
        return None
    if get_grammar_fact_value(session, lemma.id, "en", "plural"):
        return None
    countability = get_grammar_fact_value(session, lemma.id, "en", "countability")
    return build_noun_forms(word, countability=countability)


def _forms_summary(forms_dict: Dict[str, str]) -> str:
    return "; ".join(f"{name}={text.strip()}" for name, text in forms_dict.items() if text)


@confidence_gated(
    question=lambda a: LLMQuestion(
        variant_forms_topic(a["variant_key"]),
        a["form_config"].language_code,
        lemma_id=a["lemma"].id,
    ),
    value=lambda a: _forms_summary(a["forms_dict"]),
    notes_arg="notes",
)
def store_variant_forms(
    session: Session,
    lemma: Lemma,
    variant_key: str,
    forms_dict: Dict[str, str],
    form_config: FormGenerationConfig,
    *,
    notes: Optional[str] = None,
    confidence: Optional[float] = None,
    min_confidence: Optional[float] = None,
    model: Optional[str] = None,
) -> Optional[int]:
    """Add the variant's missing forms; the caller commits.

    A form the variant already has (its base word, or one entered by hand) is
    left as it is.  Each form takes the base word's grammatical gender.

    Returns:
        Forms stored, or None for an answer below min_confidence.
    """
    language_code = form_config.language_code
    base = variant_base_row(session, lemma.id, language_code, variant_key)
    if base is None:
        logger.warning("%s %s has no %s base word", lemma.guid, language_code, variant_key)
        return 0
    present = {
        row.grammatical_form for row in _variant_rows(session, lemma.id, language_code, variant_key)
    }
    stored = 0
    for form_name, form_text in forms_dict.items():
        grammatical_form = form_config.form_mapping.get(form_name)
        if grammatical_form is None or not form_text or not form_text.strip():
            continue
        if grammatical_form.value in present:
            continue
        add_variant_form(
            session,
            lemma,
            form_text.strip(),
            language_code,
            variant_key,
            grammatical_form.value,
            variant_kind=VARIANT_KIND_GENDER,
            is_base_form=False,
            grammatical_gender=base.grammatical_gender,
            source=SOURCE,
        )
        stored += 1
    return stored
