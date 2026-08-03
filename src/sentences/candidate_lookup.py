"""Multi-language candidate lemma lookup for sentence decomposition.

Given a sentence with translations in several languages, produce a flat ranked
list of candidate lemmas for the sentence as a whole. Candidates are sourced
from every language for which the sentence has a translation: any lemma whose
``lemma_text`` or ``DerivativeForm`` matches a token in some language's
translation becomes a candidate. The ranking score for each candidate is the
number of those languages whose translation contains a matching form.

The score is an internal sort key only; it is not surfaced to the LLM. The
Phase-3 prompt receives an ungrouped list of CandidateLemma rows in score
order. Stage-3 decomposition selects/validates per word.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from langtools.tokenizer import tokenize
from storage.models.schema import DerivativeForm, Lemma, LemmaTranslation, SentenceTranslation
from storage.translation_helpers import LANGUAGE_FIELDS, get_translation

logger = logging.getLogger(__name__)

# Languages searched for candidate lemmas (their tokens are matched against
# Lemma.lemma_text / DerivativeForm). These are the languages a sentence is
# expected to be translated into during the pipeline.
DEFAULT_SOURCE_LANGUAGES: List[str] = ["en", "fr", "lt", "zh", "es", "bn", "uk", "kn"]

# Cap on the flat candidate list passed to the LLM.
DEFAULT_MAX_CANDIDATES = 30

# Characters stripped from token boundaries before matching.
_PUNCTUATION_STRIP = ".,!?;:\"'()[]{}—-…"


def _forms_match(token: str, lemma_form: str, language_code: str) -> bool:
    """Case-insensitive exact match in every language.

    We previously allowed substring containment for CJK (``SUBSTRING_MATCH_LANGUAGES``)
    as a fallback for jieba mis-segmentation, but single-character function
    words like ``的`` then matched hundreds of unrelated lemmas whose
    translations happened to contain that character, drowning out real
    candidates. Exact match across the board trades that for occasional
    false negatives on compound CJK tokens, which is the correct tradeoff
    here. The ``language_code`` parameter is retained for callers but no
    longer affects matching.
    """
    del language_code  # no longer used; retained in signature for callers
    return token.lower() == lemma_form.lower()


@dataclass
class CandidateLemma:
    """One candidate lemma for a sentence."""

    guid: str
    lemma_text: str
    disambiguation: str
    pos: str
    definition: str
    translations: Dict[str, str] = field(default_factory=dict)
    # Number of source languages whose sentence translation contains a known
    # form of this lemma. Used only as a sort key, not surfaced to the LLM.
    match_score: int = 0
    # Languages whose translation matched (debug/tests).
    matched_languages: List[str] = field(default_factory=list)


def _normalize_token(token: str) -> str:
    """Strip surrounding punctuation and lowercase."""
    return token.strip(_PUNCTUATION_STRIP).strip().lower()


def _all_tokens(text: str, language_code: str) -> List[str]:
    """Tokenize and return all tokens (lowercased, de-punctuated)."""
    out: List[str] = []
    for raw in tokenize(text, language_code):
        token = _normalize_token(raw)
        if token:
            out.append(token)
    return out


def _find_candidate_lemmas_in_language(
    session: Session, language_code: str, token: str
) -> List[Lemma]:
    """Find all Lemma rows plausibly matching a surface token in one language.

    For English (``en``): match by ``Lemma.lemma_text`` (case-insensitive) and
    by English-coded ``DerivativeForm`` rows.

    For other languages: match against the language-specific translation
    column on ``Lemma`` (via ``LANGUAGE_FIELDS``) and against ``DerivativeForm``
    rows for that language.
    """
    seen_ids: Set[int] = set()
    out: List[Lemma] = []

    # Base-translation match. English lives on Lemma.lemma_text; every other
    # supported language lives on LemmaTranslation.
    field_info = LANGUAGE_FIELDS.get(language_code)
    if field_info is not None:
        _field_name, _display, use_translation_table = field_info
        if use_translation_table:
            # Exact match in every language. CJK previously used substring
            # LIKE here, but single-character function-word tokens (e.g. zh
            # ``的``, ``了``, ``是``) matched hundreds of unrelated lemmas
            # whose translations happened to contain that character, drowning
            # out real candidates. The cost is occasional false negatives
            # when jieba returns a compound like ``好朋友`` and the DB only
            # has ``朋友`` — acceptable to keep the candidate list clean.
            trans_rows = (
                session.query(LemmaTranslation.lemma_id)
                .filter(
                    LemmaTranslation.language_code == language_code,
                    func.lower(LemmaTranslation.translation) == token,
                )
                .all()
            )
            trans_lemma_ids = {row[0] for row in trans_rows}
            if trans_lemma_ids:
                direct = session.query(Lemma).filter(Lemma.id.in_(trans_lemma_ids)).all()
                for lemma in direct:
                    if lemma.id not in seen_ids:
                        seen_ids.add(lemma.id)
                        out.append(lemma)
        else:
            # English: column on Lemma.
            direct = session.query(Lemma).filter(func.lower(Lemma.lemma_text) == token).all()
            for lemma in direct:
                if lemma.id not in seen_ids:
                    seen_ids.add(lemma.id)
                    out.append(lemma)

    # DerivativeForm match for this language. Exact match across the board
    # (see _forms_match for why CJK no longer substring-matches).
    form_rows = (
        session.query(DerivativeForm.lemma_id, DerivativeForm.derivative_form_text)
        .filter(
            DerivativeForm.language_code == language_code,
            func.lower(DerivativeForm.derivative_form_text) == token,
        )
        .all()
    )
    form_lemma_ids = {row[0] for row in form_rows}

    new_ids = form_lemma_ids - seen_ids
    if new_ids:
        extra = session.query(Lemma).filter(Lemma.id.in_(new_ids)).all()
        for lemma in extra:
            if lemma.id not in seen_ids:
                seen_ids.add(lemma.id)
                out.append(lemma)

    return out


def find_lemmas_for_token(session: Session, language_code: str, token: str) -> List[Lemma]:
    """Return every lemma whose base form or derivative form matches one token.

    The public entry point onto the same matching the candidate ranker uses, for
    callers that already have a single surface token and want the lemmas behind
    it -- notably dialog vocabulary coverage, which asks "is this word in the
    dictionary yet?" of each token in a generated line.

    Args:
        session: Database session.
        language_code: Language the token is written in, e.g. "en".
        token: A single surface token; punctuation and case are normalized here,
            so callers may pass it raw.

    Returns:
        Matching lemmas, base-form matches first. Empty when nothing matches.
    """
    normalized = _normalize_token(token)
    if not normalized:
        return []
    return _find_candidate_lemmas_in_language(session, language_code, normalized)


def _collect_lemma_forms_in_language(
    session: Session, lemma_id: int, language_code: str
) -> List[str]:
    """Return all known surface strings of a lemma in a language (base + derivatives)."""
    forms: List[str] = []
    seen: Set[str] = set()

    def _push(value: Optional[str]) -> None:
        if not value:
            return
        lowered = value.strip().lower()
        if not lowered or lowered in seen:
            return
        seen.add(lowered)
        forms.append(lowered)

    try:
        lemma = session.get(Lemma, lemma_id)
        if lemma is not None:
            base = get_translation(session, lemma, language_code)
            _push(base)
    except (ValueError, KeyError):
        pass

    rows = (
        session.query(DerivativeForm.derivative_form_text)
        .filter(
            DerivativeForm.lemma_id == lemma_id,
            DerivativeForm.language_code == language_code,
        )
        .all()
    )
    for row in rows:
        _push(row[0])

    return forms


def _language_confirms_lemma(
    session: Session,
    lemma_id: int,
    language_code: str,
    tokens: Sequence[str],
) -> bool:
    """True if any known form of the lemma in this language matches some token."""
    if not tokens:
        return False
    lemma_forms = _collect_lemma_forms_in_language(session, lemma_id, language_code)
    if not lemma_forms:
        return False
    for lemma_form in lemma_forms:
        for token in tokens:
            if _forms_match(token, lemma_form, language_code):
                return True
    return False


def _build_candidate(
    session: Session,
    lemma: Lemma,
    translation_languages: Sequence[str],
    score: int,
    matched_languages: List[str],
) -> Optional[CandidateLemma]:
    """Build a CandidateLemma from a Lemma row. Returns None if no GUID."""
    if not lemma.guid:
        return None
    translations: Dict[str, str] = {}
    for lang in translation_languages:
        if lang not in LANGUAGE_FIELDS:
            continue
        try:
            value = get_translation(session, lemma, lang)
        except (ValueError, KeyError):
            continue
        if value:
            translations[lang] = value
    return CandidateLemma(
        guid=lemma.guid,
        lemma_text=lemma.lemma_text,
        disambiguation=lemma.disambiguation or "",
        pos=lemma.pos_type,
        definition=lemma.definition_text or "",
        translations=translations,
        match_score=score,
        matched_languages=matched_languages,
    )


def _run_candidate_lookup(
    session: Session,
    translations_by_language: Dict[str, str],
    source_languages: Sequence[str],
    max_candidates: int,
) -> List[CandidateLemma]:
    """Core multi-language candidate lookup. Returns a flat ranked list."""
    # Tokenize each language's translation once.
    tokens_by_language: Dict[str, List[str]] = {}
    unique_tokens_by_language: Dict[str, List[str]] = {}
    for lang in source_languages:
        text = translations_by_language.get(lang)
        if not text:
            continue
        all_toks = _all_tokens(text, lang)
        if not all_toks:
            continue
        tokens_by_language[lang] = all_toks
        seen: Set[str] = set()
        uniq: List[str] = []
        for token in all_toks:
            if token not in seen:
                seen.add(token)
                uniq.append(token)
        unique_tokens_by_language[lang] = uniq

    if not unique_tokens_by_language:
        return []

    # 1. Source candidate lemmas from every language's tokens.
    candidates_by_id: Dict[int, Lemma] = {}
    for lang, tokens in unique_tokens_by_language.items():
        for token in tokens:
            for lemma in _find_candidate_lemmas_in_language(session, lang, token):
                if lemma.id not in candidates_by_id:
                    candidates_by_id[lemma.id] = lemma

    if not candidates_by_id:
        return []

    # 2. Score each candidate by # of source languages whose translation
    #    contains a known form of the lemma.
    built: List[CandidateLemma] = []
    for lemma in candidates_by_id.values():
        score = 0
        matched: List[str] = []
        for lang in source_languages:
            lang_tokens = tokens_by_language.get(lang)
            if not lang_tokens:
                continue
            if _language_confirms_lemma(session, lemma.id, lang, lang_tokens):
                score += 1
                matched.append(lang)
        candidate = _build_candidate(session, lemma, list(source_languages), score, matched)
        if candidate is not None:
            built.append(candidate)

    # 3. Sort: score desc, then lemma_text/guid for determinism.
    built.sort(key=lambda c: (-c.match_score, c.lemma_text.lower(), c.guid))
    return built[:max_candidates]


def find_candidate_lemmas_for_sentence(
    session: Session,
    sentence_id: int,
    *,
    source_languages: Optional[Sequence[str]] = None,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> List[CandidateLemma]:
    """Flat ranked list of candidate lemmas for a sentence.

    Reads every available ``SentenceTranslation`` row in ``source_languages``
    (defaults to :data:`DEFAULT_SOURCE_LANGUAGES`), pulls candidate lemmas
    that match any token in any of those translations, and ranks them by the
    number of those languages that confirm each candidate via a matching
    surface form or derivative form.

    Args:
        session: Database session.
        sentence_id: Sentence to analyze.
        source_languages: Languages whose translations are searched and used
            for scoring. Defaults to :data:`DEFAULT_SOURCE_LANGUAGES`.
        max_candidates: Cap on the returned list.

    Returns:
        Flat list of :class:`CandidateLemma`, sorted by descending match score.
        Empty when the sentence has no translations in any source language.
    """
    effective_sources = list(source_languages or DEFAULT_SOURCE_LANGUAGES)
    rows = (
        session.query(SentenceTranslation)
        .filter(
            SentenceTranslation.sentence_id == sentence_id,
            SentenceTranslation.language_code.in_(effective_sources),
        )
        .all()
    )
    translations_by_language = {row.language_code: row.translation_text for row in rows}
    return _run_candidate_lookup(
        session,
        translations_by_language=translations_by_language,
        source_languages=effective_sources,
        max_candidates=max_candidates,
    )


def find_candidate_lemmas_from_translations(
    session: Session,
    *,
    translations: Dict[str, str],
    source_languages: Optional[Sequence[str]] = None,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> List[CandidateLemma]:
    """In-memory variant of :func:`find_candidate_lemmas_for_sentence`.

    ``translations`` is ``{language_code: translation_text}``. Entries whose
    language codes are not in ``source_languages`` (after defaulting) are
    ignored.
    """
    effective_sources = list(source_languages or DEFAULT_SOURCE_LANGUAGES)
    filtered = {
        lang: text for lang, text in translations.items() if lang in effective_sources and text
    }
    return _run_candidate_lookup(
        session,
        translations_by_language=filtered,
        source_languages=effective_sources,
        max_candidates=max_candidates,
    )
