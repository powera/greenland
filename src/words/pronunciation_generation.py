"""Word pronunciation generation workflows.

This module implements reusable pronunciation generation logic.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple, cast

from sqlalchemy import case
from sqlalchemy.orm import Session

from words.workflow_support import build_default_config
import constants
from langtools.form_registry import FORM_SPECS
from storage.backend.config import DataSourceConfig
from storage.crud.derivative_form import (
    add_derivative_form,
    needs_pronunciation_update_filter,
    pronunciation_required_filter,
)
from storage.crud.uncertain_llm_result import LLMQuestion, confidence_gated
from storage.models.schema import (
    DerivativeForm,
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from storage.translation_helpers import (
    LANGUAGE_FIELDS,
    get_translation,
    get_translation_pronunciations,
    set_translation_pronunciations,
)
from words.llm_validators import generate_pronunciation

logger = logging.getLogger(__name__)

# The floor a generated pronunciation must meet to be stored.
PRONUNCIATION_MIN_CONFIDENCE = 0.7

# Base-form field name per POS, as it appears in a LanguageFormSpec.form_mapping.
_BASE_FORM_FIELDS: Dict[str, str] = {
    "verb": "infinitive",
    "noun": "singular",
    "adjective": "positive",
    "adverb": "positive",
}


def _get_default_base_grammatical_form(pos_type: str, lang_code: str) -> str:
    """Return the canonical grammatical-form label for a synthetic base form.

    Resolves through :data:`FORM_SPECS` so the synthetic row this workflow creates
    carries the same label the forms workflow would later generate (e.g.
    ``noun/en_singular``) rather than a bare ``singular``, which produced a
    duplicate row for every lemma.  Falls back to ``"lemma"`` when the
    language has no spec for *pos_type*.
    """
    field = _BASE_FORM_FIELDS.get(pos_type)
    if field is None:
        return "lemma"
    spec = FORM_SPECS.get((lang_code, pos_type))
    if spec is None:
        return "lemma"
    form = spec.form_mapping.get(field)
    return cast(str, form.value) if form is not None else "lemma"


def get_example_sentence_for_lemma(session: Session, lemma_id: int) -> Optional[str]:
    """
    Get an example English sentence containing the lemma.

    Args:
        session: Database session
        lemma_id: ID of the lemma

    Returns:
        Example sentence text or None if not found
    """
    example_translation = (
        session.query(SentenceTranslation)
        .join(Sentence)
        .join(SentenceWord)
        .filter(
            SentenceWord.lemma_id == lemma_id,
            SentenceTranslation.language_code == "en",
        )
        .first()
    )
    return example_translation.translation_text if example_translation else None


def generate_pronunciation_for_form(
    form: DerivativeForm,
    pos_type: str,
    definition: Optional[str],
    example_sentence: Optional[str],
    english_translation: Optional[str] = None,
    model: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str], float]:
    """
    Generate pronunciation for a single derivative form.

    Args:
        form: DerivativeForm to generate pronunciation for
        pos_type: Part of speech type
        definition: English definition
        example_sentence: Example sentence for context
        model: LLM model to use (defaults to constants.DEFAULT_MODEL)

    Returns:
        Tuple of (success, ipa_pronunciation, phonetic_pronunciation, confidence)
    """
    if model is None:
        model = constants.DEFAULT_MODEL

    result = generate_pronunciation(
        word=form.derivative_form_text,
        pos_type=pos_type,
        definition=definition,
        example_sentence=example_sentence,
        model=model,
        language_code=form.language_code,
        grammatical_form=form.grammatical_form,
        english_translation=english_translation,
    )

    ipa = result.get("ipa_pronunciation")
    phonetic = result.get("phonetic_pronunciation")

    success = bool(ipa or phonetic)
    return success, ipa, phonetic, float(result.get("confidence") or 0.0)


@dataclass(frozen=True)
class PronunciationTarget:
    """One word of a lemma that needs a pronunciation, and where it goes.

    Kinds:
        ``form``: an existing DerivativeForm (``form_id``) missing one.
        ``translation``: a non-English LemmaTranslation missing one.  When the
            base form already holds both values (``known_*``) no call is needed.
        ``english_lemma``: an English lemma with no base form yet; one is
            created with the pronunciation.
    """

    kind: str
    lemma_id: int
    language_code: str
    word: str
    grammatical_form: Optional[str]
    form_id: Optional[int] = None
    known_ipa: Optional[str] = None
    known_phonetic: Optional[str] = None

    @property
    def needs_call(self) -> bool:
        return self.kind != "translation" or not (self.known_ipa and self.known_phonetic)

    def to_state(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_state(cls, state: Dict[str, Any]) -> "PronunciationTarget":
        return cls(
            kind=str(state["kind"]),
            lemma_id=int(state["lemma_id"]),
            language_code=str(state["language_code"]),
            word=str(state["word"]),
            grammatical_form=state.get("grammatical_form"),
            form_id=state.get("form_id"),
            known_ipa=state.get("known_ipa"),
            known_phonetic=state.get("known_phonetic"),
        )

    @classmethod
    def for_form(cls, form: DerivativeForm) -> "PronunciationTarget":
        return cls(
            kind="form",
            lemma_id=form.lemma_id,
            language_code=form.language_code,
            word=form.derivative_form_text,
            grammatical_form=form.grammatical_form,
            form_id=form.id,
        )

    @property
    def question_topic(self) -> str:
        """The uncertain_llm_results topic for this word's pronunciation.

        Keyed by grammatical form and word rather than ``form_id``, which a
        forms rebuild renumbers.  The grammatical form is part of it because
        homographs can be stressed differently (lt "rankos": genitive singular
        vs nominative plural).
        """
        return f"pronunciation:{self.grammatical_form or ''}:{self.word}"


def _base_form_for(
    session: Session, lemma: Lemma, language_code: str, translation_text: Optional[str]
) -> Optional[DerivativeForm]:
    """The lemma's base form in *language_code*, preferring one spelled like the translation."""
    return (
        session.query(DerivativeForm)
        .filter(
            DerivativeForm.lemma_id == lemma.id,
            DerivativeForm.language_code == language_code,
            DerivativeForm.is_base_form == True,
        )
        .order_by(
            case(
                (
                    DerivativeForm.derivative_form_text == translation_text,
                    0,
                ),
                else_=1,
            ),
            DerivativeForm.id,
        )
        .first()
    )


