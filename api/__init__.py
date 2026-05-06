"""Typed Python wrapper around the Barsukas HTTP API.

Public entry points only — internal helpers (HTTP transport, the mirroring
decorator) live in underscore-prefixed modules and are not re-exported.

The base URL defaults to ``http://localhost:5000`` and can be overridden with
the ``BARSUKAS_API_URL`` environment variable; see :mod:`api.constants`.
"""

from __future__ import annotations

from api._http import BarsukasAPIError
from api.audio import get_audio
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
    search,
)
from api.llm_agents import (
    add_missing_translations,
    check_definition,
    check_disambiguation,
    check_translations,
    generate_pronunciations,
    get_llm_info,
)
from api.sentences import get_sentence_metadata

__all__ = [
    "BarsukasAPIError",
    "add_missing_translations",
    "check_definition",
    "check_disambiguation",
    "check_translations",
    "find_pending_import_duplicates",
    "generate_pronunciations",
    "get_audio",
    "get_forms",
    "get_grammar",
    "get_lemma",
    "get_llm_info",
    "get_pronunciations",
    "get_sentence_metadata",
    "get_sentences",
    "get_translations",
    "get_word_metadata",
    "list_models",
    "list_pending_imports",
    "search",
]
