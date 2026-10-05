"""The ``--batch`` flow shared by agents that run a staged job (workqueue.llm_batch).

An agent builds its item states; this module adds the flags, checks them, plans
the run without writing, shows the counts, asks for confirmation, submits, and
says how the results come back.
"""

import argparse
import sys
from typing import Any, Dict, List, Sequence

from sqlalchemy.orm import Session

from workqueue.llm_batch import DEFAULT_ITEMS_PER_BATCH, Job, start_batch_run


def add_batch_args(parser: argparse.ArgumentParser) -> None:
    """Add ``--batch`` and ``--items-per-batch``."""
    parser.add_argument(
        "--batch",
        action="store_true",
        help=(
            "With --populate: send the requests as OpenAI batches (half price); the "
            "Barsukas batch poller writes the results when each batch completes"
        ),
    )
    parser.add_argument(
        "--items-per-batch",
        type=int,
        default=DEFAULT_ITEMS_PER_BATCH,
        help=f"With --batch: requests per OpenAI batch (default: {DEFAULT_ITEMS_PER_BATCH})",
    )


def is_openai_model(model: str) -> bool:
    """Whether *model* is served by OpenAI, whose Batch API ``--batch`` uses."""
    return model.startswith(("gpt-", "o1", "o3", "o4"))


def check_batch_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject ``--batch`` combinations that cannot work; no-op without ``--batch``."""
    if not getattr(args, "batch", False):
        return
    if not getattr(args, "populate", False):
        parser.error("--batch only applies with --populate")
    if getattr(args, "use_workqueue", False):
        parser.error("--batch and --use-workqueue cannot be used together")
    if not is_openai_model(args.model):
        parser.error(
            f"--batch uses the OpenAI Batch API; --model {args.model} is not an OpenAI model"
        )
    if args.items_per_batch < 1:
        parser.error("--items-per-batch must be at least 1")


def run_batch_populate(
    job: Job,
    states: Sequence[Dict[str, Any]],
    args: argparse.Namespace,
    session: Session,
    title: str,
    summary_lines: Sequence[str] = (),
) -> None:
    """Plan *states* as a run of *job*, confirm, and submit it.

    Args:
        job: The staged job.
        states: One item state per unit of work.
        args: Parsed CLI args (``model``, ``items_per_batch``, ``dry_run``, ``yes``).
        session: Main database session.
        title: Banner heading, e.g. ``"LAPE AGENT - BATCH POPULATE"``.
        summary_lines: Extra lines describing the selection, shown under the model.
    """
    from clients.batch_queue import BatchQueueManager, create_batch_database_session
    from clients.openai.batch_client import OpenAIBatchClient

    batch_session = create_batch_database_session()
    try:
        manager = BatchQueueManager(batch_session, OpenAIBatchClient())
        # Plan first without writing anything, so the counts can be confirmed.
        plan = start_batch_run(session, manager, job, states, args.model, dry_run=True)
        batches = -(-plan.calls // args.items_per_batch) if plan.calls else 0
        print("\n" + "=" * 80)
        print(title)
        print("=" * 80)
        print(f"Model: {args.model}")
        for line in summary_lines:
            print(f"  {line}")
        print(f"Items considered: {plan.items}")
        print(f"  already in a batch run: {plan.skipped_in_flight}")
        for outcome, count in sorted(plan.resolved_without_llm.items()):
            print(f"  {outcome} without a model call: {count}")
        if plan.unprepared:
            print(
                f"  to prepare at submission: {plan.unprepared} (each is answered "
                "mechanically where possible, otherwise sent to the model)"
            )
            print(f"Requests: up to {plan.unprepared} in batches of up to {args.items_per_batch}")
        else:
            print(f"Requests: {plan.calls} in {batches} batch(es) of up to {args.items_per_batch}")
        print("=" * 80)

        pending = plan.calls + plan.unprepared + plan.resolved_without_llm.get("answered", 0)
        if not pending:
            print("Nothing to submit.")
            return
        if args.dry_run:
            print("DRY RUN - nothing was written, queued or submitted")
            return
        if (plan.calls or plan.unprepared) and not args.yes:
            response = input("Submit these batches to OpenAI? [y/N]: ").strip().lower()
            if response not in ["y", "yes"]:
                print("Aborted.")
                sys.exit(0)

        report = start_batch_run(
            session,
            manager,
            job,
            states,
            args.model,
            items_per_batch=args.items_per_batch,
        )
        print(f"Run {report.run_id}: {report.calls} request(s)")
        for outcome, count in sorted(report.resolved_without_llm.items()):
            print(f"  {outcome} without a model call: {count}")
        for batch_id in report.batch_ids:
            print(f"  submitted {batch_id}")
        if report.batch_ids:
            print("\nThe Barsukas batch poller checks every 5 minutes and writes the results.")
            print("By hand: python -m agents.common.batch status --batch-id <id>")
            print("         python -m agents.common.batch complete --batch-id <id>")
    finally:
        batch_session.close()


def batch_summary(fact_types_by_language: Dict[str, List[str]]) -> List[str]:
    """``"<language>: a, b"`` lines for a language -> task-list selection."""
    return [f"{language}: {', '.join(tasks)}" for language, tasks in fact_types_by_language.items()]
