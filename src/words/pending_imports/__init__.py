"""The pending-import queue: terms staged for review, and what becomes of them.

A pending import is a term somebody wants in the database that nobody has
decided about yet. Four things stage them -- the frequency check, the document
parser (genys), the sentence import path, and a human in Barsukas -- and one
thing resolves them: approval, which creates a **lemma**, a **name**, or a
**concept** depending on ``PendingImport.target_kind``.

This package used to live in ``agents/dramblys/``, where it was reachable only
by importing an animal-named agent that had nothing else to do with it. The
modules here, in the order a term passes through them:

* :mod:`~words.pending_imports.classification` -- what should this term become?
* :mod:`~words.pending_imports.staging` -- create the row.
* :mod:`~words.pending_imports.sentence_links` -- remember which sentences are
  waiting on it.
* :mod:`~words.pending_imports.synonym_screening` -- is an existing lemma
  already covering this?
* :mod:`~words.pending_imports.approval` -- create the real thing, or reject.
* :mod:`~words.pending_imports.queries` -- read-only views of the queue.
"""

from words.pending_imports.approval import (
    approve_as_concept,
    approve_as_lemma,
    approve_as_name,
    approve_pending_import,
    delete_pending_import,
    reject_pending_import,
)
from words.pending_imports.classification import (
    DEFAULT_NAME_KIND,
    TargetKindSuggestion,
    classify_pending_import,
    is_valid_target_kind,
    looks_like_proper_noun,
    suggest_target_kind,
)
from words.pending_imports.queries import list_pending_imports
from words.pending_imports.sentence_links import (
    backfill_links_from_hints,
    count_links_for_sentence,
    link_sentence_to_pending_import,
    pending_import_ids_for_sentence,
    pending_imports_for_sentence,
    release_legacy_hints,
    resolve_sentence_links,
    sentence_ids_waiting_on,
    staged_texts_for_sentence,
)
from words.pending_imports.staging import (
    create_pending_import,
    find_pending_import,
    stage_missing_words_for_import,
)
from words.pending_imports.synonym_screening import (
    ACCEPTED_STATUS,
    ACTIVE_STATUS,
    IGNORED_STATUS,
    has_active_strong_synonym_candidate,
    ignore_synonym_candidates,
    run_synonym_screening,
)

__all__ = [
    "ACCEPTED_STATUS",
    "ACTIVE_STATUS",
    "DEFAULT_NAME_KIND",
    "IGNORED_STATUS",
    "TargetKindSuggestion",
    "approve_as_concept",
    "approve_as_lemma",
    "approve_as_name",
    "approve_pending_import",
    "backfill_links_from_hints",
    "classify_pending_import",
    "count_links_for_sentence",
    "create_pending_import",
    "delete_pending_import",
    "find_pending_import",
    "has_active_strong_synonym_candidate",
    "ignore_synonym_candidates",
    "is_valid_target_kind",
    "link_sentence_to_pending_import",
    "list_pending_imports",
    "looks_like_proper_noun",
    "pending_import_ids_for_sentence",
    "pending_imports_for_sentence",
    "reject_pending_import",
    "release_legacy_hints",
    "resolve_sentence_links",
    "run_synonym_screening",
    "sentence_ids_waiting_on",
    "stage_missing_words_for_import",
    "staged_texts_for_sentence",
    "suggest_target_kind",
]