def plan_pronunciation_targets(
    session: Session,
    lemma: Lemma,
    language_code: str,
    base_forms_only: bool = False,
    all_forms_pronunciation: bool = False,
    retry_uncertain: bool = False,
) -> List[PronunciationTarget]:
    """Everything of *lemma* in *language_code* that needs a pronunciation, in order:
    derivative forms, then the translation, then the English base form.

    A word a model was uncertain of is left out unless *retry_uncertain*
    (a translation whose values are known from its base form needs no call,
    so it stays)."""
    targets = _all_pronunciation_targets(
        session, lemma, language_code, base_forms_only, all_forms_pronunciation
    )
    if retry_uncertain:
        return targets
    return [
        target
        for target in targets
        if not (
            target.needs_call and store_target_pronunciation.is_uncertain(session, target=target)
        )
    ]


def _all_pronunciation_targets(
    session: Session,
    lemma: Lemma,
    language_code: str,
    base_forms_only: bool,
    all_forms_pronunciation: bool,
) -> List[PronunciationTarget]:
    translation_text = get_translation(session, lemma, language_code)
    translation_ipa, translation_phonetic = get_translation_pronunciations(
        session, lemma, language_code
    )
    existing_base_form = _base_form_for(session, lemma, language_code, translation_text)
    # English pronunciation is carried by the base DerivativeForm, not by the
    # ``en`` LemmaTranslation row -- the ``english_lemma`` target is the English
    # path.  Every other language stores its pronunciation on the translation.
    translation_missing = bool(
        language_code != "en"
        and translation_text
        and (not translation_ipa or not translation_phonetic)
    )
    needs_english_lemma_pronunciation = bool(
        language_code == "en" and translation_text and existing_base_form is None
    )

    forms_query = session.query(DerivativeForm).filter(
        DerivativeForm.lemma_id == lemma.id,
        DerivativeForm.language_code == language_code,
        needs_pronunciation_update_filter(),
        pronunciation_required_filter(include_optional_forms=all_forms_pronunciation),
    )
    if base_forms_only:
        forms_query = forms_query.filter(DerivativeForm.is_base_form == True)

    targets = [
        PronunciationTarget.for_form(form) for form in forms_query.order_by(DerivativeForm.id).all()
    ]
    if translation_missing and translation_text:
        targets.append(
            PronunciationTarget(
                kind="translation",
                lemma_id=lemma.id,
                language_code=language_code,
                word=translation_text,
                grammatical_form="lemma_translation",
                known_ipa=translation_ipa
                or (existing_base_form.ipa_pronunciation if existing_base_form else None),
                known_phonetic=translation_phonetic
                or (existing_base_form.phonetic_pronunciation if existing_base_form else None),
            )
        )
    if needs_english_lemma_pronunciation and translation_text:
        targets.append(
            PronunciationTarget(
                kind="english_lemma",
                lemma_id=lemma.id,
                language_code=language_code,
                word=translation_text,
                grammatical_form=_get_default_base_grammatical_form(lemma.pos_type, language_code),
            )
        )
    return targets


