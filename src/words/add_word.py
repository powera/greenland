"""Add a single English word to the database, from just the word.

This is the intelligent word-addition pipeline: given a bare English word, it
queries the LLM for the word's senses, decides which senses are worth adding
(sized by the word's corpus frequency and capped for closed-class parts of
speech), collapses senses the LLM over-split, and writes one lemma per surviving
sense with a freshly minted GUID and the translations the definitions call
already returned.

It is the single implementation of that pipeline. The HTTP endpoint
``POST /api/v1/words/add`` calls :func:`add_word`; batch scripts should too,
rather than re-deriving sense selection and dedup. DRAMBLYS keeps its own
two-step pending-import flow (staging queue + human review) for a different
workflow, but shares the same ``select_senses_to_add`` / ``query_definitions``
building blocks.

The "does the database already have this word?" guard is
``word_exists_in_english`` -- the canonical check that folds in lemmas,
disambiguated lemmas, English derivative forms and alternate spellings
(``variant_forms``), so "grey" resolves to the existing "gray" rather than
splitting one lexeme across two rows.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from storage.backend.config import DataSourceConfig
from storage.crud.operation_log import log_translation_change
from storage.models.guid_prefixes import SUBTYPE_GUID_PREFIXES
from storage.models.schema import (
    SENSE_PROMINENCE_COMMON,
    ExternalLexemeAnnotation,
    Lemma,
    WordToken,
)
from storage.queries.lemma import word_exists_in_english
from storage.translation_helpers import convert_llm_response_to_lang_codes, set_translation
from storage.utils.guid import generate_guid
from wordfreq.translation.client import LinguisticClient
from wordfreq.translation.constants import MAJOR_POS_TYPES
from wordfreq.translation.definitions import (
    DEFINITIONS_PROMPT_LANGUAGES,
    SENSE_PROMINENCE_ORDER,
    select_senses_to_add,
)

logger = logging.getLogger(__name__)

# Per CLAUDE.md: newly added words default to -1 (unset difficulty).
DIFFICULTY_LEVEL = -1
# Languages the definitions call already returns per sense, stored as the lemma
# is created so no second LLM call is needed for them.
TRANSLATION_LANGUAGES: Tuple[str, ...] = DEFINITIONS_PROMPT_LANGUAGES

# Frequency-driven sense sizing. A word's overall corpus rank sets only the
# *ceiling* on how many senses to bother with -- it is a signal about the word,
# not about any one meaning. Whether a given sense is worth a lemma is decided
# by that sense's own ``sense_prominence`` inside select_senses_to_add, which
# keeps a sense beyond the first only while it stays "common" or better.
#
# So min_senses is held at 1: a frequent word with a single real sense ("dog")
# gets one lemma, not two padded out with a rare sense just because the word is
# common. Frequency raises the max so a common, genuinely polysemous word
# ("strike", "bank") can contribute its several *prominent* senses, while a rare
# or corpus-absent word is capped low. Ordered most-common first; the first band
# whose ``max_rank`` the word's rank falls at or under wins. ``None`` rank (word
# absent from the corpora) falls through to the last, tightest band.
_SENSE_MIN = 1
_SENSE_BANDS: Tuple[Tuple[Optional[int], int], ...] = (
    (2000, 4),  # rank <= 2000: up to 4 prominent senses
    (10000, 3),  # rank 2001-10000: up to 3
    (None, 2),  # rank > 10000 or unknown: up to 2
)


@dataclass
class SenseResult:
    """One lemma created (or that would be created) for a sense of the word."""

    guid: str
    pos_type: str
    pos_subtype: str
    definition_text: str
    sense_prominence: str
    translations: Dict[str, str] = field(default_factory=dict)


@dataclass
class AddWordResult:
    """Outcome of an :func:`add_word` call.

    ``status`` is one of:
      * ``"created"`` -- one or more lemmas were created (see ``senses``)
      * ``"already_exists"`` -- the word is already accounted for; nothing done
      * ``"no_definitions"`` -- the LLM returned no usable senses
      * ``"error"`` -- a sense failed validation/GUID minting; see ``error``
    """

    word: str
    status: str
    frequency_rank: Optional[int] = None
    senses: List[SenseResult] = field(default_factory=list)
    dropped_senses: List[str] = field(default_factory=list)
    error: Optional[str] = None


def _lookup_frequency(session: Session, word: str) -> Tuple[Optional[int], List[Dict[str, Any]]]:
    """Return the word's overall corpus rank and its per-corpus rank breakdown.

    ``frequency_rank`` is the combined harmonic-mean rank on the ``WordToken``;
    the per-corpus list mirrors what DRAMBLYS records so the operation log
    carries the same provenance. Both are ``None``/empty when the word is not in
    the frequency corpora -- which is not an error here: the word is added
    anyway, the rank just informs sense sizing.
    """
    token = (
        session.query(WordToken)
        .filter(WordToken.language_code == "en", WordToken.token == word)
        .first()
    )
    if token is None:
        return None, []

    corpus_info: List[Dict[str, Any]] = []
    annotations = (
        session.query(ExternalLexemeAnnotation)
        .filter(
            ExternalLexemeAnnotation.word_token_id == token.id,
            ExternalLexemeAnnotation.source.like("wordfreq_%"),
        )
        .all()
    )
    for annotation in annotations:
        corpus_info.append(
            {
                "corpus": annotation.source.removeprefix("wordfreq_"),
                "rank": annotation.ordinal_rank,
                "frequency": annotation.frequency,
            }
        )
    return token.frequency_rank, corpus_info


def _sense_bounds(frequency_rank: Optional[int]) -> Tuple[int, int]:
    """Return ``(min_senses, max_senses)`` for a word at this corpus rank.

    ``min_senses`` is always ``_SENSE_MIN`` (1): whether a word deserves a
    second sense is a question about that sense's ``sense_prominence``, not about
    how frequent the word is, and select_senses_to_add already keeps prominent
    senses beyond the first on its own. Frequency sets only ``max_senses`` -- the
    ceiling -- so a common polysemous word can contribute several prominent
    senses while a rare word is capped low. The closed-class cap in
    :func:`_apply_pos_sense_cap` tightens this further, per-POS.
    """
    for max_rank, max_senses in _SENSE_BANDS:
        if max_rank is None or (frequency_rank is not None and frequency_rank <= max_rank):
            return _SENSE_MIN, max_senses
    # _SENSE_BANDS ends with a None band, so this is unreachable; satisfy mypy.
    return _SENSE_MIN, 2


def _apply_pos_sense_cap(senses: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Cap closed-class words to a single sense.

    Only the four major (open-class) POS types -- noun, verb, adjective, adverb
    -- carry several genuinely distinct senses worth separate lemmas. The LLM
    reliably over-splits closed-class words into overlapping senses ("unless"
    comes back with two near-identical conjunction senses), so once the word's
    POS is known to be closed-class, keep only the most prominent sense.

    ``select_senses_to_add`` has already ordered senses by prominence, so the
    first surviving sense is the one to keep. POS is read from the first sense:
    a word is one part of speech here, and mixed-POS answers are the LLM
    guessing.

    Returns:
        (kept senses, human-readable descriptions of the senses dropped)
    """
    if not senses:
        return senses, []
    pos_type = (senses[0].get("pos") or "").lower()
    if pos_type in MAJOR_POS_TYPES or len(senses) <= 1:
        return senses, []

    dropped = [
        f"{(sense.get('definition') or '')[:40]} (closed-class {pos_type}: 1 sense only)"
        for sense in senses[1:]
    ]
    return senses[:1], dropped


