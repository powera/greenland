"""Compatibility import for the former agent-named sentence handler."""

from workqueue.handlers.sentences.translation import (
    handle_sentences_translate as handle_translate_sentence,
)

__all__ = ["handle_translate_sentence"]
