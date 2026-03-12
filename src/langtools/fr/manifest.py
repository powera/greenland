"""WireWord manifest grammar metadata for fr."""

from __future__ import annotations

from typing import Any


_CONJUGATION_CONFIG: dict[str, Any] = {
    "tenses": [
        {
            "id": "past",
            "label": "Passé composé",
            "order": 1,
            "has_persons": True,
            "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
            "description": "Primary spoken past tense (composed form).",
        },
        {
            "id": "pres",
            "label": "Présent",
            "order": 2,
            "has_persons": True,
            "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
            "description": "Present indicative conjugations.",
        },
        {
            "id": "fut",
            "label": "Futur simple",
            "order": 3,
            "has_persons": True,
            "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
            "description": "Simple future conjugations.",
        },
        {
            "id": "impf",
            "label": "Imparfait",
            "order": 4,
            "has_persons": True,
            "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
            "description": "Imperfect past for habitual or ongoing actions.",
        },
    ]
}


def get_conjugation_manifest_config() -> dict[str, Any]:
    """Return language-specific conjugation metadata for WireWord manifests."""
    return _CONJUGATION_CONFIG
