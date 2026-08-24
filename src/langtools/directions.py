#!/usr/bin/python3

"""Lookup helpers for language-specific prompt directions."""

from importlib import import_module

from langtools.dialect_overrides import is_dialect, normalize_language_code


def get_language_direction_note(language_code: str) -> str:
    """Return optional per-language direction note for prompts.

    Uses a lightweight dynamic import of ``langtools.<language>.directions`` to avoid
    broad import lists and long conditional chains.

    A dialect deliberately does *not* inherit its parent's note.  These notes
    pin down which variant the bare code means ("for Spanish, use Castilian"),
    so inheriting one would contradict the dialect it is being used for; the
    dialect's own ``llm_prompt_note`` in ``langtools.dialect_overrides`` says
    what to use instead, and callers append that separately.
    """
    normalized = normalize_language_code(language_code)
    if not normalized or is_dialect(normalized):
        return ""

    try:
        module = import_module(f"langtools.{normalized}.directions")
    except ModuleNotFoundError:
        return ""

    getter = getattr(module, "get_general_direction_note", None)
    if callable(getter):
        note = getter()
        return note if isinstance(note, str) else ""
    return ""
