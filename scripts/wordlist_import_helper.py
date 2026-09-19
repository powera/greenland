#!/usr/bin/env python3
"""Shared driver for the corpus-derived wordlist import scripts.

Each ``import_*_level_*.py`` script contains one or two difficulty bands, a
curated wordlist, and a docstring recording where the list came from. Everything else -- the
argument parsing, the existence preflight, the pending-queue check, the
per-word add loop, the summary -- was identical in all of them, copied twenty
times, so a fix to any of it had to be made twenty times or not at all.  It
lives here instead, and a script is now its provenance note plus a call to
:func:`run_import`.

The API facade this drives is the public ``ROOT/api`` one.  In particular
``api.lemmas.add_word`` runs Barsukas' intelligent word workflow: the server's
LLM identifies the senses and supplies their translations, then the server
selects and stores the useful ones.  A bare wordlist supplies no definition or
translation of its own.

:func:`run_term_import` is the second entry point, for lists the first one
cannot carry.  A borrowed term -- "ex post facto", "voir dire" -- has no native
English headword for sense discovery to find, so ``add_word`` invents one.
Those lists are :class:`TermEntry` rows carrying the POS, subtype and
definition, and go to ``api.lemmas.add_term``, where the server's LLM supplies
the translations only.

Without ``--execute`` the run prints its plan and makes no HTTP requests at
all, which is the state every one of these scripts is committed in.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, List, Mapping, NamedTuple, Sequence, Set

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import BarsukasAPIError
from api.batch_operations import list_pending_imports
from api.constants import BASE_URL
from api.lemmas import add_term, add_word, words_exist

DEFAULT_MODEL = "gpt-5.6-luna"

# ``POST /v1/words/exists`` caps a single request's word list, so a survey of a
# hundred-word list has to be split.  25 is well inside that cap and keeps one
# request small enough to stay readable in a log.  The scripts used to carry
# their own chunking loop -- eleven of them with a hardcoded 140, the other ten
# with none at all, which left those a few added words away from a 400.
EXISTS_BATCH_SIZE = 25


def _response_data(response: Mapping[str, Any], *, operation: str) -> Any:
    if "data" not in response:
        raise RuntimeError(f"{operation} returned no data: {response!r}")
    return response["data"]


def _created_guids(response: Mapping[str, Any], *, word: str) -> List[str]:
    """The GUIDs ``add_word`` minted, or an empty list if it minted none."""
    response_data = _response_data(response, operation=f"adding {word!r}")
    if not isinstance(response_data, dict):
        raise RuntimeError(f"Adding {word!r} returned invalid data: {response_data!r}")

    raw_senses = response_data.get("senses", [])
    if not isinstance(raw_senses, list):
        raise RuntimeError(f"Adding {word!r} returned invalid senses: {raw_senses!r}")

    created_guids: List[str] = []
    for raw_sense in raw_senses:
        if not isinstance(raw_sense, dict):
            raise RuntimeError(f"Adding {word!r} returned an invalid sense: {raw_sense!r}")
        guid = raw_sense.get("guid")
        if isinstance(guid, str) and guid:
            created_guids.append(guid)
    return created_guids


def check_words_exist(words: Sequence[str]) -> dict[str, bool]:
    """Which of ``words`` the database already accounts for.

    Batches to :data:`EXISTS_BATCH_SIZE` and merges the results, because the
    endpoint caps one request's list and these wordlists run past it.

    Args:
        words: The words to survey.

    Returns:
        Each word mapped to whether the database accounts for it -- as a lemma,
        a disambiguated lemma, an English derivative form or an alternate
        spelling.
    """
    existence_data: dict[str, bool] = {}
    for start in range(0, len(words), EXISTS_BATCH_SIZE):
        batch = list(words[start : start + EXISTS_BATCH_SIZE])
        response = words_exist(batch, include_exclusions=True)
        batch_data = _response_data(response, operation="checking existing words")
        if not isinstance(batch_data, dict):
            raise RuntimeError(f"Existence check returned invalid data: {batch_data!r}")
        existence_data.update(batch_data)
    return existence_data


def pending_queue_words() -> Set[str]:
    """Every ``english_word`` currently sitting in the pending-import queue.

    ``words_exist`` deliberately does not consult this queue -- it reports what
    the database *accounts for* (lemma, disambiguated lemma, English derivative
    form, alternate spelling), and a pending row is none of those.  But a word
    whose senses were all diverted to review would otherwise be re-sent to the
    LLM on the next run and paid for again, only for the server to drop the
    result as a duplicate.  Filter it out here instead.
    """
    pending_words: Set[str] = set()
    page = 1
    while True:
        response = list_pending_imports(target_kind="lemma", page=page)
        rows = _response_data(response, operation="listing pending imports")
        if not isinstance(rows, list):
            raise RuntimeError(f"Pending-import listing returned invalid data: {rows!r}")
        for row in rows:
            if isinstance(row, dict):
                english_word = row.get("english_word")
                if isinstance(english_word, str) and english_word.strip():
                    pending_words.add(english_word.strip().lower())

        metadata = response.get("metadata") if isinstance(response, Mapping) else None
        total_pages = metadata.get("total_pages", 1) if isinstance(metadata, Mapping) else 1
        if not isinstance(total_pages, int) or page >= total_pages:
            return pending_words
        page += 1


def parse_args(description: str) -> argparse.Namespace:
    """The argument parser every one of these scripts shares."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Barsukas LLM model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Make the live, paid API calls. Without this flag, only print the plan.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Import at most this many currently unlinked words.",
    )
    return parser.parse_args()


