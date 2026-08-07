"""Route a GUID to the right element kind (lemma / phrase / sentence / idiom).

GUIDs encode their entity kind in a prefix:

* sentences use ``S_NNNNN`` (see :func:`storage.crud.sentence.next_sentence_guid`)
* phrases use a phrase-subtype prefix such as ``F01``/``F02`` (see
  :data:`storage.models.guid_prefixes.PHRASE_SUBTYPE_GUID_PREFIXES`)
* idioms use ``M01_NNN``
* everything else is a lemma (``N02_001``, ``V01_003``, ...)

Use these helpers anywhere code receives a bare GUID and must fetch the
underlying object without knowing its kind up front.
"""

from typing import Literal, Optional, Tuple, Union

from sqlalchemy.orm import Session

from storage.crud.idiom import get_idiom_by_guid
from storage.crud.lemma import get_lemma_by_guid
from storage.crud.phrase import get_phrase_by_guid
from storage.models.guid_prefixes import PHRASE_SUBTYPE_GUID_PREFIXES
from storage.models.idiom import IDIOM_GUID_PREFIX, Idiom
from storage.models.schema import Lemma, Phrase, Sentence

GuidKind = Literal["lemma", "phrase", "sentence", "idiom"]

# Phrase GUID prefixes (e.g. "F01", "F02"), longest first so prefix matching is
# unambiguous even if a longer prefix ever shares a leading substring.
_PHRASE_PREFIXES: Tuple[str, ...] = tuple(
    sorted(PHRASE_SUBTYPE_GUID_PREFIXES.values(), key=len, reverse=True)
)


def guid_kind(guid: str) -> GuidKind:
    """Return the entity kind a GUID refers to based on its prefix.

    This is a pure string classification; it does not touch the database.
    """
    if guid.startswith("S_"):
        return "sentence"
    if guid.startswith(f"{IDIOM_GUID_PREFIX}_"):
        return "idiom"
    if any(guid.startswith(prefix) for prefix in _PHRASE_PREFIXES):
        return "phrase"
    return "lemma"


def get_sentence_by_guid(session: Session, guid: str) -> Optional[Sentence]:
    """Get a sentence by its GUID (e.g. "S_00001")."""
    result: Optional[Sentence] = session.query(Sentence).filter(Sentence.guid == guid).first()
    return result


def resolve_guid(
    session: Session, guid: str
) -> Tuple[GuidKind, Optional[Union[Lemma, Phrase, Sentence, Idiom]]]:
    """Resolve a GUID to ``(kind, object)``.

    The object is ``None`` if no row with that GUID exists, but ``kind`` is
    always returned (derived from the prefix) so callers can branch on it even
    for a missing row.
    """
    kind = guid_kind(guid)
    obj: Optional[Union[Lemma, Phrase, Sentence, Idiom]]
    if kind == "sentence":
        obj = get_sentence_by_guid(session, guid)
    elif kind == "phrase":
        obj = get_phrase_by_guid(session, guid)
    elif kind == "idiom":
        obj = get_idiom_by_guid(session, guid)
    else:
        obj = get_lemma_by_guid(session, guid)
    return kind, obj
