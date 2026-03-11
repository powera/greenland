"""Rule-based Swedish verb conjugation for simple regular patterns."""

from typing import Dict, Optional


def conjugate(infinitive: str) -> Optional[Dict[str, str]]:
    """Conjugate a regular Swedish infinitive to present/past/future."""
    infinitive_value = infinitive.strip().lower()
    if not infinitive_value.endswith("a") or len(infinitive_value) < 2:
        return None

    stem = infinitive_value[:-1]
    return {
        "present": stem + "ar",
        "past": stem + "ade",
        "future": "ska " + infinitive_value,
    }
