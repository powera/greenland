"""Helpers for stripping leading subject pronouns from verb forms.

This module uses introspection to discover language-specific implementations in
``langtools.<language_code>.utils`` without introducing hard-coded import trees.
"""

from __future__ import annotations

from importlib import util
from pathlib import Path
from types import ModuleType


def _load_utils_module(language_code: str) -> ModuleType:
    langtools_spec = util.find_spec("langtools")
    if langtools_spec is None or not langtools_spec.submodule_search_locations:
        raise NotImplementedError("Could not locate langtools package")

    langtools_root = Path(next(iter(langtools_spec.submodule_search_locations)))
    utils_path = langtools_root / language_code.lower() / "utils.py"
    if not utils_path.exists():
        raise NotImplementedError(f"No utils module for language '{language_code}'")

    module_name = f"langtools_dynamic_{language_code.lower()}_utils"
    spec = util.spec_from_file_location(module_name, utils_path)
    if spec is None or spec.loader is None:
        raise NotImplementedError(f"Could not load utils for language '{language_code}'")

    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def strip_pronoun_or_raise(language_code: str, text: str) -> str:
    """Strip leading subject pronoun using a language-specific implementation."""
    if not language_code:
        raise ValueError("language_code must be non-empty")

    module = _load_utils_module(language_code)

    strip_func = getattr(module, "strip_subject_pronoun", None)
    if not callable(strip_func):
        raise NotImplementedError(
            f"Language '{language_code}' does not implement strip_subject_pronoun"
        )

    stripped = strip_func(text)
    if not isinstance(stripped, str):
        raise TypeError(
            f"Language '{language_code}' strip_subject_pronoun returned "
            f"{type(stripped).__name__}, expected str"
        )
    return stripped


def strip_pronoun(language_code: str, text: str) -> str:
    """Best-effort pronoun stripping.

    Returns ``text`` unchanged when no language-specific implementation exists.
    """
    try:
        return strip_pronoun_or_raise(language_code=language_code, text=text)
    except (NotImplementedError, ValueError):
        return text
