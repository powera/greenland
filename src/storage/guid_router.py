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

# Name GUID prefixes (P01 given_name, P04 place, ...). Unlike idioms these are
# matched exactly rather than by family, because names share the "P" family with
# pronoun lemmas: P99 is ``pronoun_other``. Reading the mapping means a new name
# kind routes as soon as it is added to NAME_KIND_GUID_PREFIXES.
_NAME_PREFIXES: Tuple[str, ...] = tuple(
    sorted(NAME_KIND_GUID_PREFIXES.values(), key=len, reverse=True)
)


def _is_idiom_guid(guid: str) -> bool:
    """Return whether a GUID belongs to the idiom ("M" family) namespace.

    Matched by family rather than by an exact prefix so that adding an ``M02``
    later - should a real subtype axis emerge - routes without touching this
    classifier. The "M" family is not shared with any other kind, which is what
    makes that safe here and not for names.

    A bare ``M`` leaves an empty remainder, and ``"".isdigit()`` is False.
    """
    prefix, separator, _ = guid.partition("_")
    if not separator or not prefix.startswith(_IDIOM_PREFIX_FAMILY):
        return False
    return prefix[1:].isdigit()


def _has_prefix(guid: str, prefixes: Tuple[str, ...]) -> bool:
    """Whether ``guid`` starts with one of ``prefixes`` and is prefix-shaped."""
    return "_" in guid and any(guid.startswith(prefix) for prefix in prefixes)


def guid_kind(guid: str) -> GuidKind:
    """Return the entity kind a GUID refers to based on its prefix.

    This is a pure string classification; it does not touch the database.
    """
    if guid.startswith("S_"):
        return "sentence"
    if _is_idiom_guid(guid):
        return "idiom"
    if _has_prefix(guid, _NAME_PREFIXES):
        return "name"
    if _has_prefix(guid, _PHRASE_PREFIXES):
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
