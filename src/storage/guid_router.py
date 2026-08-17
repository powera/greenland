"""Route a GUID to the right element kind (lemma / phrase / sentence / idiom / name).

GUIDs encode their entity kind in a prefix:

* sentences use ``S_NNNNN`` (see :func:`storage.crud.sentence.next_sentence_guid`)
* phrases use a phrase-subtype prefix such as ``F01``/``F02`` (see
  :data:`storage.models.guid_prefixes.PHRASE_SUBTYPE_GUID_PREFIXES`)
* idioms use an ``M``-family prefix, currently only ``M01`` (see
  :data:`storage.models.guid_prefixes.IDIOM_GUID_PREFIX`)
* names use an ``E``-family prefix, one per name kind (see
  :data:`storage.models.guid_prefixes.NAME_KIND_GUID_PREFIXES`)
* everything else is a lemma (``N02_001``, ``V01_003``, ...)

Use these helpers anywhere code receives a bare GUID and must fetch the
underlying object without knowing its kind up front.
"""

from typing import Literal, Optional, Tuple, Union

from sqlalchemy.orm import Session

from storage.crud.idiom import get_idiom_by_guid
from storage.crud.lemma import get_lemma_by_guid
from storage.crud.name_entity import get_name_by_guid
from storage.crud.phrase import get_phrase_by_guid
from storage.models.guid_prefixes import (
    IDIOM_GUID_PREFIX,
    NAME_KIND_GUID_PREFIXES,
    PHRASE_SUBTYPE_GUID_PREFIXES,
)
from storage.models.idiom import Idiom
from storage.models.name_entity import Name
from storage.models.schema import Lemma, Phrase, Sentence

GuidKind = Literal["lemma", "phrase", "sentence", "idiom", "name"]

# Phrase GUID prefixes (e.g. "F01", "F02"), longest first so prefix matching is
# unambiguous even if a longer prefix ever shares a leading substring.
_PHRASE_PREFIXES: Tuple[str, ...] = tuple(
    sorted(PHRASE_SUBTYPE_GUID_PREFIXES.values(), key=len, reverse=True)
)

# Idioms are not subtyped, so IDIOM_GUID_PREFIX is a single prefix rather than a
# mapping. Match the whole "M" family so that adding an ``M02`` later - should a
# real subtype axis emerge - routes without touching this classifier.
_IDIOM_PREFIX_FAMILY: str = IDIOM_GUID_PREFIX[0]

# Names are subtyped by kind (E01 given_name, E04 place, ...), so like idioms
# they are matched by family rather than by the exact allocated prefixes: a kind
# added later routes without touching this classifier.
_NAME_PREFIX_FAMILY: str = next(iter(NAME_KIND_GUID_PREFIXES.values()))[0]


def _is_family_guid(guid: str, family_letter: str) -> bool:
    """Whether a GUID's prefix is ``family_letter`` followed by digits.

    e.g. ``M01_001`` is in the "M" family and ``E04_012`` is in the "E" family.
    A bare ``M`` leaves an empty remainder, and ``"".isdigit()`` is False.
    """
    prefix, separator, _ = guid.partition("_")
    if not separator or not prefix.startswith(family_letter):
        return False
    return prefix[1:].isdigit()


def guid_kind(guid: str) -> GuidKind:
    """Return the entity kind a GUID refers to based on its prefix.

    This is a pure string classification; it does not touch the database.
    """
    if guid.startswith("S_"):
        return "sentence"
    if _is_family_guid(guid, _IDIOM_PREFIX_FAMILY):
        return "idiom"
    if _is_family_guid(guid, _NAME_PREFIX_FAMILY):
        return "name"
    if any(guid.startswith(prefix) for prefix in _PHRASE_PREFIXES):
        return "phrase"
    return "lemma"


def get_sentence_by_guid(session: Session, guid: str) -> Optional[Sentence]:
    """Get a sentence by its GUID (e.g. "S_00001")."""
    result: Optional[Sentence] = session.query(Sentence).filter(Sentence.guid == guid).first()
    return result


def resolve_guid(
    session: Session, guid: str
) -> Tuple[GuidKind, Optional[Union[Lemma, Phrase, Sentence, Idiom, Name]]]:
    """Resolve a GUID to ``(kind, object)``.

    The object is ``None`` if no row with that GUID exists, but ``kind`` is
    always returned (derived from the prefix) so callers can branch on it even
    for a missing row.
    """
    kind = guid_kind(guid)
    obj: Optional[Union[Lemma, Phrase, Sentence, Idiom, Name]]
    if kind == "sentence":
        obj = get_sentence_by_guid(session, guid)
    elif kind == "phrase":
        obj = get_phrase_by_guid(session, guid)
    elif kind == "idiom":
        obj = get_idiom_by_guid(session, guid)
    elif kind == "name":
        obj = get_name_by_guid(session, guid)
    else:
        obj = get_lemma_by_guid(session, guid)
    return kind, obj
