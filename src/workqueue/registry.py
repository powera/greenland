"""Handlers that execute Barsukas background tasks.

This module registers capability-first workqueue handlers and keeps aliases for
legacy task names during migration.
"""

from __future__ import annotations

from workqueue.handlers.audio import handle_audio_generate_lemma, handle_audio_generate_sentence
from workqueue.handlers.conversations import (
    handle_conversations_definitions_generate,
    handle_conversations_generate,
    handle_conversations_scene_generate,
)
from workqueue.handlers.idioms import (
    handle_idioms_equivalents_populate,
    handle_idioms_equivalents_validate,
    handle_idioms_generate,
)
from workqueue.handlers.sentences import (
    handle_sentences_batch_decompose_submit,
    handle_sentences_batch_translate_submit,
    handle_sentences_import,
    handle_sentences_import_document,
    handle_sentences_examples_generate,
    handle_sentences_patterns_generate,
    handle_sentences_translate,
    handle_sentences_translate_simple,
    handle_sentences_translate_batch_submit,
    handle_sentences_links_verify,
    handle_sentences_translations_verify,
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
    handle_words_translations_verify,
)
from workqueue.task_queue import TaskType

TASK_HANDLERS = {
    # New capability-first task names
    "words.translations": handle_words_translations,
    "words.translations.regenerate": handle_words_translations_regenerate,
    TaskType.WORDS_TRANSLATIONS_VERIFY: handle_words_translations_verify,
    "words.forms": handle_words_forms,
    "words.pronunciations": handle_words_pronunciations,
    "words.synonyms": handle_words_synonyms,
    "words.embeddings": handle_words_embeddings,
    "words.grammar_facts": handle_words_grammar_facts,
    "sentences.import": handle_sentences_import,
    "sentences.import.document": handle_sentences_import_document,
    TaskType.SENTENCES_PATTERNS_GENERATE: handle_sentences_patterns_generate,
    TaskType.SENTENCES_EXAMPLES_GENERATE: handle_sentences_examples_generate,
    "sentences.translate": handle_sentences_translate,
    TaskType.SENTENCES_TRANSLATE_SIMPLE: handle_sentences_translate_simple,
    TaskType.SENTENCES_TRANSLATIONS_VERIFY: handle_sentences_translations_verify,
    TaskType.SENTENCES_LINKS_VERIFY: handle_sentences_links_verify,
    "sentences.translate.batch_submit": handle_sentences_translate_batch_submit,
    "sentences.batch.translate.submit": handle_sentences_batch_translate_submit,
    "sentences.batch.decompose.submit": handle_sentences_batch_decompose_submit,
    "idioms.generate": handle_idioms_generate,
    "idioms.equivalents.populate": handle_idioms_equivalents_populate,
    "idioms.equivalents.validate": handle_idioms_equivalents_validate,
    "audio.generate.lemma": handle_audio_generate_lemma,
    "audio.generate.sentence": handle_audio_generate_sentence,
    TaskType.CONVERSATIONS_GENERATE: handle_conversations_generate,
    TaskType.CONVERSATIONS_SCENE_GENERATE: handle_conversations_scene_generate,
    TaskType.CONVERSATIONS_DEFINITIONS: handle_conversations_definitions_generate,
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
    "sarka_generate_conversation": handle_conversations_generate,
    "sarka_generate_definition": handle_conversations_definitions_generate,
    "conversations.definitions": handle_conversations_definitions_generate,
}
