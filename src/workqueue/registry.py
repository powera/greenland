"""Handlers that execute Barsukas background tasks.

This module registers capability-first workqueue handlers and keeps aliases for
legacy task names during migration.
"""

from __future__ import annotations

from workqueue.handlers.audio import handle_audio_generate_lemma, handle_audio_generate_sentence
from workqueue.handlers.sarka import handle_generate_conversation, handle_generate_definition
from workqueue.handlers.sentences import (
    handle_sentences_translate,
    handle_sentences_translate_batch_submit,
)
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

TASK_HANDLERS = {
    # New capability-first task names
    "words.translations": handle_words_translations,
    "words.translations.regenerate": handle_words_translations_regenerate,
    "words.forms": handle_words_forms,
    "words.pronunciations": handle_words_pronunciations,
    "words.synonyms": handle_words_synonyms,
    "words.embeddings": handle_words_embeddings,
    "words.grammar_facts": handle_words_grammar_facts,
    "sentences.translate": handle_sentences_translate,
    "sentences.translate.batch_submit": handle_sentences_translate_batch_submit,
    "audio.generate.lemma": handle_audio_generate_lemma,
    "audio.generate.sentence": handle_audio_generate_sentence,
    "conversations.generate": handle_generate_conversation,
    "conversations.definitions": handle_generate_definition,
    "wireword.export.directory": handle_wireword_export_directory,
    # Backward-compatible aliases (legacy snake_case)
    "add_missing_translations": handle_words_translations,
    "generate_pronunciations": handle_words_pronunciations,
    "generate_forms": handle_words_forms,
    "generate_synonyms": handle_words_synonyms,
    "generate_grammar_fact": handle_words_grammar_facts,
    "translate_sentence": handle_sentences_translate,
    "generate_audio": handle_audio_generate_lemma,
    "generate_sentence_audio": handle_audio_generate_sentence,
    # Backward-compatible aliases (agent-coupled names)
    "voras_populate_translations": handle_words_translations,
    "voras_regenerate_translations": handle_words_translations_regenerate,
    "papuga_generate_pronunciation": handle_words_pronunciations,
    "vilkas_generate_forms": handle_words_forms,
    "sernas_generate_synonyms": handle_words_synonyms,
    "word2vec_refresh_embeddings": handle_words_embeddings,
    "lape_generate_grammar_fact": handle_words_grammar_facts,
    "sarka_generate_conversation": handle_generate_conversation,
    "sarka_generate_definition": handle_generate_definition,
}
