#!/usr/bin/python3

"""Lookup helpers for language-specific prompt directions."""

from importlib import import_module


def get_language_direction_note(language_code: str) -> str:
    """Return optional per-language direction note for prompts.

    Uses a lightweight dynamic import of ``langtools.<language>.directions`` to avoid
    broad import lists and long conditional chains.
    """
    normalized = (language_code or "").strip().lower()
    if not normalized:
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
