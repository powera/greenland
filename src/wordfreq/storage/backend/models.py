"""Model adapter for backend-agnostic model access.

This module provides a unified way to access models regardless of the
backend in use (SQLite or JSONL).
"""

from wordfreq.storage.backend.config import BackendType
from wordfreq.storage.backend.factory import get_backend_type


def get_models():
    """Get the appropriate models for the current backend.

    Returns:
        A module containing the model classes (Lemma, Sentence, etc.)
    """
    backend_type = get_backend_type()

    if backend_type == BackendType.SQLITE:
        from wordfreq.storage import models as sqlite_models

        return sqlite_models
    else:  # JSONL
        from wordfreq.storage.backend.jsonl import models as jsonl_models

        return jsonl_models


# Convenience imports that auto-select based on backend
def _get_model_class(name: str):
    """Get a model class by name from the appropriate backend."""
    models = get_models()
    return getattr(models, name)


# Export commonly used model getters
def get_lemma_model():
    """Get the Lemma model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.schema import Lemma

        return Lemma
    else:
        from wordfreq.storage.backend.jsonl.models import Lemma

        return Lemma


def get_sentence_model():
    """Get the Sentence model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.schema import Sentence

        return Sentence
    else:
        from wordfreq.storage.backend.jsonl.models import Sentence

        return Sentence


def get_audio_quality_review_model():
    """Get the AudioQualityReview model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.schema import AudioQualityReview

        return AudioQualityReview
    else:
        from wordfreq.storage.backend.jsonl.models import AudioQualityReview

        return AudioQualityReview


def get_operation_log_model():
    """Get the OperationLog model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.operation_log import OperationLog

        return OperationLog
    else:
        from wordfreq.storage.backend.jsonl.models import OperationLog

        return OperationLog


def get_guid_tombstone_model():
    """Get the GuidTombstone model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.guid_tombstone import GuidTombstone

        return GuidTombstone
    else:
        from wordfreq.storage.backend.jsonl.models import GuidTombstone

        return GuidTombstone


def get_lemma_translation_model():
    """Get the LemmaTranslation model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.translations import LemmaTranslation

        return LemmaTranslation
    else:
        from wordfreq.storage.backend.jsonl.models import LemmaTranslation

        return LemmaTranslation


def get_derivative_form_model():
    """Get the DerivativeForm model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.schema import DerivativeForm

        return DerivativeForm
    else:
        from wordfreq.storage.backend.jsonl.models import DerivativeForm

        return DerivativeForm


def get_grammar_fact_model():
    """Get the GrammarFact model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.grammar_fact import GrammarFact

        return GrammarFact
    else:
        from wordfreq.storage.backend.jsonl.models import GrammarFact

        return GrammarFact