def print_plan(words: Sequence[str], level: int) -> None:
    print(f"Barsukas: {BASE_URL}")
    print(f"Target level: {level}")
    print(f"Curated words: {len(words)}")
    for rank, word in enumerate(words, start=1):
        print(f"{rank:3}. {word}")


def execute_assignments(
    assignments: Sequence[tuple[str, int]], model: str, limit: int | None
) -> None:
    """Import ranked ``(word, level)`` assignments, skipping known words."""
    if limit is not None and limit < 1:
        raise RuntimeError("--limit must be at least 1")

    words = [word for word, _level in assignments]
    level_by_word = {word: level for word, level in assignments}
    if len(level_by_word) != len(words):
        raise RuntimeError("A wordlist import assigns the same word more than once")
    existence_data = check_words_exist(words)
    queued = pending_queue_words()

    unaccounted_words = [word for word in words if not bool(existence_data.get(word, False))]
    queued_words = [word for word in unaccounted_words if word in queued]
    all_missing_words = [word for word in unaccounted_words if word not in queued]
    words_to_add = all_missing_words[:limit] if limit is not None else all_missing_words
    existing_count = len(words) - len(unaccounted_words)
    print(
        f"Preflight: {existing_count} already accounted for; "
        f"{len(queued_words)} awaiting review in the pending queue; "
        f"{len(all_missing_words)} missing; {len(words_to_add)} selected for this run."
    )
    if queued_words:
        print(f"  Skipping queued: {', '.join(queued_words)}")

    created_word_count = 0
    created_sense_count = 0
    pending_word_count = 0
    skipped_word_count = existing_count + len(queued_words)

    for position, word in enumerate(words_to_add, start=1):
        level = level_by_word[word]
        print(f"[{position}/{len(words_to_add)}] {word}: importing senses...", flush=True)
        # The level goes in with the word rather than in a PATCH afterwards. A
        # separate patch can fail once the lemma is already committed, and the
        # stranded lemma is then invisible to a re-run: words_exist counts it as
        # accounted for, so nothing ever sets its level.
        addition_response = add_word(word, model, difficulty_level=level)
        addition_data = _response_data(addition_response, operation=f"adding {word!r}")
        if not isinstance(addition_data, dict):
            raise RuntimeError(f"Adding {word!r} returned invalid data: {addition_data!r}")

        status = str(addition_data.get("status", "unknown"))
        created_guids = _created_guids(addition_response, word=word)

        pending_senses = addition_data.get("pending_senses", [])
        pending_count = len(pending_senses) if isinstance(pending_senses, list) else 0
        if created_guids:
            created_word_count += 1
            created_sense_count += len(created_guids)
        elif status == "pending_review":
            pending_word_count += 1
        else:
            skipped_word_count += 1

        print(
            f"  {status}: {len(created_guids)} sense(s) at level {level}, "
            f"{pending_count} pending review"
        )

    print(
        "Complete: "
        f"{created_word_count} word(s) / {created_sense_count} sense(s) created, "
        f"{pending_word_count} word(s) pending review, "
        f"{skipped_word_count} word(s) skipped."
    )


