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

Not every sense is committed. A sense that lands on a catch-all ``*_other``
subtype for an open-class word is diverted to that same pending-import queue
instead of becoming a lemma, on the reasoning that "noun_other" out of 55
available noun subtypes is usually the LLM failing to place the sense rather
than a sense with genuinely no category.

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

from langtools.en.utils import (
    generate_3s_present,
    generate_comparative,
    generate_past_tense,
    generate_present_participle,
    generate_regular_plural,
    generate_superlative,
)
from langtools.collation import strip_diacritics
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
from words.pending_imports.staging import create_pending_import, find_pending_import
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
# Language whose translation disambiguates a queued sense for the human
# reviewer, matching what DRAMBLYS stages.
REVIEW_DISAMBIGUATION_LANGUAGE = "lt"
# How much extra leading material two translations may differ by and still count
# as the same word when collapsing duplicate senses. Sized for the Lithuanian
# aspect prefix ("saugoti" vs "apsaugoti"); wide enough for a prefix, too narrow
# to merge unrelated words.
_STEM_PREFIX_TOLERANCE = 3

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
      * ``"pending_review"`` -- every surviving sense went to the pending queue
        instead of the database (see ``pending_senses``); no lemma was created
      * ``"already_exists"`` -- the word is already accounted for; nothing done
      * ``"no_definitions"`` -- the LLM returned no usable senses
      * ``"error"`` -- a sense failed validation/GUID minting; see ``error``

    ``created`` and ``pending_review`` are not exclusive in effect: a word can
    create some lemmas and queue others, in which case the status is
    ``"created"`` and both lists are populated.
    """

    word: str
    status: str
    frequency_rank: Optional[int] = None
    # Surface form the rank came from. Differs from ``word`` when the corpus
    # holds only an inflection ("exclaimed" for "exclaim"); None when no rank
    # was found at all.
    frequency_rank_source: Optional[str] = None
    senses: List[SenseResult] = field(default_factory=list)
    # Senses routed to the pending-import queue for human subtype review rather
    # than written as lemmas. Their ``guid`` is empty: none was minted.
    pending_senses: List[SenseResult] = field(default_factory=list)
    dropped_senses: List[str] = field(default_factory=list)
    error: Optional[str] = None


def _inflected_candidates(word: str, pos_type: str) -> List[str]:
    """Return mechanically generated surface forms of ``word`` for this POS.

    Used only to find a corpus rank when the base form itself is absent: the
    19th/20th-century book corpora hold "exclaimed" but not "exclaim".

    Strictly POS-directed, and that is the whole point. Generating every
    inflection blind would be actively harmful, because the corpora are large
    enough that wrong-POS candidates hit real tokens -- "exclaim" yields
    "exclaimer", "further" yields "furtherer", and the noun plural collides with
    the 3s present outright ("guards" is both). A spurious match returns a
    *lower* rank, and ``_SENSE_BANDS`` reads lower as more frequent, so guessing
    wrong silently buys a word extra senses. Closed-class POS types get no
    candidates at all: they do not inflect, and anything generated for them
    would be noise.

    All generators here are rule-based, no LLM -- which also bounds what this
    can recover: irregular forms are out of reach ("strike" yields "striked",
    never "struck"), so a word whose corpus evidence is entirely irregular still
    comes back unranked. That is the pre-existing behavior, not a regression;
    closing it would mean consulting the conjugation tables.
    """
    if pos_type == "verb":
        return [
            generate_3s_present(word),
            generate_past_tense(word),
            generate_present_participle(word),
        ]
    if pos_type == "noun":
        return [generate_regular_plural(word)]
    if pos_type in ("adjective", "adverb"):
        return [generate_comparative(word), generate_superlative(word)]
    return []


def _lookup_frequency(
    session: Session, word: str, pos_type: str
) -> Tuple[Optional[int], Optional[str], List[Dict[str, Any]]]:
    """Return the word's corpus rank, the form it came from, and its breakdown.

    ``frequency_rank`` is the combined harmonic-mean rank on the ``WordToken``;
    the per-corpus list mirrors what DRAMBLYS records so the operation log
    carries the same provenance. All three are ``None``/empty when neither the
    word nor any of its inflections is in the frequency corpora -- which is not
    an error here: the word is added anyway, the rank just informs sense sizing.

    The exact form always wins when present. Only when it is absent does the
    best (numerically lowest) rank among ``_inflected_candidates`` stand in, so
    a word whose corpus evidence is entirely inflected still gets sized against
    real usage rather than falling to the tightest band by default.
    """
    candidates = [word] + [
        candidate for candidate in _inflected_candidates(word, pos_type) if candidate != word
    ]
    tokens = (
        session.query(WordToken)
        .filter(WordToken.language_code == "en", WordToken.token.in_(candidates))
        .all()
    )
    if not tokens:
        return None, None, []

    by_token = {token.token: token for token in tokens}
    chosen = by_token.get(word)
    if chosen is None:
        ranked: List[Tuple[int, WordToken]] = [
            (token.frequency_rank, token) for token in tokens if token.frequency_rank is not None
        ]
        if not ranked:
            return None, None, []
        chosen = min(ranked, key=lambda pair: pair[0])[1]

    corpus_info: List[Dict[str, Any]] = []
    annotations = (
        session.query(ExternalLexemeAnnotation)
        .filter(
            ExternalLexemeAnnotation.word_token_id == chosen.id,
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
    return chosen.frequency_rank, chosen.token, corpus_info


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


def _normalize_translation(text: Optional[str]) -> str:
    """Accent-fold and case-fold one translation for duplicate comparison."""
    return strip_diacritics((text or "").strip()).lower()


def _same_stem(first: str, second: str) -> bool:
    """Whether two normalized translations are one word with a prefix apart.

    Lithuanian marks aspect with a prefix, so the LLM's two "guard" senses came
    back as ``saugoti`` and ``apsaugoti`` -- the same verb, described twice.
    Matching a bare suffix relation with a short tolerance catches that without
    doing real stemming: ``proteger``/``protéger`` is already handled by the
    accent fold, and unrelated words rarely differ by only a two-letter prefix.

    Order-independent: the longer string is chosen before testing the suffix
    relation, so the caller need not normalize argument order.
    """
    if not first or not second:
        return False
    if first == second:
        return True
    longer, shorter = (first, second) if len(first) >= len(second) else (second, first)
    extra = len(longer) - len(shorter)
    return 0 < extra <= _STEM_PREFIX_TOLERANCE and longer.endswith(shorter)


def _translations_match(first: Tuple[str, ...], second: Tuple[str, ...]) -> bool:
    """Whether two whole translation tuples describe the same sense.

    Every language must agree. A real distinction shows up as different words in
    several languages at once -- "further"'s distance and intensity senses differ
    in lt/es/fr together -- so requiring unanimity keeps those apart while still
    collapsing the accent/prefix noise.
    """
    return all(
        _same_stem(left, right) if (left and right) else left == right
        for left, right in zip(first, second)
    )


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

    Comparison is not literal. Exact matching let "guard" through as two
    ``verb_other`` senses that were the same sense twice, because the two rows
    read lt ``saugoti``/``apsaugoti``, es ``proteger``/``protéger`` -- an accent
    and a prefix apart. Each translation is accent-folded, and two are treated
    as the same when one is a suffix of the other with at most
    ``_STEM_PREFIX_TOLERANCE`` characters of extra leading material.

    Returns:
        (kept senses, human-readable descriptions of the senses collapsed)
    """
    kept: List[Dict[str, Any]] = []
    kept_keys: List[Tuple[str, Tuple[str, ...], str]] = []
    collapsed: List[str] = []

    for sense in senses:
        by_lang_code = convert_llm_response_to_lang_codes(sense)
        translations = tuple(
            _normalize_translation(by_lang_code.get(lang_code))
            for lang_code in TRANSLATION_LANGUAGES
        )
        if not any(translations):
            kept.append(sense)
            continue

        pos_type = sense.get("pos") or ""
        definition = (sense.get("definition") or "")[:40]

        duplicate_of = next(
            (
                seen_definition
                for seen_pos, seen_translations, seen_definition in kept_keys
                if seen_pos == pos_type and _translations_match(seen_translations, translations)
            ),
            None,
        )
        if duplicate_of is not None:
            collapsed.append(f"{definition} (same pos+translations as {duplicate_of!r})")
            continue

        kept_keys.append((pos_type, translations, definition))
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


