"""Capability handler for generating new idioms in a source language."""

from __future__ import annotations

from typing import Any, Optional

from idioms.generation import generate_idioms_for_language
from workqueue.tools import build_default_config, workqueue_payload_handler


def do_generate_idioms(
    session: Any,
    language_code: str,
    count: int = 10,
    theme: Optional[str] = None,
    difficulty_level: int = -1,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Generate and store new idioms for one source language."""
    config = build_default_config()
    result = generate_idioms_for_language(
        session,
        language_code,
        config=config.with_model(model) if model else config,
        count=count,
        theme=theme,
        difficulty_level=difficulty_level,
    )

    if not result.get("success"):
        raise RuntimeError(result.get("error", "Unknown idiom generation error"))

    session.commit()

    stored = result.get("stored", 0)
    skipped = result.get("skipped_duplicate", 0)
    message = f"Generated {stored} idiom(s) for {language_code}"
    if skipped:
        message += f" ({skipped} duplicate(s) skipped)"
    return message


@workqueue_payload_handler()
def handle_idioms_generate(
    session: Any,
    language_code: str = "en",
    count: int = 10,
    theme: Optional[str] = None,
    difficulty_level: int = -1,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Workqueue wrapper for idiom generation.

    Accepts and ignores any other extra payload kwargs added by the route so it
    is tolerant of payload changes. ``model`` is NOT among them: dropping it
    would run the operator's queued job on the worker's default model.
    """
    return do_generate_idioms(
        session=session,
        language_code=language_code,
        count=count,
        theme=theme,
        difficulty_level=difficulty_level,
        model=model,
    )
