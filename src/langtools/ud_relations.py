#!/usr/bin/python3

"""Universal Dependencies core relation vocabulary.

Holds the 37 core UD relation labels plus the sentinel head position used for
the sentence root. This is prompt-and-validation vocabulary: the database
column stays a plain ``String``, exactly as ``part_of_speech`` does.

Enhanced-UD subtypes (``nsubj:pass``, ``obl:tmod``, ...) are deliberately out
of scope; only the core labels are accepted.
"""

from typing import FrozenSet

# Head position meaning "this token is the sentence root". Real heads are
# zero-based indices into the decomposed word list.
ROOT_HEAD_POSITION: int = -1

# The 37 core Universal Dependencies relations.
UD_RELATIONS: FrozenSet[str] = frozenset(
    {
        "acl",
        "advcl",
        "advmod",
        "amod",
        "appos",
        "aux",
        "case",
        "cc",
        "ccomp",
        "clf",
        "compound",
        "conj",
        "cop",
        "csubj",
        "dep",
        "det",
        "discourse",
        "dislocated",
        "expl",
        "fixed",
        "flat",
        "goeswith",
        "iobj",
        "list",
        "mark",
        "nmod",
        "nsubj",
        "nummod",
        "obj",
        "obl",
        "orphan",
        "parataxis",
        "punct",
        "reparandum",
        "root",
        "vocative",
        "xcomp",
    }
)

# The label carried by the single token whose head is ROOT_HEAD_POSITION.
ROOT_RELATION: str = "root"


def is_valid_ud_relation(label: str) -> bool:
    """Return True when ``label`` is one of the core UD relations."""
    return label in UD_RELATIONS


def sorted_ud_relations() -> list[str]:
    """Return the core relations in a stable order (for schemas and prompts)."""
    return sorted(UD_RELATIONS)
