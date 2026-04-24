"""Per-English-word candidate lemma lookup for sentence decomposition.

Given a sentence with an English translation and pivot-language translations
(stored as SentenceTranslation rows), produce a grouped mapping from each
English content word to a ranked list of candidate lemmas. The ranking uses
pivot-language evidence: a candidate lemma scores higher when more pivot
translations of the sentence contain a translation or derivative form of
that lemma.

This is the machinery that turns an ambiguous English word like "can" into
a list [can (modal), can (container)] with the right sense on top, given
pivot translations that only render one of the senses.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from langtools.tokenizer import tokenize
from sentences.analysis import SUBSTRING_MATCH_LANGUAGES
from storage.models.schema import DerivativeForm, Lemma, SentenceTranslation
from storage.translation_helpers import LANGUAGE_FIELDS, get_translation

logger = logging.getLogger(__name__)

# Default pivot languages for disambiguation. Typologically diverse so at
# least one usually distinguishes any given English sense ambiguity.
DEFAULT_PIVOT_LANGUAGES: List[str] = ["bn", "uk", "kn"]

# Default cap on candidates per English word. Set high enough to let the LLM
# see legitimate alternatives but low enough to keep the prompt tight.
DEFAULT_MAX_CANDIDATES_PER_WORD = 5

# Characters stripped from token boundaries before matching.
_PUNCTUATION_STRIP = ".,!?;:\"'()[]{}—-…"


def _forms_match(token: str, lemma_form: str, language_code: str) -> bool:
    """Case-insensitive exact match; substring containment for CJK scripts."""
    token_lower = token.lower()
    lemma_lower = lemma_form.lower()
    if token_lower == lemma_lower:
        return True
    if language_code in SUBSTRING_MATCH_LANGUAGES:
        if token in lemma_form or lemma_form in token:
            return True
    return False


@dataclass
class CandidateLemma:
    """One candidate lemma for an English surface word in a sentence."""

    guid: str
    lemma_text: str
    disambiguation: str
    pos: str
    definition: str
    translations: Dict[str, str] = field(default_factory=dict)
    # Number of pivot languages whose sentence translation contains a
    # translation/derivative form of this lemma. Higher = more evidence for
    # this sense.
    pivot_match_score: int = 0
    # Which pivot languages confirmed this lemma (useful for debugging).
    confirmed_pivots: List[str] = field(default_factory=list)


def _normalize_token(token: str) -> str:
    """Strip surrounding punctuation and lowercase."""
    return token.strip(_PUNCTUATION_STRIP).strip().lower()


def _unique_tokens(text: str, language_code: str) -> List[str]:
    """Tokenize and return unique tokens (lowercased, de-punctuated).

    No grammatical/function-word filtering — that would drop legitimate
    ambiguity drivers like English "can" (modal vs. container). Tokens that
    turn out to have no lemma candidates in the DB are dropped later.
    Order preserved, duplicates removed.
    """
    seen: Set[str] = set()
    out: List[str] = []
    for raw in tokenize(text, language_code):
        token = _normalize_token(raw)
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _all_tokens(text: str, language_code: str) -> List[str]:
    """Tokenize and return all tokens (lowercased, de-punctuated) without filtering.

    Used for scanning pivot translations, where we want to match on any form
    that appears regardless of whether English considers it grammatical.
    """
    out: List[str] = []
    for raw in tokenize(text, language_code):
        token = _normalize_token(raw)
        if token:
            out.append(token)
    return out


def _find_english_candidate_lemmas(session: Session, english_token: str) -> List[Lemma]:
    """Find all Lemma rows plausibly matching an English surface word.

    Covers exact + case-insensitive lemma_text and derivative forms keyed in
    the English DerivativeForm table (so "playing" resolves to the "play"
    lemma). Returns deduped lemmas.
    """
    # Exact / case-insensitive lemma_text match.
    direct = session.query(Lemma).filter(func.lower(Lemma.lemma_text) == english_token).all()

    # English derivative forms (e.g., "playing" -> "play" lemma).
    form_rows = (
        session.query(DerivativeForm.lemma_id)
        .filter(
            DerivativeForm.language_code == "en",
            func.lower(DerivativeForm.derivative_form_text) == english_token,
        )
        .all()
    )
    form_lemma_ids = {row[0] for row in form_rows}

    seen_ids: Set[int] = set()
    out: List[Lemma] = []
    for lemma in direct:
        if lemma.id not in seen_ids:
            seen_ids.add(lemma.id)
            out.append(lemma)
    if form_lemma_ids - seen_ids:
        extra = session.query(Lemma).filter(Lemma.id.in_(form_lemma_ids - seen_ids)).all()
        for lemma in extra:
            if lemma.id not in seen_ids:
                seen_ids.add(lemma.id)
                out.append(lemma)
    return out


def _collect_lemma_forms_in_language(
    session: Session, lemma_id: int, language_code: str
) -> List[str]:
    """Return all known surface strings of a lemma in a language.

    Combines the base translation (from get_translation) with all
    DerivativeForm.derivative_form_text rows keyed to this lemma + language.
    Empty / None entries are dropped. Results lowercased and deduped while
    preserving insertion order.
    """
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

    # Base translation
    try:
        lemma = session.get(Lemma, lemma_id)
        if lemma is not None:
            base = get_translation(session, lemma, language_code)
            _push(base)
    except (ValueError, KeyError):
        # Unsupported language code — treat as no base translation.
        pass

    # Derivative forms in this language
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


def _score_pivot_confirmations(
    session: Session,
    lemma_id: int,
    pivot_tokens_by_language: Dict[str, List[str]],
) -> Tuple[int, List[str]]:
    """For one lemma, count how many pivot languages confirm it.

    A language confirms the lemma when at least one of its known forms
    (translation + derivative forms in that language) matches a token in
    that language's pivot-sentence tokenization. Returns (score, langs).
    """
    score = 0
    confirmed: List[str] = []
    for lang, tokens in pivot_tokens_by_language.items():
        if not tokens:
            continue
        lemma_forms = _collect_lemma_forms_in_language(session, lemma_id, lang)
        if not lemma_forms:
            continue
        matched = False
        for lemma_form in lemma_forms:
            for token in tokens:
                if _forms_match(token, lemma_form, lang):
                    matched = True
                    break
            if matched:
                break
        if matched:
            score += 1
            confirmed.append(lang)
    return score, confirmed


def _build_candidate(
    session: Session,
    lemma: Lemma,
    translation_languages: Sequence[str],
    score: int,
    confirmed: List[str],
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
        pivot_match_score=score,
        confirmed_pivots=confirmed,
    )


def find_candidate_lemmas_by_english_word(
    session: Session,
    sentence_id: int,
    *,
    pivot_languages: Optional[Sequence[str]] = None,
    target_languages: Optional[Sequence[str]] = None,
    max_candidates_per_word: int = DEFAULT_MAX_CANDIDATES_PER_WORD,
) -> Dict[str, List[CandidateLemma]]:
    """Return candidate lemmas grouped by English surface word.

    The sentence must have an English SentenceTranslation. Pivot-language
    translations (if stored) drive the ranking: for each English content
    word, candidate lemmas are scored by how many pivot languages render
    the sentence using a known translation or derivative form of that lemma.

    Unlike the existing sentences.analysis.find_candidate_lemmas_for_sentence
    (which reads SentenceWord rows — i.e. post-decomposition), this function
    works pre-decomposition from raw translation strings.

    Args:
        session: Database session.
        sentence_id: Sentence to analyze. Must have an English translation.
        pivot_languages: Languages used purely for disambiguation. Defaults
            to DEFAULT_PIVOT_LANGUAGES. Missing translations are silently
            skipped.
        target_languages: Final target languages. Their translations are
            included in CandidateLemma.translations for prompt rendering,
            but are NOT used for scoring (to avoid confusing the two roles).
        max_candidates_per_word: Cap applied after ranking. When the top
            score is > 0, score-0 candidates are dropped before capping.

    Returns:
        {english_surface_word: [CandidateLemma, ...]} — keys are the
        lowercased English tokens from the sentence, ordered by first
        appearance. Each value list is sorted by pivot_match_score desc
        (ties broken by lemma_text for determinism) and capped. Words with
        no candidates are omitted.
    """
    pivot_languages = list(pivot_languages or DEFAULT_PIVOT_LANGUAGES)
    target_languages = list(target_languages or [])
    translation_langs: List[str] = []
    for lang in list(target_languages) + list(pivot_languages):
        if lang not in translation_langs:
            translation_langs.append(lang)

    # Load English sentence text.
    english_trans = (
        session.query(SentenceTranslation)
        .filter_by(sentence_id=sentence_id, language_code="en")
        .first()
    )
    if english_trans is None:
        logger.debug("Sentence %s has no English translation; returning empty", sentence_id)
        return {}

    english_tokens = _unique_tokens(english_trans.translation_text, "en")
    if not english_tokens:
        return {}

    # Load pivot translations and tokenize.
    pivot_tokens_by_language: Dict[str, List[str]] = {}
    if pivot_languages:
        pivot_rows = (
            session.query(SentenceTranslation)
            .filter(
                SentenceTranslation.sentence_id == sentence_id,
                SentenceTranslation.language_code.in_(list(pivot_languages)),
            )
            .all()
        )
        for row in pivot_rows:
            pivot_tokens_by_language[row.language_code] = _all_tokens(
                row.translation_text, row.language_code
            )

    result: Dict[str, List[CandidateLemma]] = {}
    for english_token in english_tokens:
        lemmas = _find_english_candidate_lemmas(session, english_token)
        if not lemmas:
            continue
        built: List[CandidateLemma] = []
        for lemma in lemmas:
            score, confirmed = _score_pivot_confirmations(
                session, lemma.id, pivot_tokens_by_language
            )
            candidate = _build_candidate(session, lemma, translation_langs, score, confirmed)
            if candidate is not None:
                built.append(candidate)
        if not built:
            continue

        # Sort: score desc, then lemma_text asc for determinism.
        built.sort(key=lambda c: (-c.pivot_match_score, c.lemma_text.lower(), c.guid))

        # Drop score-0 candidates when at least one scores.
        if any(c.pivot_match_score > 0 for c in built):
            filtered = [c for c in built if c.pivot_match_score > 0]
        else:
            filtered = built

        result[english_token] = filtered[:max_candidates_per_word]
    return result
