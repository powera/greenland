"""Capability handler for generating new idioms in a source language."""

from __future__ import annotations

from typing import Any, Optional

from idioms.generation import generate_idioms_for_language
from workqueue.tools import workqueue_payload_handler


def do_generate_idioms(
    session: Any,
    language_code: str,
    count: int = 10,
    theme: Optional[str] = None,
    difficulty_level: int = -1,
    **_: Any,
) -> str:
    """Generate and store new idioms for one source language."""
    result = generate_idioms_for_language(
        session,
        language_code,
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
    **_: Any,
) -> str:
    """Workqueue wrapper for idiom generation.

    Accepts and ignores extra payload kwargs (``model``, etc.) added by the
    route so it is tolerant of payload changes.
    """
    return do_generate_idioms(
        session=session,
        language_code=language_code,
        count=count,
        theme=theme,
        difficulty_level=difficulty_level,
    )
