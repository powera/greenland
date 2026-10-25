"""Configuration and outcomes shared by word-form workflows."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict

from storage.models.enums import GrammaticalForm


class FormsOutcome(Enum):
    """What :func:`process_lemma_forms` did with one lemma.

    Truthy exactly when the old boolean return was True (the forms are now on
    file), so callers that only test success are unchanged; a caller that
    needs to tell an uncertain answer from a failed call compares members.
    """

    WRITTEN = "written"
    ALREADY_COMPLETE = "already_complete"
    #: Answered below the confidence floor; recorded as uncertain.
    UNCERTAIN = "uncertain"
    #: A model was uncertain before and retry_uncertain was off.
    SKIPPED_UNCERTAIN = "skipped_uncertain"
    FAILED = "failed"

    def __bool__(self) -> bool:
        return self in (FormsOutcome.WRITTEN, FormsOutcome.ALREADY_COMPLETE)

    @property
    def is_uncertain(self) -> bool:
        return self in (FormsOutcome.UNCERTAIN, FormsOutcome.SKIPPED_UNCERTAIN)


@dataclass
class FormGenerationConfig:
    """Configuration for language and POS-specific form generation."""

    language_code: str  # e.g., 'fr', 'es', 'pt', 'de', 'en'
    language_name: str  # e.g., 'French', 'Spanish'
    pos_type: str  # e.g., 'noun', 'verb', 'adjective'
    form_mapping: Dict[str, GrammaticalForm]  # Maps form names to GrammaticalForm enums
    # For logs only: the langtools generator that produces the forms (see
    # langtools.form_tasks), or "query_forms" for a direct LLM query.
    generator_name: str
    min_forms_threshold: int  # Minimum number of forms to consider complete
    base_form_identifier: str  # Form name that should be marked as base form
    detect_number_type: bool = True  # Detect plurale_tantum/singulare_tantum for nouns
    extract_gender: bool = False  # Extract grammatical gender from forms (for gendered languages)
