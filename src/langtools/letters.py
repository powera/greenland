#!/usr/bin/env python3
"""
Per-language alphabet letters for dictionary-view "letter bars" and similar UX.

Each supported language exposes its alphabet in
``src/langtools/<lang>/letters.py`` as the module-level constant:

    LETTERS_UPPER: List[str]

The list is in canonical dictionary order for that language. For scripts that
have no upper/lower distinction (CJK kana/hanzi, Hangul jamo, Thai, Tamil,
Devanagari, Bengali, Kannada), ``LETTERS_UPPER`` simply holds the script's
ordering set and ``get_letters(..., uppercase=False)`` returns the same list.

Note: the alphabet is an *explicit* per-language list, not a derivation from
``collation.py``. This is intentional — collation handles diacritic
remapping for *sorting strings*, while the alphabet bar needs the exact
letters a user expects to see (e.g. Spanish includes Ñ; Lithuanian includes
Y between Į and J; Chinese uses pinyin initials minus rare ones).

Languages currently supported include tiers 1–3 plus Turkish. Other languages
return ``None``; callers should fall back to plain A–Z when appropriate.
"""

from __future__ import annotations

from importlib import util
from pathlib import Path
from types import ModuleType
from typing import List, Optional


def _load_letters_module(language_code: str) -> Optional[ModuleType]:
    """Dynamically import ``src/langtools/<lang>/letters.py``, if present."""
    langtools_spec = util.find_spec("langtools")
    if langtools_spec is None or not langtools_spec.submodule_search_locations:
        return None

    langtools_root = Path(next(iter(langtools_spec.submodule_search_locations)))
    letters_path = langtools_root / language_code.lower() / "letters.py"
    if not letters_path.exists():
        return None

    module_name = f"langtools_dynamic_{language_code.lower()}_letters"
    spec = util.spec_from_file_location(module_name, letters_path)
    if spec is None or spec.loader is None:
        return None

    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_letters(lang_code: str, *, uppercase: bool = True) -> Optional[List[str]]:
    """Return the alphabet of *lang_code* in canonical dictionary order.

    Args:
        lang_code: ISO-style language code (e.g. ``"lt"``, ``"zh"``).
        uppercase: When ``True`` (default), letters are returned in their
            uppercase form. When ``False``, lowercase is returned. Scripts
            without case distinction (CJK, Thai, Tamil, Devanagari, etc.)
            ignore this argument and return the same list either way.

    Returns:
        Ordered list of single-letter strings, or ``None`` if the language
        has no ``letters.py`` module. Callers wanting a default for unsupported
        languages should fall back to ``list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")``.
    """
    if not lang_code:
        return None

    module = _load_letters_module(lang_code)
    if module is None:
        return None

    upper = getattr(module, "LETTERS_UPPER", None)
    if not isinstance(upper, list) or not upper:
        return None

    if uppercase:
        return list(upper)
    return [ch.lower() for ch in upper]
