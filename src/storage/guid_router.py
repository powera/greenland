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

from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple, Union

from sqlalchemy.orm import Session

from storage.crud.guid_tombstone import get_replacement_chain
from storage.crud.idiom import get_idiom_by_guid
from storage.crud.lemma import get_lemma_by_guid
from storage.crud.name_entity import get_name_by_guid
from storage.crud.phrase import get_phrase_by_guid
from storage.models.guid_prefixes import (
    IDIOM_GUID_PREFIX,
    NAME_KIND_GUID_PREFIXES,
    PHRASE_SUBTYPE_GUID_PREFIXES,
)
from storage.models.guid_tombstone import GuidTombstone
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


@dataclass(frozen=True)
class ResolvedGuid:
    """What a GUID names now, including GUIDs that no longer name anything.

    :func:`resolve_guid` answers "is there a row with this GUID?" and returns
    ``None`` when there is not - which is the same answer for a GUID that was
    never issued and one that was retired years ago.  This distinguishes them,
    so "what happened to A05_001?" has an answer.
    """

    #: The GUID that was looked up.
    guid: str
    #: Entity kind implied by the prefix, whether or not a row exists.
    kind: GuidKind
    #: The row this GUID names, if it still exists.
    obj: Optional[Union[Lemma, Phrase, Sentence, Idiom, Name]]
    #: Tombstones walked from ``guid`` along ``replacement_guid``, nearest first.
    #: Empty when the GUID was never retired.
    tombstones: List[GuidTombstone]
    #: The live row the chain ends at, when ``guid`` itself is retired but its
    #: replacement (or the replacement's replacement) still exists.
    replacement: Optional[Union[Lemma, Phrase, Sentence, Idiom, Name]]
    #: The GUID of :attr:`replacement`.
    replacement_guid: Optional[str]

    @property
    def is_tombstoned(self) -> bool:
        """Whether this GUID was retired."""
        return bool(self.tombstones)

    @property
    def exists(self) -> bool:
        """Whether the GUID still names a live row."""
        return self.obj is not None


def resolve_guid_with_history(session: Session, guid: str) -> ResolvedGuid:
    """Resolve a GUID, following tombstones when it no longer names a row.

    A retired GUID is never reissued (see ``storage.utils.guid``), so a lookup
    that misses is worth explaining rather than reporting as "not found": the
    number may have been replaced when a word changed part of speech, or when
    it was merged into another lemma as a synonym.

    The chain is followed to whichever GUID last had a replacement recorded, and
    that row is resolved if it still exists.  A tombstone with no
    ``replacement_guid`` - a plain deletion - leaves ``replacement`` as None.
    """
    kind, obj = resolve_guid(session, guid)

    chain = get_replacement_chain(session, guid)
    replacement_guid: Optional[str] = None
    for tombstone in chain:
        if tombstone.replacement_guid:
            replacement_guid = tombstone.replacement_guid

    replacement: Optional[Union[Lemma, Phrase, Sentence, Idiom, Name]] = None
    if replacement_guid is not None and replacement_guid != guid:
        _, replacement = resolve_guid(session, replacement_guid)

    return ResolvedGuid(
        guid=guid,
        kind=kind,
        obj=obj,
        tombstones=chain,
        replacement=replacement,
        replacement_guid=replacement_guid,
    )
