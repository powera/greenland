"""Ežys CLI: coverage, exact request previews, and population of native definitions.

The work itself lives in :mod:`words.definition_populate`; the staged job that
runs it live or as OpenAI batches is
:mod:`workqueue.handlers.words.definitions`.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from agents.common.batch_run import check_batch_args, run_batch_populate
from agents.common.common_args import (
    add_backend_args,
    add_level_args,
    add_pos_type_args,
    get_data_source_config,
)
from clients.lib import to_openai_schema
from clients.unified_client import UnifiedLLMClient
from constants import DEFAULT_MODEL
from storage.backend import create_session
from storage.backend.config import BackendType
from storage.models.schema import Lemma
from words.definition_populate import (
    DEFAULT_MIN_CONFIDENCE,
    build_definition_call,
    definition_groups,
    definition_register,
    lemma_cefr,
    missing_definition_languages,
)
from words.lemma_selection import get_lemmas_for_agent
from words.translation_workflow import resolve_generation_languages
from workqueue.handlers.words.definitions import DEFINITIONS_JOB
from workqueue.llm_batch import DEFAULT_ITEMS_PER_BATCH, run_inline


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser (also used for introspection by launchers)."""
    parser = argparse.ArgumentParser(
        description=(
            "Ežys — native definitions for lemma translations: each language's word "
            "defined in that language, never a translation of the English definition"
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "command", nargs="?", choices=("coverage", "preview", "populate"), default="coverage"
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        help=(
            "Language codes, a group name (ancient) or 'all' (tiers 1-3). "
            "Default: tiers 1 and 2. English is never generated: it is the lemma's own definition"
        ),
    )
    parser.add_argument("--guid", help="Select one lemma by GUID")
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit actionable lemmas, after finding missing definitions (preview defaults to 1)",
    )
    add_level_args(parser)
    add_pos_type_args(parser)
    add_backend_args(parser)
    parser.add_argument("--db-path", help="SQLite database override")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE)
    parser.add_argument(
        "--retry-uncertain",
        action="store_true",
        help="Also ask languages a model was uncertain of before",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help=(
            "Ask again for languages that already have a definition and overwrite "
            "them where the new answer is confident"
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Plan only; never call a model or write"
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Confirm batch submission")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="With populate: submit the requests as OpenAI batches (half price)",
    )
    parser.add_argument(
        "--items-per-batch",
        type=int,
        default=DEFAULT_ITEMS_PER_BATCH,
        help="Requests per OpenAI batch",
    )
    return parser


def resolve_languages(requested: List[str] | None) -> List[str]:
    """The requested languages, expanded as voras does, without English."""
    return [code for code in resolve_generation_languages(requested) if code != "en"]


class Selection:
    """The lemmas in scope and, for each, the language groups to ask."""

    def __init__(self) -> None:
        self.groups: List[Tuple[Lemma, List[str]]] = []
        self.translated: Counter[str] = Counter()
        self.defined: Counter[str] = Counter()
        self.pending: Counter[str] = Counter()
        self.lemmas_considered = 0

    @property
    def actionable_lemmas(self) -> int:
        return len({lemma.id for lemma, _group in self.groups})


def select(session: Session, args: argparse.Namespace, languages: List[str]) -> Selection:
    """Apply the limit to actionable lemmas rather than to the candidate pool."""
    selection_args = argparse.Namespace(**{**vars(args), "limit": None})
    limit = args.limit if args.limit is not None else (1 if args.command == "preview" else None)
    selection = Selection()
    actionable = 0
    for lemma in get_lemmas_for_agent(session, selection_args):
        selection.lemmas_considered += 1
        for row in lemma.translations:
            if row.language_code in languages and (row.translation or "").strip():
                selection.translated[row.language_code] += 1
                if (row.definition_text or "").strip():
                    selection.defined[row.language_code] += 1
        if limit is not None and actionable >= limit:
            continue
        missing = missing_definition_languages(
            session,
            lemma,
            languages,
            retry_uncertain=args.retry_uncertain,
            replace_existing=args.regenerate,
        )
        if not missing:
            continue
        actionable += 1
        selection.pending.update(missing)
        selection.groups.extend((lemma, group) for group in definition_groups(missing))
    return selection


def print_coverage(selection: Selection, languages: List[str]) -> None:
    print(f"Lemmas considered: {selection.lemmas_considered}")
    print(f"{'lang':<8} {'translated':>10} {'defined':>8} {'%':>6} {'to ask':>7}")
    for code in languages:
        translated = selection.translated[code]
        defined = selection.defined[code]
        percent = f"{100 * defined / translated:.1f}" if translated else "-"
        print(f"{code:<8} {translated:>10} {defined:>8} {percent:>6} {selection.pending[code]:>7}")
    print(
        f"Actionable lemmas: {selection.actionable_lemmas}; "
        f"requests: {len(selection.groups)}; definitions to ask: {sum(selection.pending.values())}"
    )


def print_previews(session: Session, selection: Selection) -> None:
    for lemma, group in selection.groups:
        cefr = lemma_cefr(session, lemma)
        call = build_definition_call(session, lemma, group)
        print(
            json.dumps(
                {
                    "guid": lemma.guid,
                    "level": lemma.difficulty_level,
                    "level_cefr": cefr,
                    "register": definition_register(cefr),
                    "languages": group,
                    "context": call.context,
                    "prompt": call.prompt,
                    "schema": to_openai_schema(call.schema),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


def main() -> int:
    """Run Ežys; returns the process exit status (1 if any inline item failed)."""
    parser = get_argument_parser()
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if not math.isfinite(args.min_confidence) or not 0 <= args.min_confidence <= 1:
        parser.error("--min-confidence must be between 0 and 1")
    args.populate = args.command == "populate"
    check_batch_args(parser, args)
    try:
        languages = resolve_languages(args.languages)
    except ValueError as error:
        parser.error(str(error))
    if not languages:
        parser.error("No languages to generate (English definitions are not generated here)")

    config = get_data_source_config(args)
    if config.backend_type == BackendType.JSONL:
        parser.error("Ežys requires a SQLite or PostgreSQL database")
    if config.backend_type == BackendType.SQLITE and not Path(str(config.sqlite_path)).is_file():
        parser.error("SQLite database does not exist")
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    # Plan on a read-only session; open a writable one only to populate.
    session = create_session(config, readonly=True)
    try:
        selection = select(session, args, languages)
        print_coverage(selection, languages)
        if args.command == "preview":
            print_previews(session, selection)
            return 0
        # A batch dry run still goes on: run_batch_populate prints the plan.
        if args.command == "coverage" or not selection.groups:
            return 0
        if args.dry_run and not args.batch:
            print("DRY RUN - no model calls, nothing written")
            return 0

        states: List[Dict[str, Any]] = [
            {
                "lemma_id": lemma.id,
                "languages": group,
                "retry_uncertain": args.retry_uncertain,
                "replace_existing": args.regenerate,
                "min_confidence": args.min_confidence,
            }
            for lemma, group in selection.groups
        ]
        session.close()
        session = create_session(config)
        if args.batch:
            run_batch_populate(
                DEFINITIONS_JOB,
                states,
                args,
                session,
                "EŽYS — NATIVE DEFINITIONS",
                summary_lines=[f"Languages: {', '.join(languages)}"],
            )
            return 0

        client = UnifiedLLMClient.from_config(config)
        failed = 0
        for state in states:
            item_lemma = session.get(Lemma, state["lemma_id"])
            label = item_lemma.guid if item_lemma is not None else state["lemma_id"]
            outcome = run_inline(session, DEFINITIONS_JOB, [state], client, args.model)[0]
            print(f"{label} [{'+'.join(state['languages'])}]: {outcome.status}: {outcome.detail}")
            if outcome.status == "failed":
                failed += 1
        return 1 if failed else 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
