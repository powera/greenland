"""Language selector for mechanical noun declension engines."""

from importlib import import_module
from typing import Callable, Dict, Optional, cast

DeclineFunc = Callable[[str], Optional[Dict[str, str]]]


def get_mechanical_noun_decliner(language_code: str) -> Optional[DeclineFunc]:
    """Return a language-specific mechanical noun declension function if available."""
    normalized = (language_code or "").strip().lower()
    if not normalized:
        return None

    try:
        module = import_module(f"langtools.{normalized}.declension")
    except ModuleNotFoundError:
        return None

    decline_func = getattr(module, "decline_noun", None)
    if callable(decline_func):
        return cast(DeclineFunc, decline_func)

    return None
