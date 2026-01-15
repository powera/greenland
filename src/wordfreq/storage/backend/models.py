"""Model access for the storage backend.

This module provides convenience imports for the SQLAlchemy models.
"""

from typing import Any, Type

from wordfreq.storage.models.schema import (
    AudioQualityReview,
    DerivativeForm,
    Lemma,
    LemmaTranslation,
    Sentence,
)
from wordfreq.storage.models.grammar_fact import GrammarFact
from wordfreq.storage.models.guid_tombstone import GuidTombstone
from wordfreq.storage.models.operation_log import OperationLog


def get_models() -> Any:
    """Get the models module.

    Returns:
        The wordfreq.storage.models module
    """
    from wordfreq.storage import models

    return models


def get_lemma_model() -> Type[Lemma]:
    """Get the Lemma model class."""
    return Lemma


def get_sentence_model() -> Type[Sentence]:
    """Get the Sentence model class."""
    return Sentence


def get_audio_quality_review_model() -> Type[AudioQualityReview]:
    """Get the AudioQualityReview model class."""
    return AudioQualityReview


def get_operation_log_model() -> Type[OperationLog]:
    """Get the OperationLog model class."""
    return OperationLog


def get_guid_tombstone_model() -> Type[GuidTombstone]:
    """Get the GuidTombstone model class."""
    return GuidTombstone


def get_lemma_translation_model() -> Type[LemmaTranslation]:
    """Get the LemmaTranslation model class."""
    return LemmaTranslation


def get_derivative_form_model() -> Type[DerivativeForm]:
    """Get the DerivativeForm model class."""
    return DerivativeForm


def get_grammar_fact_model() -> Type[GrammarFact]:
    """Get the GrammarFact model class."""
    return GrammarFact
