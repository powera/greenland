"""Model adapter for backend-agnostic model access.

This module provides a unified way to access models regardless of the
backend in use (SQLite or JSONL).
"""

from typing import Any

from wordfreq.storage.backend.config import BackendType
from wordfreq.storage.backend.factory import get_backend_type


def get_models() -> Any:
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
def _get_model_class(name: str) -> Any:
    """Get a model class by name from the appropriate backend."""
    models = get_models()
    return getattr(models, name)  # type: ignore[no-any-return]


# Export commonly used model getters
def get_lemma_model() -> Any:
    """Get the Lemma model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.schema import Lemma as SQLiteLemma

        return SQLiteLemma  # type: ignore[return-value]
    else:
        from wordfreq.storage.backend.jsonl.models import Lemma as JSONLLemma

        return JSONLLemma  # type: ignore[return-value]


def get_sentence_model() -> Any:
    """Get the Sentence model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.schema import Sentence as SQLiteSentence

        return SQLiteSentence  # type: ignore[return-value]
    else:
        from wordfreq.storage.backend.jsonl.models import Sentence as JSONLSentence

        return JSONLSentence  # type: ignore[return-value]


def get_audio_quality_review_model() -> Any:
    """Get the AudioQualityReview model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.schema import AudioQualityReview as SQLiteAudioQualityReview

        return SQLiteAudioQualityReview  # type: ignore[return-value]
    else:
        from wordfreq.storage.backend.jsonl.models import (
            AudioQualityReview as JSONLAudioQualityReview,
        )

        return JSONLAudioQualityReview  # type: ignore[return-value]


def get_operation_log_model() -> Any:
    """Get the OperationLog model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.operation_log import OperationLog as SQLiteOperationLog

        return SQLiteOperationLog  # type: ignore[return-value]
    else:
        from wordfreq.storage.backend.jsonl.models import OperationLog as JSONLOperationLog

        return JSONLOperationLog  # type: ignore[return-value]


def get_guid_tombstone_model() -> Any:
    """Get the GuidTombstone model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.guid_tombstone import GuidTombstone as SQLiteGuidTombstone

        return SQLiteGuidTombstone  # type: ignore[return-value]
    else:
        from wordfreq.storage.backend.jsonl.models import GuidTombstone as JSONLGuidTombstone

        return JSONLGuidTombstone  # type: ignore[return-value]


def get_lemma_translation_model() -> Any:
    """Get the LemmaTranslation model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.schema import LemmaTranslation as SQLiteLemmaTranslation

        return SQLiteLemmaTranslation  # type: ignore[return-value]
    else:
        from wordfreq.storage.backend.jsonl.models import (
            LemmaTranslation as JSONLLemmaTranslation,
        )

        return JSONLLemmaTranslation  # type: ignore[return-value]


def get_derivative_form_model() -> Any:
    """Get the DerivativeForm model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.schema import DerivativeForm as SQLiteDerivativeForm

        return SQLiteDerivativeForm  # type: ignore[return-value]
    else:
        from wordfreq.storage.backend.jsonl.models import (
            DerivativeForm as JSONLDerivativeForm,
        )

        return JSONLDerivativeForm  # type: ignore[return-value]


def get_grammar_fact_model() -> Any:
    """Get the GrammarFact model class for the current backend."""
    backend_type = get_backend_type()
    if backend_type == BackendType.SQLITE:
        from wordfreq.storage.models.grammar_fact import GrammarFact as SQLiteGrammarFact

        return SQLiteGrammarFact  # type: ignore[return-value]
    else:
        from wordfreq.storage.backend.jsonl.models import GrammarFact as JSONLGrammarFact

        return JSONLGrammarFact  # type: ignore[return-value]
