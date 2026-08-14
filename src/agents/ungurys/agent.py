"""Compatibility imports for the former Ungurys export implementation."""

from exports.wireword.service import (
    MIN_WIREWORD_SENTENCE_EXPORT_COUNT,
    SUPPORTED_LANGUAGES,
    SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES,
    WirewordExportService,
)

UngurysAgent = WirewordExportService

__all__ = [
    "MIN_WIREWORD_SENTENCE_EXPORT_COUNT",
    "SUPPORTED_LANGUAGES",
    "SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES",
    "UngurysAgent",
]