def _needs_subtype_review(pos_type: str, pos_subtype: str) -> bool:
    """Whether this sense should go to the pending queue instead of the database.

    ``*_other`` is the catch-all subtype, and on an open-class word it usually
    means the LLM could not place the sense rather than that the sense genuinely
    has no category -- noun has 55 subtypes and verb 14, so "noun_other" is a
    near-miss worth a human look before it becomes a lemma.

    Restricted to the open-class POS types on purpose. Every closed-class type
    (preposition, conjunction, article, determiner, pronoun, interjection) has
    ``<pos>_other`` as its *only* subtype, so treating "_other" as suspicious
    there would divert every preposition in the language to review.
    """
    return pos_type in MAJOR_POS_TYPES and pos_subtype.endswith("_other")


def _stage_for_review(
    session: Session,
    word: str,
    sense: Dict[str, Any],
    *,
    pos_type: str,
    pos_subtype: str,
    definition_text: str,
    frequency_rank: Optional[int],
    source: str,
) -> bool:
    """Write one sense to the pending-import queue. Returns False if already there.

    ``disambiguation_translation`` is NOT NULL on ``PendingImport``, so it falls
    back to the definition when the LLM returned no Lithuanian -- the same
    fallback ``stage_missing_words_for_import`` uses.
    """
    if find_pending_import(session, word, definition=definition_text) is not None:
        return False

    by_lang_code = convert_llm_response_to_lang_codes(sense)
    disambiguation = (by_lang_code.get(REVIEW_DISAMBIGUATION_LANGUAGE) or "").strip()

    create_pending_import(
        session,
        english_word=word,
        definition=definition_text,
        disambiguation_translation=disambiguation or definition_text,
        disambiguation_language=REVIEW_DISAMBIGUATION_LANGUAGE,
        pos_type=pos_type,
        pos_subtype=pos_subtype,
        source=source,
        frequency_rank=frequency_rank,
        sense_prominence=sense.get("sense_prominence"),
        notes=f"add_word: {pos_subtype} needs subtype review before import",
    )
    session.commit()
    return True


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


