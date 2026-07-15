"""Helpers for building agent subprocess command lines."""

from typing import List

from flask import current_app


def agent_db_args() -> List[str]:
    """Return the arguments that point an agent subprocess at this app's database.

    Barsukas launches agents as subprocesses, which need to be told which main
    database to use. Passing the persona says that in one word and keeps the
    decision in personas.py rather than restating it as backend flags at every
    call site.

    Agents use only the persona's main database; its concepts and UI settings do
    not apply to them.

    Returns:
        Arguments to append to an agent argv, e.g. ["--persona", "local"]
    """
    persona = current_app.config.get("PERSONA")
    if persona:
        return ["--persona", str(persona)]

    # No persona (test fixtures, or a directly-constructed app): fall back to the
    # concrete path this app is actually using.
    backend_config = current_app.backend_config  # type: ignore[attr-defined]
    if backend_config.postgres_url:
        return ["--postgres"]
    return ["--db-path", str(backend_config.sqlite_path)]
