"""The passé composé auxiliary (avoir or être) of a French verb.

Every French verb is stored with an explicit ``auxiliary_verb`` grammar fact,
avoir included; there is no implied default.  Most of them follow from a rule:

* reflexive verbs (``se laver``, ``s'asseoir``) take être;
* a closed list of intransitive motion / change-of-state verbs takes être;
* everything else takes avoir.

A handful of verbs take either, depending on the sense: être when intransitive
("elle est sortie"), avoir with a direct object ("elle a sorti la poubelle").
Those return ``None`` here and are decided per lemma from its definition.
"""

from typing import FrozenSet, Optional

AVOIR = "avoir"
ETRE = "être"

# Verbs that always take être (non-reflexive use).
ETRE_VERBS: FrozenSet[str] = frozenset(
    {
        "aller",
        "venir",
        "arriver",
        "partir",
        "entrer",
        "naître",
        "mourir",
        "rester",
        "tomber",
        "devenir",
        "revenir",
        "parvenir",
        "intervenir",
        "survenir",
        "redevenir",
        "repartir",
        "retomber",
        "renaître",
        "décéder",
        "advenir",
        "apparaître",
    }
)

# Verbs whose auxiliary depends on the sense: être intransitive, avoir with a
# direct object.
DUAL_AUXILIARY_VERBS: FrozenSet[str] = frozenset(
    {
        "passer",
        "monter",
        "descendre",
        "sortir",
        "rentrer",
        "retourner",
        "remonter",
        "redescendre",
        "ressortir",
        "repasser",
        "demeurer",
        "accourir",
    }
)

_VERB_ENDINGS = ("er", "ir", "re", "ïr")


def _split_reflexive(verb: str) -> tuple[bool, str]:
    """Return (is_reflexive, rest) for ``se laver`` / ``s'asseoir`` / ``laver``."""
    if verb.startswith("se "):
        return True, verb[3:]
    if verb.startswith(("s'", "s’")):
        return True, verb[2:]
    return False, verb


def pc_auxiliary(verb: str) -> Optional[str]:
    """Return the passé composé auxiliary for *verb*, or ``None`` if it depends on sense.

    *verb* is an infinitive, optionally reflexive or multi-word ("faire du
    vélo", "aller chercher"); the first word is the verb that conjugates.  Input
    that does not look like a French infinitive also returns ``None``.
    """
    text = verb.strip().lower()
    if not text:
        return None
    is_reflexive, rest = _split_reflexive(text)
    if is_reflexive:
        return ETRE

    head = rest.split()[0]
    if not head.endswith(_VERB_ENDINGS):
        return None
    if head in DUAL_AUXILIARY_VERBS:
        return None
    if head in ETRE_VERBS:
        return ETRE
    return AVOIR