def target_still_needed(session: Session, lemma: Lemma, target: PronunciationTarget) -> bool:
    """Whether *target* still lacks its pronunciation (nobody filled it meanwhile)."""
    if target.kind == "form":
        return (
            session.query(DerivativeForm)
            .filter(DerivativeForm.id == target.form_id, needs_pronunciation_update_filter())
            .first()
            is not None
        )
    if target.kind == "translation":
        ipa, phonetic = get_translation_pronunciations(session, lemma, target.language_code)
        return not ipa or not phonetic
    return _base_form_for(session, lemma, target.language_code, target.word) is None


@confidence_gated(
    question=lambda a: LLMQuestion(
        a["target"].question_topic, a["target"].language_code, lemma_id=a["target"].lemma_id
    ),
    value=lambda a: " ".join(
        value
        for value in (
            a["ipa"] or a["target"].known_ipa,
            a["phonetic"] or a["target"].known_phonetic,
        )
        if value
    ),
    min_confidence=PRONUNCIATION_MIN_CONFIDENCE,
)
def store_target_pronunciation(
    session: Session,
    lemma: Lemma,
    target: PronunciationTarget,
    ipa: Optional[str],
    phonetic: Optional[str],
    *,
    confidence: Optional[float] = None,
    min_confidence: Optional[float] = None,
    model: Optional[str] = None,
) -> Optional[bool]:
    """Write a generated (or, for a translation, known) pronunciation; the caller commits.

    Shared by the live path and batch completion.  Generated values take
    precedence over known ones.

    ``confidence``, ``min_confidence`` and ``model`` are for a model's
    answer; see storage.crud.uncertain_llm_result.confidence_gated.  One
    below min_confidence (PRONUNCIATION_MIN_CONFIDENCE by default) is
    recorded as uncertain, and plan_pronunciation_targets then skips the word.

    Returns:
        Whether anything was written; None for an answer below min_confidence.
    """
    if target.kind == "form":
        form = session.get(DerivativeForm, target.form_id)
        if form is None:
            return False
        if ipa:
            form.ipa_pronunciation = ipa
        if phonetic:
            form.phonetic_pronunciation = phonetic
        return bool(ipa or phonetic)

    if target.kind == "translation":
        ipa_value = ipa or target.known_ipa
        phonetic_value = phonetic or target.known_phonetic
        if not ipa_value and not phonetic_value:
            return False
        set_translation_pronunciations(
            session,
            lemma,
            target.language_code,
            ipa_pronunciation=ipa_value,
            phonetic_pronunciation=phonetic_value,
        )
        # If no base DerivativeForm exists yet, create one so the rhyme key
        # event listener fires and the word appears in the rhyming dictionary.
        if _base_form_for(session, lemma, target.language_code, target.word) is None:
            add_derivative_form(
                session=session,
                lemma=lemma,
                derivative_form_text=target.word,
                language_code=target.language_code,
                grammatical_form=_get_default_base_grammatical_form(
                    lemma.pos_type, target.language_code
                ),
                is_base_form=True,
                ipa_pronunciation=ipa_value,
                phonetic_pronunciation=phonetic_value,
            )
        return True

    if not ipa and not phonetic:
        return False
    add_derivative_form(
        session=session,
        lemma=lemma,
        derivative_form_text=target.word,
        language_code=target.language_code,
        grammatical_form=target.grammatical_form
        or _get_default_base_grammatical_form(lemma.pos_type, target.language_code),
        is_base_form=True,
        ipa_pronunciation=ipa,
        phonetic_pronunciation=phonetic,
    )
    return True


