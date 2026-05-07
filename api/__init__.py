"""Typed Python wrapper around the Barsukas HTTP API.

Public entry points only — internal helpers (HTTP transport, the mirroring
decorator) live in underscore-prefixed modules and are not re-exported.

The base URL defaults to ``http://localhost:5000`` and can be overridden with
the ``BARSUKAS_API_URL`` environment variable; see :mod:`api.constants`.
"""

from __future__ import annotations

from api._http import BarsukasAPIError
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
)
from api.batch_operations import (
    find_pending_import_duplicates,
    get_word_metadata,
    list_models,
    list_pending_imports,
)
from api.lemmas import (
    get_forms,
    get_grammar,
    get_lemma,
    get_pronunciations,
    get_sentences,
    get_translations,
    get_translations_bulk,
    list_by_difficulty,
    search,
)
from api.llm_agents import (
    add_missing_translations,
    generate_audio,
    generate_pronunciations,
    get_llm_info,
)
from api.sentences import get_sentence_metadata

__all__ = [
    "BarsukasAPIError",
    "add_missing_translations",
    "check_definition",
    "check_disambiguation",
    "check_pronunciations",
    "check_translations",
    "find_pending_import_duplicates",
    "generate_pronunciations",
    "generate_audio",
    "get_audio",
    "list_voices",
    "get_forms",
    "get_grammar",
    "get_lemma",
    "get_llm_info",
    "get_pronunciations",
    "get_sentence_metadata",
    "get_sentences",
    "get_translations",
    "get_translations_bulk",
    "get_word_metadata",
    "list_by_difficulty",
    "list_models",
    "list_pending_imports",
    "queue_add_missing_translations",
    "queue_generate_forms",
    "queue_generate_pronunciations",
    "queue_generate_synonyms",
    "search",
]
