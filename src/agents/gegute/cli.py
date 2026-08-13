#!/usr/bin/env python3
"""GEGUTE Agent - Command Line Interface."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_language_args,
    add_llm_args,
    add_processing_args,
    confirm_operation,
    get_data_source_config,
)
from agents.gegute.agent import GeguteAgent, IdiomCoverage
from storage.backend import create_session
from storage.models.idiom import Idiom
from workqueue.task_queue import enqueue_task

logger = logging.getLogger(__name__)

# Canonical capability task names, per agents/WORKQUEUE_REFACTOR_PLAN.md. These
# are deliberately not agent-prefixed: the queue records the capability, not
# which finder discovered the work.
TASK_GENERATE = "idioms.generate"
TASK_POPULATE = "idioms.equivalents.populate"
TASK_VALIDATE = "idioms.equivalents.validate"


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(
        description="Gegute - Idiom Generation and Equivalent Management Agent"
    )

    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5.4-mini")
    add_processing_args(parser)
    add_guid_arg(parser, help_text="Process only the idiom with this GUID")
    add_language_args(parser, multiple=True)
    add_backend_args(parser)

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--coverage",
        action="store_true",
        help="Report idiom equivalent coverage (default mode, read-only)",
    )
    mode_group.add_argument(
        "--generate",
        action="store_true",
        help="Generate new idioms for the source language",
    )
    mode_group.add_argument(
        "--populate",
        action="store_true",
        help="Populate missing equivalents for existing idioms",
    )
    mode_group.add_argument(
        "--validate",
        action="store_true",
        help="Audit stored equivalents and report problems (read-only)",
    )

    parser.add_argument(
        "--source-language",
        default=None,
        help="Source language to generate idioms in, or filter existing idioms by",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="[--generate] Number of idioms to request (default: 10)",
    )
    parser.add_argument(
        "--theme",
        default=None,
        help="[--generate] Restrict generated idioms to a theme",
    )
    parser.add_argument(
        "--difficulty-level",
        type=int,
        default=-1,
        help="[--generate] Difficulty level for new idioms (default: -1, unrated)",
    )
    parser.add_argument(
        "--all-languages",
        action="store_true",
        help="[--populate] Regenerate every target language, not only missing ones",
    )
    parser.add_argument(
        "--use-workqueue",
        action="store_true",
        help="Enqueue capability tasks instead of running the work inline",
    )

    return parser


def _resolve_target_languages(args: argparse.Namespace) -> Optional[List[str]]:
    """Return explicit target languages from --language, or None for defaults.

    ``add_language_args(multiple=True)`` stores under ``languages``, not
    ``language``; reading the wrong attribute would silently ignore the flag.
    """
    languages = getattr(args, "languages", None)
    if not languages:
        return None
    if isinstance(languages, str):
        return [languages]
    return list(languages)


def _print_coverage(report: Dict[str, Any]) -> None:
    """Print the coverage report."""
    rows: Sequence[IdiomCoverage] = report["rows"]
    print(f"\nIdioms:                 {report['total_idioms']}")
    print(f"Complete:               {report['complete']}")
    print(f"Incomplete:             {report['incomplete']}")
    print(f"Missing equivalents:    {report['missing_equivalent_slots']}\n")

    for row in rows:
        if row.is_complete:
            continue
        guid = row.guid or "(no guid)"
        missing = ", ".join(row.missing_languages)
        print(
            f"  {guid}  [{row.source_language_code}] {row.expression}"
            f"  ({row.equivalent_count} stored; missing: {missing})"
        )
    print()


def _print_findings(result: Dict[str, Any]) -> None:
    """Print audit findings."""
    findings = result["findings"]
    print(f"\nEquivalents checked: {result['checked']}")
    print(f"Problems found:      {len(findings)}\n")

    for finding in findings:
        guid = finding.get("guid") or "(no guid)"
        print(
            f"  [{finding.get('severity')}] {guid} {finding.get('expression')!r}"
            f" equivalent {finding.get('equivalent_id')}"
        )
        print(f"      {finding.get('problem')}")
        if finding.get("suggested_kind"):
            print(f"      suggested kind: {finding['suggested_kind']}")
        if finding.get("suggested_expression"):
            print(f"      suggested expression: {finding['suggested_expression']}")
    print()

    for failure in result.get("failed", []):
        print(f"  FAILED {failure.get('guid')}: {failure.get('error')}")


def _enqueue_generate(session: Session, args: argparse.Namespace) -> int:
    """Enqueue one idiom-generation task."""
    language = args.source_language or "en"
    result = enqueue_task(
        session,
        task_type=TASK_GENERATE,
        target_type="language",
        target_id=None,
        payload={
            "schema_version": 1,
            "source_component": "agents.gegute",
            "language_code": language,
            "count": args.count,
            "theme": args.theme,
            "difficulty_level": args.difficulty_level,
        },
        dedup_key=f"{TASK_GENERATE}:{language}:{args.theme or ''}",
    )
    session.commit()
    print(f"Enqueued {TASK_GENERATE} for {language} (task {result.task.id})")
    return 0


def _enqueue_for_idioms(
    session: Session,
    idioms: Sequence[Idiom],
    task_type: str,
    payload_extra: Optional[Dict[str, Any]] = None,
) -> int:
    """Enqueue one task per idiom, reporting how many were newly created."""
    created = 0
    for idiom in idioms:
        payload: Dict[str, Any] = {
            "schema_version": 1,
            "source_component": "agents.gegute",
            "idiom_id": idiom.id,
        }
        if payload_extra:
            payload.update(payload_extra)

        result = enqueue_task(
            session,
            task_type=task_type,
            target_type="idiom",
            target_id=idiom.id,
            payload=payload,
            dedup_key=f"{task_type}:{idiom.id}",
        )
        if result.created:
            created += 1

    session.commit()
    print(f"Enqueued {created} {task_type} task(s) ({len(idioms) - created} already active)")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main entry point."""
    parser = get_argument_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = get_data_source_config(args)
    agent = GeguteAgent(config=config, debug=args.debug)
    session = create_session(config)

    try:
        # --generate acts on a language, so it does not select existing idioms.
        if args.generate:
            language = args.source_language or "en"
            if args.use_workqueue:
                return _enqueue_generate(session, args)

            if not confirm_operation(
                message=f"Will generate {args.count} idiom(s) in {language}",
                estimated_calls=1,
                skip_confirmation=args.yes,
                dry_run=args.dry_run,
            ):
                return 0

            result = agent.generate(
                session,
                language,
                count=args.count,
                theme=args.theme,
                difficulty_level=args.difficulty_level,
                dry_run=args.dry_run,
            )
            if not result.get("success"):
                print(f"Generation failed: {result.get('error')}", file=sys.stderr)
                return 1

            print(
                f"Stored {result['stored']} idiom(s); "
                f"{result['skipped_duplicate']} duplicate(s), "
                f"{result['skipped_invalid']} invalid"
                + (" [DRY RUN, rolled back]" if result.get("dry_run") else "")
            )
            return 0

        idioms = agent.select_idioms(
            session,
            guid=args.guid,
            source_language=args.source_language,
            limit=args.limit,
        )
        if not idioms:
            print("No idioms matched the given filters.", file=sys.stderr)
            return 1

        if args.populate:
            target_languages = _resolve_target_languages(args)
            only_missing = not args.all_languages

            if args.use_workqueue:
                return _enqueue_for_idioms(
                    session,
                    idioms,
                    TASK_POPULATE,
                    {
                        "target_languages": target_languages,
                        "only_missing": only_missing,
                    },
                )

            if not confirm_operation(
                message=f"Will populate equivalents for {len(idioms)} idiom(s)",
                estimated_calls=len(idioms),
                skip_confirmation=args.yes,
                dry_run=args.dry_run,
            ):
                return 0

            result = agent.populate(
                session,
                idioms,
                target_languages=target_languages,
                only_missing=only_missing,
                dry_run=args.dry_run,
            )
            print(
                f"Processed {result['processed']} idiom(s); "
                f"stored {result['stored']} equivalent(s); "
                f"{len(result['failed'])} failed"
                + (" [DRY RUN, rolled back]" if result.get("dry_run") else "")
            )
            for failure in result["failed"]:
                print(f"  FAILED {failure.get('guid')}: {failure.get('error')}")
            return 0

        if args.validate:
            if args.use_workqueue:
                return _enqueue_for_idioms(session, idioms, TASK_VALIDATE)

            if not confirm_operation(
                message=f"Will audit equivalents for {len(idioms)} idiom(s)",
                estimated_calls=len(idioms),
                skip_confirmation=args.yes,
                dry_run=args.dry_run,
            ):
                return 0

            result = agent.validate(session, idioms)
            _print_findings(result)
            return 0

        # Default mode: coverage (read-only).
        report = agent.coverage(
            session,
            guid=args.guid,
            source_language=args.source_language,
            target_languages=_resolve_target_languages(args),
            limit=args.limit,
        )
        _print_coverage(report)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
