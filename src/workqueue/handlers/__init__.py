"""Workqueue handlers organized by capability domains."""

from workqueue.handlers.audio import handle_audio_generate_lemma, handle_audio_generate_sentence
from workqueue.handlers.conversations import (
    handle_conversations_generate,
    handle_conversations_scene_generate,
)
from workqueue.handlers.sentences import handle_sentences_translate
from workqueue.handlers.wireword import handle_wireword_export_directory
from workqueue.handlers.words import (
    handle_words_embeddings,
    handle_words_forms,
    handle_words_grammar_facts,
    handle_words_pronunciations,
    handle_words_synonyms,
    handle_words_translations,
    handle_words_translations_regenerate,
)

__all__ = [
    "handle_audio_generate_lemma",
    "handle_conversations_scene_generate",
    "handle_conversations_generate",
    "handle_words_grammar_facts",
    "handle_audio_generate_sentence",
    "handle_sentences_translate",
    "handle_words_embeddings",
    "handle_words_forms",
    "handle_words_pronunciations",
    "handle_words_synonyms",
    "handle_words_translations",
    "handle_words_translations_regenerate",
    "handle_wireword_export_directory",
]