def _query_senses(client: LinguisticClient, word: str) -> List[Dict[str, Any]]:
    """Ask the LLM for every sense of the word. One LLM call, no filtering.

    Split from :func:`_select_senses` because selection is frequency-sized and
    the frequency lookup is POS-directed -- so the POS has to come back from
    this call before the rank can be looked up. Nothing about the call itself
    depends on the rank.
    """
    definitions_list, success = client.query_definitions(word)
    if not success or not definitions_list:
        return []
    return definitions_list


def _leading_pos_type(definitions_list: List[Dict[str, Any]]) -> str:
    """POS of the most prominent sense, used to direct the frequency lookup.

    ``query_definitions`` returns senses prominence-ordered, and
    ``_apply_pos_sense_cap`` already treats the first sense's POS as the word's
    POS -- mixed-POS answers are the LLM guessing. Same assumption here.
    """
    if not definitions_list:
        return ""
    return (definitions_list[0].get("pos") or "").lower()


def _select_senses(
    definitions_list: List[Dict[str, Any]], frequency_rank: Optional[int]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Keep the senses worth adding from an already-fetched definitions list.

    Selection is frequency-sized (``_sense_bounds``), extended to include senses
    tied in prominence at the ceiling (``_extend_for_prominence_ties``), then
    capped for closed-class parts of speech (``_apply_pos_sense_cap``), then
    collapsed where the LLM over-split into translation-identical senses
    (``_drop_translation_duplicates``).

    Returns:
        (selected senses, human-readable descriptions of the senses dropped)
    """
    if not definitions_list:
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
) -> AddWordResult:
    """Add a single English word to the database, from just the word.

    Runs the full pipeline: existence guard, one LLM call for the word's senses,
    a POS-directed frequency lookup, frequency-sized and closed-class-capped
    sense selection, translation-duplicate collapse, then one lemma per
    surviving sense with a minted GUID and the translations the definitions call
    returned.

    Note the order: the frequency lookup follows the LLM call rather than
    preceding it, because knowing which inflections to search the corpora for
    requires knowing the word's POS. A word the LLM cannot define therefore
    returns with ``frequency_rank`` unset -- there was no POS to look it up
    with, and nothing left to size.

    The word is committed per sense on success (a multi-sense word is a series
    of small writes, not one all-or-nothing transaction), matching how the
    batch importer behaves.

    There is deliberately no preview mode. Showing what would be written
    requires the LLM call, and that call is non-deterministic, so a preview does
    not predict what a subsequent committing run produces -- it costs money to
    show a result that will not reproduce.

    Args:
        session: Database session.
        word: English word to add.
        config: Data source configuration for the ``LinguisticClient``.
        model: LLM model override; falls back to ``config.model``.
        source: Operation-log source tag.

    Returns:
        An :class:`AddWordResult` describing what was created.
    """
    normalized = word.strip()
    if not normalized:
        return AddWordResult(word=word, status="error", error="word must be non-empty")

    # Existence guard: lemmas, disambiguated lemmas, en derivative forms and
    # alternate spellings. include_exclusions=True because this gates an import
    # -- a word rejected once should not be re-added.
    if word_exists_in_english(session, normalized, include_exclusions=True):
        return AddWordResult(word=normalized, status="already_exists")

    client_config = config.with_model(model) if model else config
    client = LinguisticClient(config=client_config)
    client_model = client_config.model

    # The definitions call comes first because the frequency lookup needs the
    # word's POS to know which inflections to look for, and only the LLM knows
    # the POS. Sense *selection* then consumes the rank, so the order is
    # definitions -> POS -> rank -> selection.
    definitions_list = _query_senses(client, normalized)
    if not definitions_list:
        return AddWordResult(word=normalized, status="no_definitions")

    frequency_rank, rank_source, corpus_info = _lookup_frequency(
        session, normalized, _leading_pos_type(definitions_list)
    )
    best_corpus_rank = min((c["rank"] for c in corpus_info if c["rank"] is not None), default=None)

    senses, dropped = _select_senses(definitions_list, frequency_rank)
    if not senses:
        return AddWordResult(
            word=normalized,
            status="no_definitions",
            frequency_rank=frequency_rank,
            frequency_rank_source=rank_source,
            dropped_senses=dropped,
        )

    result = AddWordResult(
        word=normalized,
        status="created",
        frequency_rank=frequency_rank,
        frequency_rank_source=rank_source,
        dropped_senses=dropped,
    )

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
                    frequency_rank_source=rank_source,
                    senses=result.senses,
                    dropped_senses=dropped,
                    error=f"LLM gave {pos_error}",
                )
            assert pos_subtype is not None  # _validate_pos rejects None

            # A catch-all subtype on an open-class word is usually the LLM
            # failing to place the sense. Queue it for review rather than
            # minting a GUID that a human would have to undo.
            if _needs_subtype_review(pos_type, pos_subtype):
                staged = _stage_for_review(
                    session,
                    normalized,
                    sense,
                    pos_type=pos_type,
                    pos_subtype=pos_subtype,
                    definition_text=definition_text,
                    frequency_rank=frequency_rank,
                    source=source,
                )
                if staged:
                    result.pending_senses.append(
                        SenseResult(
                            guid="",
                            pos_type=pos_type,
                            pos_subtype=pos_subtype,
                            definition_text=definition_text,
                            sense_prominence=prominence,
                            translations={
                                code: value
                                for code, value in convert_llm_response_to_lang_codes(sense).items()
                                if code in TRANSLATION_LANGUAGES and value
                            },
                        )
                    )
                else:
                    dropped.append(f"{definition_text[:40]} (already in the pending queue)")
                continue

            try:
                guid = generate_guid(session, pos_type, pos_subtype)
            except ValueError as exc:
                session.rollback()
                return AddWordResult(
                    word=normalized,
                    status="error",
                    frequency_rank=frequency_rank,
                    frequency_rank_source=rank_source,
                    senses=result.senses,
                    dropped_senses=dropped,
                    error=f"GUID generation: {exc}",
                )

            sense_result = SenseResult(
                guid=guid,
                pos_type=pos_type,
                pos_subtype=pos_subtype,
                definition_text=definition_text,
                sense_prominence=prominence,
            )

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
    except Exception:
        session.rollback()
        raise

    if not result.senses:
        # Distinguish "the LLM gave us nothing usable" from "everything it gave
        # us is waiting on a human": the second is a queue to work through, not
        # a dead end.
        result.status = "pending_review" if result.pending_senses else "no_definitions"
    return result
