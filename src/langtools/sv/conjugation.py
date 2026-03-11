"""Rule-based Swedish verb conjugation for simple regular patterns."""

from typing import Dict, Optional, Set

# Irregular and Group 2/3/4 verbs that must NOT be mechanically conjugated.
# Only Group 1 (-ar present) verbs are handled here.
_IRREGULAR_VERBS: Set[str] = {
    # Truly irregular
    "vara",
    "ha",
    "bli",
    "göra",
    "gå",
    "få",
    "se",
    "ge",
    "veta",
    "kunna",
    "ska",
    "vilja",
    "böra",
    "måste",
    # Group 2 verbs ending in -a (present in -er, not -ar)
    "ringa",
    "stänga",
    "hänga",
    "tvinga",
    "svänga",
    "bygga",
    "lägga",
    "säga",
    "sätta",
    "köpa",
    "komma",
    "springa",
    "sjunga",
    "dricka",
    "skriva",
    "binda",
    "finna",
    "vinna",
    "brinna",
    "sitta",
    "ligga",
    "sova",
    "flyga",
    "skjuta",
    "bjuda",
    "bryta",
    "njuta",
    "ljuga",
    "frysa",
    "bära",
    "skära",
    "stjäla",
    "falla",
    "hålla",
    "äta",
    "läsa",
    "slå",
    "stå",
    "dra",
    "ta",
    "le",
    "dö",
    # Common Group 2 -a verbs (2a: -er/-te, 2b: -er/-de)
    "köra",
    "höra",
    "föra",
    "göra",
    "lära",
    "behöva",
    "böja",
    "dölja",
    "följa",
    "välja",
    "ställa",
    "berätta",
    "möta",
    "röra",
    "störa",
    "glömma",
    "känna",
    "sända",
    "vända",
    "tänka",
}


def conjugate(infinitive: str) -> Optional[Dict[str, str]]:
    """Conjugate a regular Swedish infinitive to present/past/future."""
    infinitive_value = infinitive.strip().lower()
    if not infinitive_value.endswith("a") or len(infinitive_value) < 2:
        return None

    if infinitive_value in _IRREGULAR_VERBS:
        return None

    stem = infinitive_value[:-1]
    return {
        "present": stem + "ar",
        "past": stem + "ade",
        "future": "ska " + infinitive_value,
    }
