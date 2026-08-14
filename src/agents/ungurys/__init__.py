"""Compatibility package for the former Ungurys export agent."""

from exports.wireword.service import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES,
    WirewordExportService,
)
from exports.wireword.cli import get_argument_parser, main

UngurysAgent = WirewordExportService

__all__ = [
    "SUPPORTED_LANGUAGES",
    "SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES",
    "UngurysAgent",
    "get_argument_parser",
    "main",
]