def execute(words: Sequence[str], level: int, model: str, limit: int | None) -> None:
    """Import ``words`` at one ``level``, skipping what is already accounted for."""
    execute_assignments([(word, level) for word in words], model, limit)


class TermEntry(NamedTuple):
    """One fully specified term for :func:`run_term_import`.

    Unlike a bare wordlist entry, a term carries the facts the sense-discovery
    pipeline would otherwise have to guess and would get wrong for a borrowing:
    which part of speech it is and what it means. ``pos_subtype`` may be a
    catch-all ``*_other`` -- for a Latin legal term that is usually the honest
    answer, and the terms endpoint honors it rather than queueing it.
    """

    term: str
    pos_type: str
    pos_subtype: str
    definition: str


def print_term_plan(terms: Sequence[TermEntry], level: int) -> None:
    print(f"Barsukas: {BASE_URL}")
    print(f"Target level: {level}")
    print(f"Curated terms: {len(terms)}")
    for rank, entry in enumerate(terms, start=1):
        print(f"{rank:3}. {entry.term}  [{entry.pos_type}/{entry.pos_subtype}]")
        print(f"       {entry.definition}")


def execute_terms(
    terms: Sequence[TermEntry],
    level: int,
    model: str,
    limit: int | None,
    tags: Sequence[str] | None = None,
) -> None:
    """Import fully specified ``terms`` at one ``level``.

    Shares the preflight with :func:`execute_assignments` -- the same existence
    check and pending-queue skip -- but calls ``add_term`` per entry, so the
    server generates translations only and never runs sense discovery.
    """
    if limit is not None and limit < 1:
        raise RuntimeError("--limit must be at least 1")

    term_texts = [entry.term for entry in terms]
    if len(set(term_texts)) != len(term_texts):
        raise RuntimeError("A term import lists the same term more than once")

    existence_data = check_words_exist(term_texts)
    queued = pending_queue_words()

    unaccounted = [entry for entry in terms if not bool(existence_data.get(entry.term, False))]
    queued_entries = [entry for entry in unaccounted if entry.term in queued]
    missing = [entry for entry in unaccounted if entry.term not in queued]
    to_add = missing[:limit] if limit is not None else missing
    existing_count = len(terms) - len(unaccounted)

    print(
        f"Preflight: {existing_count} already accounted for; "
        f"{len(queued_entries)} awaiting review in the pending queue; "
        f"{len(missing)} missing; {len(to_add)} selected for this run."
    )
    if queued_entries:
        print(f"  Skipping queued: {', '.join(entry.term for entry in queued_entries)}")

    created_count = 0
    skipped_count = existing_count + len(queued_entries)
    incomplete: List[str] = []

    for position, entry in enumerate(to_add, start=1):
        print(f"[{position}/{len(to_add)}] {entry.term}: translating...", flush=True)
        response = add_term(
            entry.term,
            model,
            pos_type=entry.pos_type,
            pos_subtype=entry.pos_subtype,
            definition=entry.definition,
            difficulty_level=level,
            tags=list(tags) if tags else None,
        )
        data = _response_data(response, operation=f"adding {entry.term!r}")
        if not isinstance(data, dict):
            raise RuntimeError(f"Adding {entry.term!r} returned invalid data: {data!r}")

        status = str(data.get("status", "unknown"))
        guid = data.get("guid")
        missing_languages = data.get("missing_languages") or []

        if status == "created":
            created_count += 1
        else:
            skipped_count += 1

        # A term nobody could translate is still worth having -- these are
        # wanted for tokenizing first -- but it is worth naming at the end
        # rather than leaving in the scrollback.
        if missing_languages:
            incomplete.append(f"{entry.term} (no {', '.join(missing_languages)})")

        print(f"  {status}: {guid or '-'}")

    print(f"Complete: {created_count} term(s) created, {skipped_count} skipped.")
    if incomplete:
        print(f"Incomplete translations ({len(incomplete)}):")
        for note in incomplete:
            print(f"  {note}")