def pronunciation_context(session: Session, lemma: Lemma, language_code: str) -> Dict[str, Any]:
    """The context a pronunciation request for *lemma* carries."""
    return {
        "pos_type": lemma.pos_type,
        "definition": lemma.definition_text,
        "example_sentence": get_example_sentence_for_lemma(session, lemma.id),
        "english_translation": lemma.lemma_text if language_code != "en" else None,
    }


_NO_PRONUNCIATION_MESSAGES = {
    "form": "No pronunciation generated for '{word}'",
    "translation": "No pronunciation generated for lemma translation '{word}'",
    "english_lemma": "No pronunciation generated for lemma '{word}'",
}


def generate_pronunciations_for_lemma(
    session: Session,
    lemma: Lemma,
    language_code: str = "en",
    config: Optional[DataSourceConfig] = None,
    base_forms_only: bool = False,
    all_forms_pronunciation: bool = False,
    lang_code: Optional[str] = None,
    retry_uncertain: bool = False,
) -> Tuple[int, List[str]]:
    """
    Generate pronunciations for all forms of a lemma missing them.

    This is the core pronunciation generation logic shared by workers and CLIs.
    The batch path (``workqueue.handlers.words.pronunciations``) plans and
    stores through the same functions.

    Args:
        session: Database session
        lemma: Lemma to generate pronunciations for
        language_code: Language code (default: "en")
        config: DataSourceConfig (uses default if not provided)
        base_forms_only: Restrict derivative-form generation to base forms
        all_forms_pronunciation: Include optional forms (legacy behavior)
        lang_code: Deprecated payload compatibility alias for language_code
        retry_uncertain: Also ask for words a model was uncertain of before

    Returns:
        Tuple of (generated_count, list of error messages)
    """
    if config is None:
        config = build_default_config()

    effective_language_code = lang_code or language_code
    targets = plan_pronunciation_targets(
        session,
        lemma,
        effective_language_code,
        base_forms_only=base_forms_only,
        all_forms_pronunciation=all_forms_pronunciation,
        retry_uncertain=retry_uncertain,
    )
    if not targets:
        return 0, []

    context = pronunciation_context(session, lemma, effective_language_code)
    generated_count = 0
    errors: List[str] = []

    for target in targets:
        ipa: Optional[str] = None
        phonetic: Optional[str] = None
        confidence: Optional[float] = None
        if target.needs_call:
            form = (
                session.get(DerivativeForm, target.form_id)
                if target.kind == "form"
                else DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text=target.word,
                    language_code=effective_language_code,
                    grammatical_form=target.grammatical_form,
                    is_base_form=True,
                )
            )
            if form is None:
                errors.append(_NO_PRONUNCIATION_MESSAGES[target.kind].format(word=target.word))
                continue
            success, ipa, phonetic, confidence = generate_pronunciation_for_form(
                form=form,
                pos_type=lemma.pos_type,
                definition=lemma.definition_text,
                example_sentence=context["example_sentence"],
                english_translation=(
                    None if target.kind == "english_lemma" else context["english_translation"]
                ),
                model=config.model,
            )
            if not success:
                errors.append(_NO_PRONUNCIATION_MESSAGES[target.kind].format(word=target.word))
                # A failed call is not an uncertain answer; known values still apply.
                confidence = None
        stored = store_target_pronunciation(
            session, lemma, target, ipa, phonetic, confidence=confidence, model=config.model
        )
        if stored:
            generated_count += 1
        elif stored is None and confidence is not None:
            errors.append(
                f"Pronunciation of '{target.word}' below confidence ({confidence:.2f}); "
                "recorded as uncertain"
            )

    return generated_count, errors
