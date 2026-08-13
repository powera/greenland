"""Capability handlers for idiom equivalent population and auditing."""

from __future__ import annotations

from typing import Any, List, Optional

from idioms.generation import (
    populate_equivalents_for_idiom,
    validate_equivalents_for_idiom,
)
from workqueue.handlers.idioms.tools import get_idiom_or_raise
from workqueue.tools import workqueue_payload_handler


def do_populate_equivalents(
    session: Any,
    idiom_id: int,
    target_languages: Optional[List[str]] = None,
    only_missing: bool = True,
    **_: Any,
) -> str:
    """Fill in missing cross-language equivalents for one idiom."""
    idiom = get_idiom_or_raise(session, idiom_id)
    result = populate_equivalents_for_idiom(
        session,
        idiom,
        target_languages=target_languages,
        only_missing=only_missing,
    )

    if not result.get("success"):
        raise RuntimeError(result.get("error", "Unknown idiom equivalent error"))

    session.commit()

    if result.get("note") == "no missing languages":
        return f"No missing languages for {idiom.expression!r}"
    return f"Stored {result.get('stored', 0)} equivalent(s) for {idiom.expression!r}"


def do_validate_equivalents(session: Any, idiom_id: int, **_: Any) -> str:
    """Audit one idiom's stored equivalents and report findings.

    Read-only: findings are returned in the task result for a human to act on.
    Nothing is written, so there is no commit.
    """
    idiom = get_idiom_or_raise(session, idiom_id)
    result = validate_equivalents_for_idiom(session, idiom)

    if not result.get("success"):
        raise RuntimeError(result.get("error", "Unknown idiom validation error"))

    problems = result.get("problems", [])
    checked = result.get("checked", 0)
    if not problems:
        return f"Checked {checked} equivalent(s) for {idiom.expression!r}; no problems"

    errors = sum(1 for problem in problems if problem.get("severity") == "error")
    summary = "; ".join(
        f"[{problem.get('equivalent_id')}] {problem.get('severity')}: {problem.get('problem')}"
        for problem in problems
    )
    return (
        f"Checked {checked} equivalent(s) for {idiom.expression!r}; "
        f"{len(problems)} problem(s), {errors} error(s): {summary}"
    )


@workqueue_payload_handler()
def handle_idioms_equivalents_populate(
    session: Any,
    idiom_id: Optional[int] = None,
    idiom_ids: Optional[List[int]] = None,
    target_languages: Optional[List[str]] = None,
    only_missing: bool = True,
    **_: Any,
) -> str:
    """Workqueue wrapper for idiom equivalent population.

    Accepts and ignores extra payload kwargs (``model``, etc.) added by the
    route so it is tolerant of payload changes.
    """
    if idiom_ids:
        results = [
            do_populate_equivalents(
                session=session,
                idiom_id=queued_idiom_id,
                target_languages=target_languages,
                only_missing=only_missing,
            )
            for queued_idiom_id in idiom_ids
        ]
        return f"Batch completed for {len(idiom_ids)} idioms: " + "; ".join(results)
    if idiom_id is None:
        raise ValueError("idiom_id or idiom_ids is required")
    return do_populate_equivalents(
        session=session,
        idiom_id=idiom_id,
        target_languages=target_languages,
        only_missing=only_missing,
    )


@workqueue_payload_handler()
def handle_idioms_equivalents_validate(
    session: Any,
    idiom_id: Optional[int] = None,
    idiom_ids: Optional[List[int]] = None,
    **_: Any,
) -> str:
    """Workqueue wrapper for idiom equivalent auditing."""
    if idiom_ids:
        results = [
            do_validate_equivalents(session=session, idiom_id=queued_idiom_id)
            for queued_idiom_id in idiom_ids
        ]
        return f"Batch completed for {len(idiom_ids)} idioms: " + "; ".join(results)
    if idiom_id is None:
        raise ValueError("idiom_id or idiom_ids is required")
    return do_validate_equivalents(session=session, idiom_id=idiom_id)
