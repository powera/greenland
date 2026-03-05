"""Sentence-level capability handlers."""

from workqueue.handlers.sentences.translation import (
    do_translate_sentence,
    handle_sentences_translate,
)

__all__ = ["do_translate_sentence", "handle_sentences_translate"]
