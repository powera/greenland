"""Capability handlers for idiom equivalent population and auditing."""

from __future__ import annotations

from typing import Any, List, Optional

from idioms.generation import (
    populate_equivalents_for_idiom,
    validate_equivalents_for_idiom,
)
from workqueue.handlers.idioms.tools import get_idiom_or_raise
from workqueue.tools import build_default_config, workqueue_payload_handler


def do_populate_equivalents(
    session: Any,
    idiom_id: int,
    target_languages: Optional[List[str]] = None,
    only_missing: bool = True,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Fill in missing cross-language equivalents for one idiom."""
    idiom = get_idiom_or_raise(session, idiom_id)
    config = build_default_config()
    result = populate_equivalents_for_idiom(
        session,
        idiom,
        config=config.with_model(model) if model else config,
        target_languages=target_languages,
        only_missing=only_missing,
    )

    if not result.get("success"):
        raise RuntimeError(result.get("error", "Unknown idiom equivalent error"))

    session.commit()

    if result.get("note") == "no missing languages":
        return f"No missing languages for {idiom.expression!r}"
    return f"Stored {result.get('stored', 0)} equivalent(s) for {idiom.expression!r}"


def do_validate_equivalents(
    session: Any, idiom_id: int, model: Optional[str] = None, **_: Any
) -> str:
    """Audit one idiom's stored equivalents and report findings.

    Read-only: findings are returned in the task result for a human to act on.
    Nothing is written, so there is no commit.
    """
    idiom = get_idiom_or_raise(session, idiom_id)
    config = build_default_config()
    result = validate_equivalents_for_idiom(
        session, idiom, config=config.with_model(model) if model else config
    )

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
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Workqueue wrapper for idiom equivalent population.

    Accepts and ignores any other extra payload kwargs added by the route so it
    is tolerant of payload changes. ``model`` is NOT among them: dropping it
    would run the operator's queued job on the worker's default model.
    """
    if idiom_ids:
        results = [
            do_populate_equivalents(
                session=session,
                idiom_id=queued_idiom_id,
                target_languages=target_languages,
                only_missing=only_missing,
                model=model,
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
        model=model,
    )


@workqueue_payload_handler()
def handle_idioms_equivalents_validate(
    session: Any,
    idiom_id: Optional[int] = None,
    idiom_ids: Optional[List[int]] = None,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Workqueue wrapper for idiom equivalent auditing."""
    if idiom_ids:
        results = [
            do_validate_equivalents(session=session, idiom_id=queued_idiom_id, model=model)
            for queued_idiom_id in idiom_ids
        ]
        return f"Batch completed for {len(idiom_ids)} idioms: " + "; ".join(results)
    if idiom_id is None:
        raise ValueError("idiom_id or idiom_ids is required")
    return do_validate_equivalents(session=session, idiom_id=idiom_id, model=model)
