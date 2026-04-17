"""Rule-based Portuguese verb conjugation for common regular patterns."""

from typing import Dict, Optional, Set, Tuple

# Common irregular verbs with hard-coded core forms.
# We intentionally keep this list small and focused on high-frequency verbs.
_HARDCODED_CONJUGATIONS: Dict[str, Dict[str, str]] = {
    "ser": {
        "1s_present": "sou",
        "2s_present": "és",
        "3s_present": "é",
        "1p_present": "somos",
        "2p_present": "sois",
        "3p_present": "são",
        "1s_past": "fui",
        "2s_past": "foste",
        "3s_past": "foi",
        "1p_past": "fomos",
        "2p_past": "fostes",
        "3p_past": "foram",
        "1s_future": "serei",
        "2s_future": "serás",
        "3s_future": "será",
        "1p_future": "seremos",
        "2p_future": "sereis",
        "3p_future": "serão",
    },
    "estar": {
        "1s_present": "estou",
        "2s_present": "estás",
        "3s_present": "está",
        "1p_present": "estamos",
        "2p_present": "estais",
        "3p_present": "estão",
        "1s_past": "estive",
        "2s_past": "estiveste",
        "3s_past": "esteve",
        "1p_past": "estivemos",
        "2p_past": "estivestes",
        "3p_past": "estiveram",
        "1s_future": "estarei",
        "2s_future": "estarás",
        "3s_future": "estará",
        "1p_future": "estaremos",
        "2p_future": "estareis",
        "3p_future": "estarão",
    },
}

# Irregular verbs that must NOT be mechanically conjugated.
_IRREGULAR_VERBS: Set[str] = {
    # Fully irregular
    "ir",
    "ter",
    "haver",
    # Irregular present / preterite / participle
    "fazer",
    "dizer",
    "trazer",
    "poder",
    "pôr",
    "por",
    "querer",
    "saber",
    "ver",
    "vir",
    "dar",
    "ler",
    "crer",
    "rir",
    "ouvir",
    "pedir",
    "medir",
    "sentir",
    "dormir",
    "subir",
    "fugir",
    "seguir",
    "vestir",
    "mentir",
    "servir",
    "repetir",
    "preferir",
    "sugerir",
    "divertir",
    "cobrir",
    "descobrir",
    "engolir",
    # Orthographic / stem-changing
    "perder",
    "valer",
    "caber",
}

_PRESENT_ENDINGS: Dict[str, Tuple[str, str, str, str, str, str]] = {
    "ar": ("o", "as", "a", "amos", "ais", "am"),
    "er": ("o", "es", "e", "emos", "eis", "em"),
    "ir": ("o", "es", "e", "imos", "is", "em"),
}

_PRETERITE_ENDINGS: Dict[str, Tuple[str, str, str, str, str, str]] = {
    "ar": ("ei", "aste", "ou", "amos", "astes", "aram"),
    "er": ("i", "este", "eu", "emos", "estes", "eram"),
    "ir": ("i", "iste", "iu", "imos", "istes", "iram"),
}

_FUTURE_ENDINGS: Tuple[str, str, str, str, str, str] = ("ei", "ás", "á", "emos", "eis", "ão")
_PERSONS: Tuple[str, str, str, str, str, str] = ("1s", "2s", "3s", "1p", "2p", "3p")


def conjugate(infinitive: str) -> Optional[Dict[str, str]]:
    """Conjugate a regular Portuguese infinitive across present/past/future."""
    infinitive_value = infinitive.strip().lower()
    hardcoded_conjugation = _HARDCODED_CONJUGATIONS.get(infinitive_value)
    if hardcoded_conjugation is not None:
        return dict(hardcoded_conjugation)

    verb_class = ""
    for candidate in ("ar", "er", "ir"):
        if infinitive_value.endswith(candidate):
            verb_class = candidate
            break

    if not verb_class:
        return None

    if infinitive_value in _IRREGULAR_VERBS:
        return None

    stem = infinitive_value[:-2]
    forms: Dict[str, str] = {}
    for index, person in enumerate(_PERSONS):
        forms[f"{person}_present"] = stem + _PRESENT_ENDINGS[verb_class][index]
        forms[f"{person}_past"] = stem + _PRETERITE_ENDINGS[verb_class][index]
        forms[f"{person}_future"] = infinitive_value + _FUTURE_ENDINGS[index]

    return forms
