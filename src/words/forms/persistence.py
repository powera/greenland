"""Store generated forms and grammar facts, gating uncertain model answers."""

import logging
from typing import Dict, Optional, Set, Tuple

from sqlalchemy.orm import Session

from storage import database as linguistic_db
from storage.crud.operation_log import log_operation
from storage.crud.uncertain_llm_result import LLMQuestion, confidence_gated
from storage.models.uncertain_llm_result import TOPIC_FORMS
from words.forms.config import FormGenerationConfig
from words.forms.traits import detect_number_type_from_forms, extract_gender_from_forms

logger = logging.getLogger(__name__)


def _existing_form_values(
    session: Session, lemma_id: int, form_config: FormGenerationConfig
) -> Set[str]:
    """Grammatical-form values this lemma already has in the config's language."""
    existing_forms = (
        session.query(linguistic_db.DerivativeForm)
        .filter(
            linguistic_db.DerivativeForm.lemma_id == lemma_id,
            linguistic_db.DerivativeForm.language_code == form_config.language_code,
        )
        .all()
    )
    return {f.grammatical_form for f in existing_forms}


def forms_already_complete(
    session: Session, lemma_id: int, form_config: FormGenerationConfig
) -> bool:
    """Whether the lemma already has at least ``min_forms_threshold`` of these forms."""
    expected_grammatical_forms = {g.value for g in form_config.form_mapping.values()}
    existing_count = len(
        _existing_form_values(session, lemma_id, form_config) & expected_grammatical_forms
    )
    return existing_count >= form_config.min_forms_threshold


_SUMMARY_FORMS = 8


def _forms_summary(forms_dict: Dict[str, str]) -> str:
    """The non-empty forms as ``name=text; ...``: the gate's value, and its note."""
    shown = [f"{name}={text.strip()}" for name, text in forms_dict.items() if text and text.strip()]
    if len(shown) > _SUMMARY_FORMS:
        return "; ".join(shown[:_SUMMARY_FORMS]) + f"; ... ({len(shown)} forms)"
    return "; ".join(shown)


def forms_uncertain(session: Session, lemma_id: int, form_config: FormGenerationConfig) -> bool:
    """Whether a model was uncertain of this lemma's forms in the config's language."""
    return store_generated_forms.is_uncertain(session, lemma_id=lemma_id, form_config=form_config)


@confidence_gated(
    question=lambda a: LLMQuestion(
        TOPIC_FORMS, a["form_config"].language_code, lemma_id=a["lemma_id"]
    ),
    value=lambda a: _forms_summary(a["forms_dict"]),
    notes_arg="notes",
)
def store_generated_forms(
    session: Session,
    lemma_id: int,
    forms_dict: Dict[str, str],
    form_config: FormGenerationConfig,
    *,
    notes: Optional[str] = None,
    confidence: Optional[float] = None,
    min_confidence: Optional[float] = None,
    model: Optional[str] = None,
) -> Optional[Tuple[int, int]]:
    """Store generated forms, and the grammar facts read off them; the caller commits.

    Shared by the live path (:func:`process_lemma_forms`) and batch completion
    (``workqueue.handlers.words.forms``).  A form the lemma already has is left
    as it is, so a form entered by hand while a batch ran stays.

    ``confidence``, ``min_confidence`` and ``model`` are for a model's answer
    (a mechanical paradigm passes none); see
    storage.crud.uncertain_llm_result.confidence_gated.  One below
    min_confidence is recorded as uncertain, with the model's ``notes``, and
    form runs then skip the lemma in that language unless told to retry.

    Returns:
        ``(forms stored, grammar facts added)``, or None for an answer below
        min_confidence.
    """
    existing_grammatical_forms = _existing_form_values(session, lemma_id, form_config)

    # Store each form
    stored = 0
    skipped = 0
    grammar_facts_added = 0
    for form_name, form_text in forms_dict.items():
        if form_name not in form_config.form_mapping:
            logger.debug(f"Unknown form name: {form_name}, skipping")
            continue

        if not form_text or not form_text.strip():
            logger.debug(f"Skipping empty form: {form_name}")
            continue

        # Check if this specific form already exists (using the set we built earlier)
        grammatical_form_enum = form_config.form_mapping[form_name].value
        if grammatical_form_enum in existing_grammatical_forms:
            logger.debug(f"Form {form_name} already exists for lemma ID {lemma_id}, skipping")
            skipped += 1
            continue

        # Get or create word token
        word_token = linguistic_db.add_word_token(session, form_text, form_config.language_code)

        # Create derivative form
        session.add(
            linguistic_db.DerivativeForm(
                lemma_id=lemma_id,
                derivative_form_text=form_text,
                word_token_id=word_token.id,
                language_code=form_config.language_code,
                grammatical_form=grammatical_form_enum,
                is_base_form=(form_name == form_config.base_form_identifier),
                verified=False,
            )
        )
        stored += 1

    # Detect and store grammatical properties
    # Detect number type (plurale_tantum, singulare_tantum) for nouns
    if form_config.detect_number_type and form_config.pos_type == "noun":
        number_type = detect_number_type_from_forms(forms_dict, form_config)
        if any(
            form_text and form_text.strip()
            for form_name, form_text in forms_dict.items()
            if "singular" in form_name.lower() or "plural" in form_name.lower()
        ):
            grammar_fact = linguistic_db.add_grammar_fact(
                session,
                lemma_id=lemma_id,
                language_code=form_config.language_code,
                fact_type="number_type",
                fact_value=number_type,
                notes=f"Detected during {form_config.pos_type} form generation",
                verified=False,
            )
            if grammar_fact:
                grammar_facts_added += 1
                logger.info(
                    f"Added grammar_fact for lemma ID {lemma_id}: number_type={number_type}"
                )
            else:
                logger.debug(
                    f"Grammar fact for number_type={number_type} already exists for lemma ID {lemma_id}"
                )

    # Extract and store grammatical gender for gendered languages
    if form_config.extract_gender:
        gender = extract_gender_from_forms(forms_dict, form_config)
        if gender:
            grammar_fact = linguistic_db.add_grammar_fact(
                session,
                lemma_id=lemma_id,
                language_code=form_config.language_code,
                fact_type="grammatical_gender",
                fact_value=gender,
                notes=f"Extracted from {form_config.pos_type} forms",
                verified=False,
            )
            if grammar_fact:
                grammar_facts_added += 1
                logger.info(f"Added grammar_fact for lemma ID {lemma_id}: gender={gender}")
            else:
                logger.debug(
                    f"Grammar fact for gender={gender} already exists for lemma ID {lemma_id}"
                )

    # Record what this run changed. Logged in the same transaction as the
    # forms themselves, so the log cannot survive a rolled-back write.
    if stored or grammar_facts_added:
        log_operation(
            session,
            operation_type="derivative_forms_generated",
            source=f"vilkas-{form_config.language_code}-{form_config.pos_type}",
            entity_type="derivative_form",
            lemma_id=lemma_id,
            details={
                "language_code": form_config.language_code,
                "pos_type": form_config.pos_type,
                "forms_added": stored,
                "forms_skipped": skipped,
                "grammar_facts_added": grammar_facts_added,
                "generator": form_config.generator_name,
            },
        )

    return stored, grammar_facts_added