def run_term_import(
    terms: Sequence[TermEntry],
    level: int,
    description: str,
    tags: Sequence[str] | None = None,
) -> int:
    """Entry point for a fully specified term import script.

    The counterpart to :func:`run_import` for terms the sense-discovery
    pipeline cannot handle. Same two-step contract: without ``--execute`` it
    prints the plan and makes no HTTP request.
    """
    args = parse_args(description)
    print_term_plan(terms, level)
    if not args.execute:
        print("\nNo API calls made. Re-run with --execute only after approval.")
        return 0

    print(f"\nLIVE MODE: Barsukas will use {args.model!r} for paid translation calls.")
    try:
        execute_terms(terms, level, args.model, args.limit, tags=tags)
    except (BarsukasAPIError, RuntimeError, requests.exceptions.RequestException) as error:
        print(f"Import stopped: {error}", file=sys.stderr)
        return 1
    return 0


def run_import(words: Sequence[str], level: int, description: str) -> int:
    """Entry point for a wordlist import script.

    Args:
        words: The curated wordlist, in the order it should be imported.
        level: The difficulty level to stamp on every sense created.
        description: The calling script's docstring, used as ``--help`` text.

    Returns:
        A process exit status: 0 on success, 1 if the import stopped early.
    """
    args = parse_args(description)
    print_plan(words, level)
    if not args.execute:
        print("\nNo API calls made. Re-run with --execute only after approval.")
        return 0

    print(f"\nLIVE MODE: Barsukas will use {args.model!r} for paid sense/translation calls.")
    try:
        execute(words, level, args.model, args.limit)
    except (BarsukasAPIError, RuntimeError, requests.exceptions.RequestException) as error:
        print(f"Import stopped: {error}", file=sys.stderr)
        return 1
    return 0


def run_domain_import(
    words: Sequence[str],
    general_words: Sequence[str],
    general_level: int,
    topic_level: int,
    description: str,
) -> int:
    """Import a reviewed domain sample generally and the remainder topically."""
    general_word_set = set(general_words)
    unknown_general_words = general_word_set - set(words)
    if unknown_general_words:
        raise ValueError(
            f"General sample contains unknown words: {sorted(unknown_general_words)!r}"
        )
    if len(general_word_set) != len(general_words):
        raise ValueError("General sample contains a duplicate word")
    ranked_general_words = [word for word in words if word in general_word_set]
    topic_words = [word for word in words if word not in general_word_set]
    return run_tiered_import(
        ranked_general_words,
        topic_words,
        general_level,
        topic_level,
        description,
    )


def run_tiered_import(
    general_words: Sequence[str],
    topic_words: Sequence[str],
    general_level: int,
    topic_level: int,
    description: str,
) -> int:
    """Import two explicit, disjoint general and topic wordlists."""
    all_words = [*general_words, *topic_words]
    if len(set(all_words)) != len(all_words):
        raise ValueError("General and topic lists contain a duplicate word")
    args = parse_args(description)
    print("General-curriculum sample:")
    print_plan(general_words, general_level)
    if topic_words:
        print("\nTopic-specific remainder:")
        print_plan(topic_words, topic_level)
    if not args.execute:
        print("\nNo API calls made. Re-run with --execute only after approval.")
        return 0

    print(f"\nLIVE MODE: Barsukas will use {args.model!r} for paid sense/translation calls.")
    assignments = [
        *((word, general_level) for word in general_words),
        *((word, topic_level) for word in topic_words),
    ]
    try:
        execute_assignments(assignments, args.model, args.limit)
    except (BarsukasAPIError, RuntimeError, requests.exceptions.RequestException) as error:
        print(f"Import stopped: {error}", file=sys.stderr)
        return 1
    return 0
