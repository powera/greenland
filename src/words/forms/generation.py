"""Generate and persist forms for one lemma using language-specific generators."""

import logging
import time

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from langtools.form_tasks import generate_forms
from langtools.llm_forms_base import forms_answer_confidence, forms_answer_notes
from storage import database as linguistic_db
from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from words.linguistic_client import LinguisticClient
from words.forms.config import FormGenerationConfig, FormsOutcome
from words.forms.persistence import forms_already_complete, forms_uncertain, store_generated_forms

logger = logging.getLogger(__name__)

# Retry settings for transient SQLite errors (e.g., database locked).
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0


def _commit_with_retry(session: Session, lemma_id: int) -> None:
    """Commit with retry logic for transient SQLite errors (e.g., database locked)."""
    for attempt in range(MAX_RETRIES):
        try:
            session.commit()
            return
        except OperationalError as e:
            session.rollback()
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    f"Database locked on commit for lemma ID {lemma_id}, "
                    f"retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                time.sleep(delay)
            else:
                raise


def process_lemma_forms(
    client: LinguisticClient,
    lemma_id: int,
    data_config: DataSourceConfig,
    form_config: FormGenerationConfig,
    retry_uncertain: bool = False,
) -> FormsOutcome:
    """
    Process and store forms for a single lemma.

    Args:
        client: LinguisticClient instance
        lemma_id: ID of the lemma to process
        data_config: DataSourceConfig with database configuration
        form_config: FormGenerationConfig with language and form settings
        retry_uncertain: Ask again where a model was uncertain of these
            forms before; by default the lemma is skipped

    Returns:
        A :class:`FormsOutcome`, truthy when the forms are on file.  An
        uncertain answer and a skipped-as-uncertain lemma are falsy but are
        not FAILED.
    """
    session = create_session(data_config)

    try:
        lemma = (
            session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
        )

        if not lemma:
            logger.error(f"Lemma ID {lemma_id} not found")
            return FormsOutcome.FAILED

        if forms_already_complete(session, lemma_id, form_config):
            logger.info(
                f"Lemma ID {lemma_id} already has {form_config.language_name} forms, skipping"
            )
            return FormsOutcome.ALREADY_COMPLETE

        if not retry_uncertain and forms_uncertain(session, lemma_id, form_config):
            logger.info(
                f"Lemma ID {lemma_id}: a model was uncertain of its "
                f"{form_config.language_name} forms, skipping (--retry-uncertain to ask again)"
            )
            return FormsOutcome.SKIPPED_UNCERTAIN

        generated = generate_forms(
            form_config.language_code,
            form_config.pos_type,
            client.client,
            lemma_id,
            client.get_session,
        )
        forms_dict, success = generated

        if not success or not forms_dict:
            logger.error(f"Failed to get forms for lemma ID {lemma_id}")
            return FormsOutcome.FAILED

        result = store_generated_forms(
            session,
            lemma_id,
            forms_dict,
            form_config,
            notes=forms_answer_notes(generated),
            confidence=forms_answer_confidence(generated),
            model=data_config.model,
        )

        # Also commits an uncertain answer's record.
        _commit_with_retry(session, lemma_id)
        if result is None:
            logger.warning(
                f"Lemma ID {lemma_id}: forms below confidence "
                f"({forms_answer_confidence(generated) or 0.0:.2f}), recorded as uncertain"
            )
            return FormsOutcome.UNCERTAIN
        logger.info(f"Added {result[0]} forms for lemma ID {lemma_id}")
        return FormsOutcome.WRITTEN

    except OperationalError as oe:
        session.rollback()
        logger.error(f"Database error processing lemma ID {lemma_id}: {oe}")
        return FormsOutcome.FAILED
    except Exception as e:
        session.rollback()
        logger.error(f"Error processing lemma ID {lemma_id}: {e}", exc_info=True)
        return FormsOutcome.FAILED
    finally:
        session.close()