def _drop_translation_duplicates(
    senses: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Collapse senses that share a pos_type and every translation.

    The LLM over-splits grammatical words: "continue" comes back as a separate
    intransitive "keep happening" and transitive "make something keep happening"
    whose definitions differ but whose lt/es/fr/zh translations are identical --
    the signal that these are one sense described twice. Storing both would mint
    two GUIDs no downstream consumer can tell apart.

    Keyed on pos_type plus the translation tuple, ignoring pos_subtype and
    definition text: a differing subtype on identical translations is the LLM
    guessing, not a real distinction. Senses arrive prominence-ordered, so the
    first one wins.

    Returns:
        (kept senses, human-readable descriptions of the senses collapsed)
    """
    kept: List[Dict[str, Any]] = []
    collapsed: List[str] = []
    seen: Dict[Tuple[str, ...], str] = {}

    for sense in senses:
        by_lang_code = convert_llm_response_to_lang_codes(sense)
        translations = tuple(
            (by_lang_code.get(lang_code) or "").strip().lower()
            for lang_code in TRANSLATION_LANGUAGES
        )
        if not any(translations):
            kept.append(sense)
            continue

        key = (sense.get("pos") or "",) + translations
        first = seen.get(key)
        if first is not None:
            definition = (sense.get("definition") or "")[:40]
            collapsed.append(f"{definition} (same pos+translations as {first!r})")
            continue

        seen[key] = (sense.get("definition") or "")[:40]
        kept.append(sense)

    return kept, collapsed


def _normalize_subtype(pos_type: str, pos_subtype: Optional[str]) -> Optional[str]:
    """Map an LLM-supplied subtype onto the spelling ``guid_prefixes`` expects.

    For the closed-class POS types the only subtype is "<pos>_other", but the
    LLM tends to answer with the bare pos name ("preposition") or "other".
    ``storage/utils/guid.py`` already special-cases exactly this for
    interjection; the same mismatch exists for preposition, conjunction,
    pronoun, article and determiner, so normalize them all here.
    """
    if pos_subtype is None:
        return None
    canonical = f"{pos_type}_other"
    subtypes = SUBTYPE_GUID_PREFIXES.get(pos_type, {})
    if canonical in subtypes and pos_subtype in (pos_type, "other", canonical):
        return canonical
    # Verbs/nouns/adjectives/adverbs spell their catch-all "<pos>_other" too,
    # while storage.utils.enums spells it plain "other".
    if pos_subtype == "other" and canonical in subtypes:
        return canonical
    return pos_subtype


def _validate_pos(pos_type: str, pos_subtype: Optional[str]) -> Optional[str]:
    """Return an error string if pos_type/pos_subtype are not a valid GUID pair.

    ``guid_prefixes`` is the binding constraint: a lemma needs a GUID, and
    ``storage.utils.enums`` lists pos_types ("modal", "auxiliary") that have no
    GUID prefix at all, and spells the catch-all subtype differently.
    """
    if pos_type not in SUBTYPE_GUID_PREFIXES:
        return f"pos_type {pos_type!r} has no GUID prefix; not a lemma pos_type"
    if pos_subtype is None:
        return f"pos_type {pos_type!r} requires a subtype"
    if pos_subtype not in SUBTYPE_GUID_PREFIXES[pos_type]:
        return f"invalid pos_subtype {pos_subtype!r} for {pos_type!r}"
    return None


def _prominence_rank(sense: Dict[str, Any]) -> int:
    """Ordinal of a sense's prominence (0 = very_common); unrated counts as common."""
    order = {value: index for index, value in enumerate(SENSE_PROMINENCE_ORDER)}
    default = order[SENSE_PROMINENCE_COMMON]
    return order.get(sense.get("sense_prominence", ""), default)


def _extend_for_prominence_ties(
    selected: List[Dict[str, Any]], definitions_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Re-include senses the ``max_senses`` ceiling split off mid-prominence-tier.

    ``max_senses`` is a soft target, not a hard cut. When the ceiling lands
    *between* prominence tiers -- two very_common senses with a max of two, the
    rest merely common -- that cut is right: keep the two, drop the commons.
    But when it lands *inside* a tier -- one very_common plus four common with a
    max of three -- cutting arbitrarily keeps three of the four equally-common
    senses and drops one for no reason but list position. In that case keep the
    whole tied tier.

    Only same-prominence senses are pulled back in, and only at the boundary
    tier of what ``select_senses_to_add`` already kept, so this never reaches
    down into ``uncommon``/``rare``: those stay dropped.

    Returns the (possibly extended) selection, most-prominent first.
    """
    if not selected:
        return selected

    boundary_rank = _prominence_rank(selected[-1])
    # Only extend within common-or-better tiers. If the boundary sense is only
    # there because min_senses forced an uncommon/rare one in, do not drag its
    # equally-marginal siblings along.
    if boundary_rank > _prominence_rank({"sense_prominence": SENSE_PROMINENCE_COMMON}):
        return selected

    kept_ids = {id(sense) for sense in selected}
    extras = [
        sense
        for sense in definitions_list
        if id(sense) not in kept_ids and _prominence_rank(sense) == boundary_rank
    ]
    return selected + extras


def _pick_senses(
    client: LinguisticClient, word: str, frequency_rank: Optional[int]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Ask the LLM for the word's senses and keep the ones worth adding.

    One LLM call. Selection is frequency-sized (``_sense_bounds``), extended to
    include senses tied in prominence at the ceiling (``_extend_for_prominence_ties``),
    then capped for closed-class parts of speech (``_apply_pos_sense_cap``), then
    collapsed where the LLM over-split into translation-identical senses
    (``_drop_translation_duplicates``).

    Returns:
        (selected senses, human-readable descriptions of the senses dropped)
    """
    definitions_list, success = client.query_definitions(word)
    if not success or not definitions_list:
        return [], []

    min_senses, max_senses = _sense_bounds(frequency_rank)
    selected = select_senses_to_add(definitions_list, max_senses=max_senses, min_senses=min_senses)
    selected = _extend_for_prominence_ties(selected, definitions_list)
    kept_ids = {id(sense) for sense in selected}
    dropped = [
        f"{(sense.get('definition') or '')[:40]} ({sense.get('sense_prominence', 'unrated')})"
        for sense in definitions_list
        if id(sense) not in kept_ids
    ]

    capped, cap_dropped = _apply_pos_sense_cap(selected)
    deduped, collapsed = _drop_translation_duplicates(capped)
    return [dict(sense) for sense in deduped], dropped + cap_dropped + collapsed


def _store_sense_translations(
    session: Session, lemma: Lemma, sense: Dict[str, Any], *, source: str, model: Optional[str]
) -> Dict[str, str]:
    """Save the translations the definitions call already returned for this sense.

    The definitions schema returns lt/es/fr/zh per sense, so they arrive with
    the definition at no extra LLM cost, and each sense gets its own
    translation. Field names map to language codes through translation_helpers,
    per CLAUDE.md -- no local mapping.

    Returns:
        The language code -> translation text pairs actually stored.
    """
    by_lang_code = convert_llm_response_to_lang_codes(sense)
    stored: Dict[str, str] = {}
    for lang_code in TRANSLATION_LANGUAGES:
        translation = (by_lang_code.get(lang_code) or "").strip()
        if not translation:
            continue
        set_translation(session, lemma, lang_code, translation)
        log_translation_change(
            session=session,
            source=source,
            operation_type="translation",
            lemma_id=lemma.id,
            language_code=lang_code,
            old_translation=None,
            new_translation=translation,
            guid=lemma.guid,
            model=model,
        )
        stored[lang_code] = translation
    return stored


def add_word(
    session: Session,
    word: str,
    *,
    config: DataSourceConfig,
    model: Optional[str] = None,
    source: str = "add_word",
    dry_run: bool = False,
) -> AddWordResult:
    """Add a single English word to the database, from just the word.

    Runs the full pipeline: existence guard, frequency lookup, one LLM call for
    the word's senses, frequency-sized and closed-class-capped sense selection,
    translation-duplicate collapse, then one lemma per surviving sense with a
    minted GUID and the translations the definitions call returned.

    The word is committed per sense on success (a multi-sense word is a series
    of small writes, not one all-or-nothing transaction), matching how the
    batch importer behaves. ``dry_run`` runs the whole pipeline -- including the
    LLM call, which is needed to show what would be written -- but writes
    nothing and rolls back.

    Args:
        session: Database session.
        word: English word to add.
        config: Data source configuration for the ``LinguisticClient``.
        model: LLM model override; falls back to ``config.model``.
        source: Operation-log source tag.
        dry_run: Run the pipeline without writing (still makes the LLM call).

    Returns:
        An :class:`AddWordResult` describing what was (or would be) created.
    """
    normalized = word.strip()
    if not normalized:
        return AddWordResult(word=word, status="error", error="word must be non-empty")

    # Existence guard: lemmas, disambiguated lemmas, en derivative forms and
    # alternate spellings. include_exclusions=True because this gates an import
    # -- a word rejected once should not be re-added.
    if word_exists_in_english(session, normalized, include_exclusions=True):
        return AddWordResult(word=normalized, status="already_exists")

    frequency_rank, corpus_info = _lookup_frequency(session, normalized)
    best_corpus_rank = min((c["rank"] for c in corpus_info if c["rank"] is not None), default=None)

    client_config = config.with_model(model) if model else config
    client = LinguisticClient(config=client_config)
    client_model = client_config.model

    senses, dropped = _pick_senses(client, normalized, frequency_rank)
    if not senses:
        return AddWordResult(
            word=normalized,
            status="no_definitions",
            frequency_rank=frequency_rank,
            dropped_senses=dropped,
        )

    result = AddWordResult(
        word=normalized,
        status="created",
        frequency_rank=frequency_rank,
        dropped_senses=dropped,
    )
    issued_guids: Dict[str, str] = {}

    try:
        for sense in senses:
            pos_type = (sense.get("pos") or "").lower()
            pos_subtype = _normalize_subtype(pos_type, sense.get("pos_subtype"))
            definition_text = sense.get("definition") or ""
            prominence = sense.get("sense_prominence") or SENSE_PROMINENCE_COMMON

            if not definition_text:
                logger.warning("Skipping empty definition for %r", normalized)
                continue

            pos_error = _validate_pos(pos_type, pos_subtype)
            if pos_error is not None:
                session.rollback()
                return AddWordResult(
                    word=normalized,
                    status="error",
                    frequency_rank=frequency_rank,
                    senses=result.senses,
                    dropped_senses=dropped,
                    error=f"LLM gave {pos_error}",
                )
            assert pos_subtype is not None  # _validate_pos rejects None

            try:
                guid = generate_guid(session, pos_type, pos_subtype)
            except ValueError as exc:
                session.rollback()
                return AddWordResult(
                    word=normalized,
                    status="error",
                    frequency_rank=frequency_rank,
                    senses=result.senses,
                    dropped_senses=dropped,
                    error=f"GUID generation: {exc}",
                )

            # In dry-run nothing is flushed, so generate_guid returns the same
            # GUID for same-subtype senses; note the collision rather than
            # reporting it twice as distinct.
            issued_guids.setdefault(guid, normalized)

            sense_result = SenseResult(
                guid=guid,
                pos_type=pos_type,
                pos_subtype=pos_subtype,
                definition_text=definition_text,
                sense_prominence=prominence,
            )

            if dry_run:
                preview = convert_llm_response_to_lang_codes(sense)
                sense_result.translations = {
                    code: preview[code] for code in TRANSLATION_LANGUAGES if preview.get(code)
                }
                result.senses.append(sense_result)
                continue

            new_lemma = Lemma(
                lemma_text=normalized,
                definition_text=definition_text,
                pos_type=pos_type,
                pos_subtype=pos_subtype,
                guid=guid,
                difficulty_level=DIFFICULTY_LEVEL,
                confidence=0.0,
                verified=False,
                sense_prominence=prominence,
            )
            session.add(new_lemma)
            session.flush()

            log_translation_change(
                session=session,
                source=source,
                operation_type="lemma_create",
                lemma_id=new_lemma.id,
                language_code="en",
                old_translation=None,
                new_translation=normalized,
                guid=guid,
                pos_type=pos_type,
                pos_subtype=pos_subtype,
                definition=definition_text,
                sense_prominence=prominence,
                model=client_model,
                best_corpus_rank=best_corpus_rank,
            )
            sense_result.translations = _store_sense_translations(
                session, new_lemma, sense, source=source, model=client_model
            )

            # Commit per sense: a multi-sense word is a series of small writes,
            # so a failure on a later sense does not discard the earlier ones.
            session.commit()
            result.senses.append(sense_result)

        if dry_run:
            session.rollback()
    except Exception:
        session.rollback()
        raise

    if not result.senses:
        result.status = "no_definitions"
    return result
