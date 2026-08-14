"""Word-level capability handlers."""

from workqueue.handlers.words.embeddings import (
    do_rebuild_embeddings,
    do_refresh_embedding,
    handle_words_embeddings,
)
from workqueue.handlers.words.forms import do_generate_forms, handle_words_forms
from workqueue.handlers.words.grammar_facts import (
    do_generate_grammar_fact,
    handle_words_grammar_facts,
)
from workqueue.handlers.words.pronunciations import (
    do_generate_pronunciations,
    handle_words_pronunciations,
)
from workqueue.handlers.words.synonyms import do_generate_synonyms, handle_words_synonyms
from workqueue.handlers.words.translations import (
    do_generate_missing_translations,
    do_regenerate_translations,
    handle_words_translations,
    handle_words_translations_regenerate,
)
from workqueue.handlers.words.verification import handle_words_translations_verify

__all__ = [
    "do_rebuild_embeddings",
    "do_refresh_embedding",
    "do_generate_forms",
    "do_generate_grammar_fact",
    "do_generate_missing_translations",
    "do_generate_pronunciations",
    "do_generate_synonyms",
    "do_regenerate_translations",
    "handle_words_embeddings",
    "handle_words_forms",
    "handle_words_grammar_facts",
    "handle_words_pronunciations",
    "handle_words_synonyms",
    "handle_words_translations",
    "handle_words_translations_regenerate",
    "handle_words_translations_verify",
]
