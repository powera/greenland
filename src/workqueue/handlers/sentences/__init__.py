"""Sentence-level capability handlers."""

from workqueue.handlers.sentences.batch_decompose_submit import (
    handle_sentences_batch_decompose_submit,
)
from workqueue.handlers.sentences.batch_submit import (
    handle_sentences_translate_batch_submit,
)
from workqueue.handlers.sentences.batch_translate_submit import (
    handle_sentences_batch_translate_submit,
)
from workqueue.handlers.sentences.import_document import (
    do_import_document,
    handle_sentences_import_document,
)
from workqueue.handlers.sentences.import_workflow import (
    do_import_sentence,
    handle_sentences_import,
)
from workqueue.handlers.sentences.generation import (
    handle_sentences_examples_generate,
    handle_sentences_patterns_generate,
)
from workqueue.handlers.sentences.translation import (
    do_translate_sentence,
    handle_sentences_translate,
    handle_sentences_translate_simple,
)
from workqueue.handlers.sentences.verification import (
    handle_sentences_links_verify,
    handle_sentences_translations_verify,
)

__all__ = [
    "do_import_document",
    "do_import_sentence",
    "do_translate_sentence",
    "handle_sentences_batch_decompose_submit",
    "handle_sentences_batch_translate_submit",
    "handle_sentences_import",
    "handle_sentences_examples_generate",
    "handle_sentences_patterns_generate",
    "handle_sentences_import_document",
    "handle_sentences_translate",
    "handle_sentences_translate_simple",
    "handle_sentences_translate_batch_submit",
    "handle_sentences_links_verify",
    "handle_sentences_translations_verify",
]
