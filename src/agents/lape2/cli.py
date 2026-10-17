"""Coverage, exact request previews, and population without task presets."""

from __future__ import annotations

import argparse
import json
import logging
import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from agents.common.batch_run import check_batch_args, run_batch_populate
from agents.common.common_args import (
    add_backend_args,
    add_level_args,
    add_pos_type_args,
    get_data_source_config,
)
from agents.lape2.catalog import CATALOG
from agents.lape2.job import LAPE2_JOB
from agents.lape2.planner import RequestPlan, plan_request
from agents.lape2.query import build_query
from clients.unified_client import UnifiedLLMClient
from constants import DEFAULT_MODEL
from storage.backend import create_session
from storage.backend.config import BackendType
from words.lemma_selection import get_lemmas_for_agent
from workqueue.llm_batch import DEFAULT_ITEMS_PER_BATCH, run_inline


def get_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lape2 — one request per sense for its missing grammar across languages",
        allow_abbrev=False,
    )
    parser.add_argument(
        "command", nargs="?", choices=("coverage", "preview", "populate"), default="coverage"
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=sorted(
            {
                language
                for spec in CATALOG.values()
                if spec.kind != "concept"
                for language in spec.languages()
            }
        ),
        help="Default: all supported languages with existing translations",
    )
    parser.add_argument(
        "--facts",
        nargs="+",
        choices=sorted(CATALOG),
        help="Default: all applicable facts; missing prerequisites are included",
    )
    parser.add_argument("--guid", help="Select one lemma sense by GUID")
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit actionable lemmas, after finding missing facts (preview defaults to 1)",
    )
    add_level_args(parser)
    add_pos_type_args(parser)
    add_backend_args(parser)
    parser.add_argument("--db-path", help="SQLite database override")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--min-confidence", type=float, default=0.7)
    parser.add_argument(
        "--retry-uncertain", action="store_true", help="Include previously low-confidence questions"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Plan only; never call a model or write"
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Confirm batch submission")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="With populate: submit bundled requests as OpenAI batches",
    )
    parser.add_argument(
        "--items-per-batch",
        type=int,
        default=DEFAULT_ITEMS_PER_BATCH,
        help="Requests per OpenAI batch",
    )
    return parser


def select_plans(session: Session, args: argparse.Namespace) -> list[RequestPlan]:
    """Apply the limit to actionable lemmas, rather than the initial candidate pool."""
    selection_args = argparse.Namespace(**{**vars(args), "limit": None})
    languages = args.languages or sorted(
        {
            language
            for spec in CATALOG.values()
            if spec.kind != "concept"
            for language in spec.languages()
        }
    )
    limit = args.limit if args.limit is not None else (1 if args.command == "preview" else None)
    plans: list[RequestPlan] = []
    for lemma in get_lemmas_for_agent(session, selection_args):
        plan = plan_request(
            session, lemma, languages, facts=args.facts, retry_uncertain=args.retry_uncertain
        )
        if not plan.questions and not plan.uncertain:
            continue
        plans.append(plan)
        if limit is not None and sum(bool(item.questions) for item in plans) >= limit:
            break
    return plans


def main() -> None:
    parser = get_argument_parser()
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if not math.isfinite(args.min_confidence) or not 0 <= args.min_confidence <= 1:
        parser.error("--min-confidence must be between 0 and 1")
    args.populate = args.command == "populate"
    if args.batch and not args.populate:
        parser.error("--batch requires the populate command")
    check_batch_args(parser, args)
    config = get_data_source_config(args)
    if config.backend_type == BackendType.JSONL:
        parser.error("Lape2 requires a SQLite or PostgreSQL database")
    if config.backend_type == BackendType.SQLITE and not Path(str(config.sqlite_path)).is_file():
        parser.error("SQLite database does not exist; Lape2 only backfills an existing database")
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    # Skip schema initialization during every planning/read-only path. Open a
    # writable session only for actual population. This additive workflow does
    # not back up on every invocation; back up once before a risky bulk run.
    session = create_session(config, readonly=True)
    try:
        plans = select_plans(session, args)
        counts = Counter(question.key for plan in plans for question in plan.questions)
        print(
            f"Actionable lemmas: {sum(bool(plan.questions) for plan in plans)}; questions: {sum(counts.values())}; previously uncertain: {sum(len(plan.uncertain) for plan in plans)}"
        )
        for identifier, count in sorted(counts.items()):
            print(f"  {identifier}: {count} pending")
        if args.command == "preview":
            for plan in plans:
                if plan.questions:
                    query = build_query(plan)
                    print(
                        json.dumps(
                            {
                                "manifest": plan.to_dict(),
                                "context": query.context,
                                "prompt": query.prompt,
                                "schema": asdict(query.schema),
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
            return
        if args.command == "coverage" or args.dry_run or not counts:
            return
        session.close()
        session = create_session(config)
        states: list[dict[str, Any]] = [
            {
                "lemma_id": plan.lemma_id,
                "languages": list(plan.source["translations"]),
                "facts": args.facts,
                "retry_uncertain": args.retry_uncertain,
                "min_confidence": args.min_confidence,
            }
            for plan in plans
            if plan.questions
        ]
        if args.batch:
            run_batch_populate(LAPE2_JOB, states, args, session, "LAPE2 — BUNDLED GRAMMAR")
        else:
            client = UnifiedLLMClient.from_config(config)
            for state in states:
                outcome = run_inline(session, LAPE2_JOB, [state], client, args.model)[0]
                print(f"{state['lemma_id']}: {outcome.status}: {outcome.detail}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
