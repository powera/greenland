"""Capability handlers for naming curriculum levels."""

from __future__ import annotations

from typing import Any, List, Optional

from words.level_naming import generate_level_name, translate_level_name
from workqueue.tools import build_default_config, workqueue_payload_handler


def do_generate_level_name(
    session: Any,
    level: int,
    overwrite: bool = False,
    translate: bool = False,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Name one level from its words and commit; optionally translate after.

    ``translate`` runs the translation in the same task rather than queueing a
    second one: the workqueue orders only lemma tasks, so a separately queued
    translation could run before there is a name to translate.  An overwritten
    name re-translates every language, since the old translations were of the
    old name.
    """
    config = build_default_config()
    run_config = config.with_model(model) if model else config
    result = generate_level_name(session, int(level), config=run_config, overwrite=bool(overwrite))
    session.commit()
    if result["written"]:
        message = f"Named level {level} {result['name']!r} ({result.get('cefr') or 'no CEFR'})"
    else:
        message = f"Level {level} already named {result['name']!r}; left unchanged"

    if translate:
        written = translate_level_name(
            session, int(level), config=run_config, overwrite=bool(result["written"] and overwrite)
        )
        session.commit()
        message += f"; translated into {len(written)} language(s)"
    return message


def do_translate_level_name(
    session: Any,
    level: int,
    languages: Optional[List[str]] = None,
    overwrite: bool = False,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Translate one level's name and commit."""
    config = build_default_config()
    written = translate_level_name(
        session,
        int(level),
        config=config.with_model(model) if model else config,
        languages=languages,
        overwrite=bool(overwrite),
    )
    session.commit()
    if not written:
        return f"Level {level}: no translations needed"
    return f"Level {level}: translated into {', '.join(sorted(written))}"


@workqueue_payload_handler()
def handle_levels_name_generate(
    session: Any,
    level: int,
    overwrite: bool = False,
    translate: bool = False,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Workqueue wrapper for :func:`do_generate_level_name`."""
    return do_generate_level_name(
        session=session, level=level, overwrite=overwrite, translate=translate, model=model
    )


@workqueue_payload_handler()
def handle_levels_name_translate(
    session: Any,
    level: int,
    languages: Optional[List[str]] = None,
    overwrite: bool = False,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Workqueue wrapper for :func:`do_translate_level_name`."""
    return do_translate_level_name(
        session=session, level=level, languages=languages, overwrite=overwrite, model=model
    )
