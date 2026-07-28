"""Typed Python wrapper around the Barsukas HTTP API.

Public entry points only — internal helpers (HTTP transport, the mirroring
decorator) live in underscore-prefixed modules and are not re-exported.

The base URL defaults to ``http://localhost:5000`` and can be overridden with
the ``BARSUKAS_API_URL`` environment variable; see :mod:`api.constants`.
"""

from __future__ import annotations

from api._http import BarsukasAPIError
from api.admin import restart as admin_restart
from api.audio import get_audio, list_voices
from api.agent_tasks import (
    check_definition,
    check_disambiguation,
    check_pronunciations,
    check_translations,
    queue_add_missing_translations,
    queue_generate_forms,
    queue_generate_pronunciations,
    queue_generate_synonyms,
    get_task,
)
from api.batch_operations import (
    find_pending_import_duplicates,
    get_level_distribution_by_pos,
    get_word_metadata,
    list_models,
    list_pending_imports,
    list_pos_subtypes,
)
from api.lemmas import (
    add_lemmas,
    get_forms,
    get_grammar,
    get_lemma,
    get_pronunciations,
    get_sentences,
    get_translations,
    get_translations_bulk,
    list_by_difficulty,
    merge_synonym,
    patch_translation_metadata,
    search,
)
from api.llm_agents import (
    add_missing_translations,
    generate_audio,
    generate_pronunciations,
    get_llm_info,
)
from api.sentences import get_sentence, get_sentence_metadata
from api.tags import (
    add_lemma_tags,
    get_lemma_tags,
    lemmas_for_tag,
    list_tags,
    remove_lemma_tags,
)

__all__ = [
    "BarsukasAPIError",
    "add_lemma_tags",
    "add_lemmas",
    "add_missing_translations",
    "admin_restart",
    "check_definition",
    "check_disambiguation",
    "check_pronunciations",
    "check_translations",
    "find_pending_import_duplicates",
    "generate_audio",
    "generate_pronunciations",
    "get_audio",
    "get_forms",
    "get_grammar",
    "get_lemma",
    "get_lemma_tags",
    "get_level_distribution_by_pos",
    "get_llm_info",
    "get_pronunciations",
    "get_sentence",
    "get_sentence_metadata",
    "get_sentences",
    "get_task",
    "get_translations",
    "get_translations_bulk",
    "get_word_metadata",
    "lemmas_for_tag",
    "list_by_difficulty",
    "list_models",
    "list_pending_imports",
    "list_pos_subtypes",
    "list_tags",
    "list_voices",
    "merge_synonym",
    "patch_translation_metadata",
    "queue_add_missing_translations",
    "queue_generate_forms",
    "queue_generate_pronunciations",
    "queue_generate_synonyms",
    "remove_lemma_tags",
    "search",
]
