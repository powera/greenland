"""Persist decomposition output as ``SentenceWord`` rows.

The translate/decompose pipeline returns per-word dictionaries; turning those
into database rows means the same coercion work every time -- normalizing the
part of speech, resolving a lemma GUID the LLM named, and rejecting Phase-4
fields that only exist when the dependency pass ran and validated.

That loop previously lived inside ``GenysAgent._store_sentence``. Having it in
one place matters more than it looks: three separate copies of sentence-word
writing is how the codebase ended up with two word tables that nothing
reconciles. Every caller that stores a decomposition should come through here.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from sentences.translate_and_decompose import SYNTHETIC_GUID_PREFIX
from storage.crud.operation_log import SENTENCE_WORD_CREATE, log_batch_operation
from storage.crud.sentence_word import add_sentence_word
from storage.models.schema import Lemma, Sentence, SentenceWord

logger = logging.getLogger(__name__)


def is_real_guid(lemma_guid: str) -> bool:
    """True when the LLM named an actual database lemma.

    The ``SYN###`` branch is deprecated and should no longer fire: no prompt
    asks for synthetic ids any more, and every path now uses ``NONE`` for "no
    lemma matched". It is kept because a model can still emit the old format
    from memory, and treating ``SYN001`` as a real GUID would look up a lemma
    that cannot exist. A run that trips it is worth investigating.
    """
    if not lemma_guid:
        return False
    if lemma_guid.strip().lower() in {"", "none", "null"}:
        return False
    synthetic = (
        lemma_guid.startswith(SYNTHETIC_GUID_PREFIX)
        and lemma_guid[len(SYNTHETIC_GUID_PREFIX) :].isdigit()
    )
    if synthetic:
        logger.warning(
            "Deprecated synthetic lemma_guid %r from the LLM; prompts ask for "
            "NONE. Treating as unmatched.",
            lemma_guid,
        )
    return not synthetic


def _coerce_head_position(raw: Any) -> Optional[int]:
    """Phase-4 head position, or None when the pass did not run.

    ``bool`` is excluded explicitly because it is an ``int`` subclass in Python
    and ``True`` would silently become head position 1.
    """
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return int(raw)


def store_decomposition(
    session: Session,
    *,
    sentence: Sentence,
    language_code: str,
    words: Sequence[Dict[str, Any]],
    replace_existing: bool = False,
    source: Optional[str] = None,
) -> int:
    """Write one language's decomposition as ``SentenceWord`` rows.

    Does not commit; the caller owns the transaction.

    Args:
        session: Database session.
        sentence: The sentence being decomposed.
        language_code: Language of this decomposition.
        words: Per-word dictionaries from the pipeline, in sentence order. Keys
            honored: ``surface_form``, ``english_gloss``, ``part_of_speech``,
            ``grammatical_form``, ``lemma_guid``, ``ud_relation``,
            ``ud_head_position``.
        replace_existing: Delete this language's existing rows first. Off by
            default so a re-run cannot silently discard links a human or an
            earlier pass established; the unique key on
            ``(sentence_id, language_code, position)`` would otherwise reject
            the insert.
        source: Who is writing these, for the operation log. None skips logging.
            One entry is written per call, not per word row.

    Returns:
        Number of rows written.
    """
    if replace_existing:
        session.query(SentenceWord).filter(
            SentenceWord.sentence_id == sentence.id,
            SentenceWord.language_code == language_code,
        ).delete(synchronize_session=False)
        session.flush()

    written = 0
    linked_lemma_guids: List[str] = []
    for position, word_entry in enumerate(words):
        part_of_speech = str(word_entry.get("part_of_speech") or "").strip().lower() or "unknown"
        surface = str(word_entry.get("surface_form") or "").strip()
        english_gloss = str(word_entry.get("english_gloss") or "").strip()

        grammatical_form_raw = word_entry.get("grammatical_form")
        grammatical_form = (
            str(grammatical_form_raw).strip() if grammatical_form_raw is not None else None
        )

        word_lemma: Optional[Lemma] = None
        lemma_guid = str(word_entry.get("lemma_guid") or "").strip()
        if is_real_guid(lemma_guid):
            word_lemma = session.query(Lemma).filter(Lemma.guid == lemma_guid).first()
            if word_lemma is not None:
                linked_lemma_guids.append(lemma_guid)

        ud_relation_raw = word_entry.get("ud_relation")
        ud_relation = str(ud_relation_raw).strip() if ud_relation_raw is not None else None

        add_sentence_word(
            session,
            sentence=sentence,
            position=position,
            part_of_speech=part_of_speech,
            language_code=language_code,
            lemma=word_lemma,
            english_text=english_gloss or None,
            target_language_text=surface or None,
            grammatical_form=grammatical_form,
            declined_form=surface or None,
            ud_relation=ud_relation or None,
            ud_head_position=_coerce_head_position(word_entry.get("ud_head_position")),
        )
        written += 1

    session.flush()

    # One entry for the whole decomposition. Per-word entries would outnumber
    # every other kind of log in the table by an order of magnitude while
    # telling you nothing this does not.
    log_batch_operation(
        session,
        source=source,
        operation_type=SENTENCE_WORD_CREATE,
        entity_guid=sentence.guid,
        count=written,
        fact={
            "language_code": language_code,
            "linked_lemma_guids": linked_lemma_guids,
            "replaced_existing": replace_existing,
        },
    )

    return written
