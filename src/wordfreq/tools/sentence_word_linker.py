"""Unified sentence-word linking: resolve lemmas for sentences.

This module consolidates all strategies for matching words in sentences to
lemma records in the database. It provides:

- resolve_lemma_for_word(): Single-word resolution with a cascade of strategies
- resolve_lemmas_for_sentence(): Full sentence resolution using all available data
- find_lemma_by_text(): Consolidated text-based lemma lookup (replaces duplicated
  _find_lemma_for_word in guided_sentences.py and llm_sentences.py)

Strategy cascade (highest to lowest confidence):
1. GUID lookup - direct lemma.guid match
2. Source lemma match - if generating for a specific lemma and text matches
3. Exact text + POS match - case-sensitive lemma_text query
4. Case-insensitive text + POS match - ilike fallback
5. Cross-language derivative form matching - match declined forms across languages
6. LLM disambiguation - ask an LLM to pick among candidates
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import func, literal, or_
from sqlalchemy.orm import Session

from wordfreq.storage.models.schema import (
    DerivativeForm,
    Lemma,
    SentencePatternWord,
    SentenceTranslation,
    SentenceWord,
)

logger = logging.getLogger(__name__)

# Languages where substring matching is appropriate (logographic scripts)
SUBSTRING_MATCH_LANGUAGES = {"zh", "ja", "ko"}

# Map word roles to POS types
ROLE_TO_POS: Dict[str, str] = {
    "subject": "noun",
    "noun": "noun",
    "object": "noun",
    "verb": "verb",
    "adjective": "adjective",
    "adverb": "adverb",
    "other": "",  # no POS filter
}


@dataclass
class ResolvedLemma:
    """Result of attempting to resolve a word to a lemma."""

    position: int
    english_text: str
    lemma: Optional[Lemma]
    method: str  # "guid", "source_lemma", "exact_text", "ilike_text",
    #              "derivative_form", "llm", "unresolved"
    confidence: float  # 0.0 to 1.0
    candidates: List[Lemma] = field(default_factory=list)
    slot_name: Optional[str] = None


def find_lemma_by_text(
    session: Session,
    word_text: str,
    word_role: str,
    *,
    source_lemma: Optional[Lemma] = None,
) -> Optional[Lemma]:
    """Find a lemma matching English text and role.

    This consolidates the duplicated _find_lemma_for_word() from
    guided_sentences.py and llm_sentences.py.

    Args:
        session: Database session
        word_text: English lemma text to match (e.g., "teacher", "see")
        word_role: Word role (e.g., "noun", "verb", "subject", "object")
        source_lemma: Prefer this lemma if text matches (used when generating
            sentences for a specific lemma)

    Returns:
        Matching Lemma or None
    """
    if not word_text:
        return None

    # Check source lemma first
    if source_lemma:
        source_text = source_lemma.lemma_text
        # Strip disambiguation parenthetical, e.g., "mouse (animal)" -> "mouse"
        if "(" in source_text:
            source_base = source_text.split("(")[0].strip()
        else:
            source_base = source_text

        if word_text.lower() == source_base.lower():
            logger.debug(
                "Matched '%s' to source lemma: %s (%s)",
                word_text,
                source_lemma.guid,
                source_lemma.lemma_text,
            )
            return source_lemma

    pos_hint = ROLE_TO_POS.get(word_role)

    # Try exact match
    query = session.query(Lemma).filter(Lemma.lemma_text == word_text)
    if pos_hint:
        query = query.filter(Lemma.pos_type == pos_hint)
    lemma: Optional[Lemma] = query.first()
    if lemma:
        logger.debug("Found lemma for '%s': %s", word_text, lemma.guid)
        return lemma

    # Try case-insensitive match
    query = session.query(Lemma).filter(Lemma.lemma_text.ilike(word_text))
    if pos_hint:
        query = query.filter(Lemma.pos_type == pos_hint)
    lemma = query.first()
    if lemma:
        logger.debug("Found lemma (case-insensitive) for '%s': %s", word_text, lemma.guid)
        return lemma

    logger.debug("No lemma found for '%s' (role: %s)", word_text, word_role)
    return None


def resolve_lemma_for_word(
    session: Session,
    *,
    guid: Optional[str] = None,
    english_text: Optional[str] = None,
    pos_type: Optional[str] = None,
    word_role: Optional[str] = None,
    forms_by_language: Optional[Dict[str, str]] = None,
    sentence_context: Optional[str] = None,
    disambiguation_hint: Optional[str] = None,
    use_llm_disambiguation: bool = False,
    source_lemma: Optional[Lemma] = None,
    min_derivative_languages: int = 2,
) -> ResolvedLemma:
    """Resolve a single word to a lemma using a cascade of strategies.

    Tries strategies in order of decreasing confidence:
    1. GUID lookup
    2. Source lemma text match
    3. Exact English text + POS
    4. Case-insensitive text + POS
    5. Cross-language derivative form matching
    6. LLM disambiguation (if enabled and candidates exist)

    Args:
        session: Database session
        guid: Lemma GUID if known (e.g., from pattern_words or LLM response)
        english_text: English lemma text (e.g., "teacher")
        pos_type: Part of speech (e.g., "noun", "verb")
        word_role: Semantic role (e.g., "subject", "verb") - used to infer POS
        forms_by_language: Declined/conjugated forms by language code,
            e.g., {"lt": "mokytoją", "fr": "professeur", "zh": "老师"}
        sentence_context: Full English sentence for LLM disambiguation context
        disambiguation_hint: Additional hint about intended meaning
        use_llm_disambiguation: Whether to use LLM for ambiguous cases
        source_lemma: Prefer this lemma when text matches
        min_derivative_languages: Minimum languages needed for derivative form match

    Returns:
        ResolvedLemma with the best match (or lemma=None if unresolved)
    """
    effective_english = english_text or ""
    effective_pos = pos_type or ROLE_TO_POS.get(word_role or "", "")
    exact_candidates: List[Lemma] = []

    # Strategy 1: GUID lookup
    if guid:
        lemma = session.query(Lemma).filter(Lemma.guid == guid).first()
        if lemma:
            return ResolvedLemma(
                position=0,
                english_text=effective_english,
                lemma=lemma,
                method="guid",
                confidence=1.0,
                candidates=[lemma],
            )
        logger.warning("GUID %s not found in database", guid)

    # Strategy 2: Source lemma match
    if source_lemma and effective_english:
        source_text = source_lemma.lemma_text
        source_base = source_text.split("(")[0].strip() if "(" in source_text else source_text
        if effective_english.lower() == source_base.lower():
            return ResolvedLemma(
                position=0,
                english_text=effective_english,
                lemma=source_lemma,
                method="source_lemma",
                confidence=0.95,
                candidates=[source_lemma],
            )

    # Strategy 3: Exact text match with POS filter
    if effective_english:
        exact_query = session.query(Lemma).filter(Lemma.lemma_text == effective_english)
        if effective_pos:
            exact_query = exact_query.filter(Lemma.pos_type == effective_pos)
        text_matches: List[Lemma] = exact_query.all()

        if len(text_matches) == 1:
            return ResolvedLemma(
                position=0,
                english_text=effective_english,
                lemma=text_matches[0],
                method="exact_text",
                confidence=0.9,
                candidates=text_matches,
            )

        if len(text_matches) > 1:
            # Multiple exact matches - try narrowing before falling through
            # Prefer lemmas without disambiguation marker
            no_disambig = [c for c in text_matches if not c.disambiguation]
            if len(no_disambig) == 1:
                return ResolvedLemma(
                    position=0,
                    english_text=effective_english,
                    lemma=no_disambig[0],
                    method="exact_text",
                    confidence=0.8,
                    candidates=text_matches,
                )
            # Keep candidates for later LLM disambiguation
            exact_candidates = text_matches

    # Strategy 4: Case-insensitive text match with POS filter
    if effective_english and not exact_candidates:
        ilike_query = session.query(Lemma).filter(Lemma.lemma_text.ilike(effective_english))
        if effective_pos:
            ilike_query = ilike_query.filter(Lemma.pos_type == effective_pos)
        ilike_matches: List[Lemma] = ilike_query.all()

        if len(ilike_matches) == 1:
            return ResolvedLemma(
                position=0,
                english_text=effective_english,
                lemma=ilike_matches[0],
                method="ilike_text",
                confidence=0.85,
                candidates=ilike_matches,
            )

        if len(ilike_matches) > 1:
            no_disambig_ilike = [c for c in ilike_matches if not c.disambiguation]
            if len(no_disambig_ilike) == 1:
                return ResolvedLemma(
                    position=0,
                    english_text=effective_english,
                    lemma=no_disambig_ilike[0],
                    method="ilike_text",
                    confidence=0.75,
                    candidates=ilike_matches,
                )
            exact_candidates = ilike_matches

    # Strategy 5: Cross-language derivative form matching
    if forms_by_language:
        derivative_matches = _match_derivative_forms(
            session, forms_by_language, min_derivative_languages
        )
        if len(derivative_matches) == 1:
            matched_lemma = derivative_matches[0]
            return ResolvedLemma(
                position=0,
                english_text=effective_english,
                lemma=matched_lemma,
                method="derivative_form",
                confidence=0.85,
                candidates=derivative_matches,
            )
        if derivative_matches:
            # Multiple matches from derivative forms - merge with text candidates
            if exact_candidates:
                # Intersect: lemmas that match both text AND derivative forms
                exact_ids = {c.id for c in exact_candidates}
                overlap = [m for m in derivative_matches if m.id in exact_ids]
                if len(overlap) == 1:
                    return ResolvedLemma(
                        position=0,
                        english_text=effective_english,
                        lemma=overlap[0],
                        method="derivative_form",
                        confidence=0.9,
                        candidates=derivative_matches,
                    )
            exact_candidates = derivative_matches if not exact_candidates else exact_candidates

    # Strategy 6: LLM disambiguation
    if use_llm_disambiguation and exact_candidates and len(exact_candidates) > 1:
        llm_result = _llm_disambiguate(
            candidates=exact_candidates,
            english_text=effective_english,
            sentence_context=sentence_context,
            disambiguation_hint=disambiguation_hint,
        )
        if llm_result:
            return ResolvedLemma(
                position=0,
                english_text=effective_english,
                lemma=llm_result,
                method="llm",
                confidence=0.7,
                candidates=exact_candidates,
            )

    # Fallback: return first candidate if any, or None
    if exact_candidates:
        logger.warning(
            "Ambiguous match for '%s': %d candidates, defaulting to first",
            effective_english,
            len(exact_candidates),
        )
        return ResolvedLemma(
            position=0,
            english_text=effective_english,
            lemma=exact_candidates[0],
            method="exact_text",
            confidence=0.5,
            candidates=exact_candidates,
        )

    return ResolvedLemma(
        position=0,
        english_text=effective_english,
        lemma=None,
        method="unresolved",
        confidence=0.0,
    )


def resolve_lemmas_for_sentence(
    session: Session,
    sentence_id: int,
    *,
    use_llm_disambiguation: bool = False,
    min_derivative_languages: int = 2,
    source_lemma: Optional[Lemma] = None,
) -> List[ResolvedLemma]:
    """Resolve all word-lemma links for a sentence.

    Combines data from SentencePatternWord (GUIDs, english_text),
    SentenceWord (declined forms across languages), and SentenceTranslation
    (sentence context) to resolve each word slot to its best lemma match.

    Args:
        session: Database session
        sentence_id: ID of the sentence to resolve
        use_llm_disambiguation: Whether to use LLM for ambiguous words
        min_derivative_languages: Minimum languages for derivative form matching
        source_lemma: Prefer this lemma when text matches (e.g., the lemma
            the sentence was generated for)

    Returns:
        List of ResolvedLemma, one per word slot (based on pattern_words
        or, if no pattern_words exist, from sentence_words grouped by english_text)
    """
    # Load pattern words (the "template" - has GUIDs and english_text)
    pattern_words = (
        session.query(SentencePatternWord)
        .filter_by(sentence_id=sentence_id)
        .order_by(SentencePatternWord.position)
        .all()
    )

    # Load sentence words (the actual word breakdown per language)
    sentence_words = (
        session.query(SentenceWord)
        .filter(SentenceWord.sentence_id == sentence_id)
        .order_by(SentenceWord.position)
        .all()
    )

    # Get English sentence for LLM context
    english_trans = (
        session.query(SentenceTranslation)
        .filter_by(sentence_id=sentence_id, language_code="en")
        .first()
    )
    sentence_context = english_trans.translation_text if english_trans else None

    # Build forms_by_language for each english_text slot from sentence_words
    # Group: english_text -> {lang_code: declined_form}
    slot_forms: Dict[str, Dict[str, str]] = {}
    slot_roles: Dict[str, str] = {}
    for sw in sentence_words:
        if sw.english_text:
            slot_key = sw.english_text.lower()
            if slot_key not in slot_forms:
                slot_forms[slot_key] = {}
                slot_roles[slot_key] = sw.word_role or ""
            if sw.declined_form:
                slot_forms[slot_key][sw.language_code] = sw.declined_form

    results: List[ResolvedLemma] = []

    if pattern_words:
        # Use pattern_words as the canonical list of word slots
        for pw in pattern_words:
            # Check if already linked via pattern_word.lemma_id
            existing_lemma: Optional[Lemma] = None
            existing_guid: Optional[str] = None
            if pw.lemma_id:
                existing_lemma = session.get(Lemma, pw.lemma_id)
                if existing_lemma:
                    existing_guid = existing_lemma.guid

            slot_key = pw.english_text.lower() if pw.english_text else ""
            forms = slot_forms.get(slot_key, {})
            word_role = slot_roles.get(slot_key, pw.slot_name or "")

            resolved = resolve_lemma_for_word(
                session,
                guid=existing_guid,
                english_text=pw.english_text,
                word_role=word_role,
                forms_by_language=forms if forms else None,
                sentence_context=sentence_context,
                use_llm_disambiguation=use_llm_disambiguation,
                source_lemma=source_lemma,
                min_derivative_languages=min_derivative_languages,
            )
            resolved.position = pw.position
            resolved.slot_name = pw.slot_name
            results.append(resolved)
    else:
        # No pattern words - work from sentence_words grouped by english_text
        seen_slots: set[str] = set()
        position = 0
        for sw in sentence_words:
            if not sw.english_text:
                continue
            slot_key = sw.english_text.lower()
            if slot_key in seen_slots:
                continue
            seen_slots.add(slot_key)

            forms = slot_forms.get(slot_key, {})
            sw_guid: Optional[str] = None
            if sw.lemma_id:
                sw_lemma = session.get(Lemma, sw.lemma_id)
                if sw_lemma:
                    sw_guid = sw_lemma.guid

            resolved = resolve_lemma_for_word(
                session,
                guid=sw_guid,
                english_text=sw.english_text,
                word_role=sw.word_role or "",
                forms_by_language=forms if forms else None,
                sentence_context=sentence_context,
                use_llm_disambiguation=use_llm_disambiguation,
                source_lemma=source_lemma,
                min_derivative_languages=min_derivative_languages,
            )
            resolved.position = position
            resolved.slot_name = sw.word_role
            results.append(resolved)
            position += 1

    return results


def _match_derivative_forms(
    session: Session,
    forms_by_language: Dict[str, str],
    min_languages: int,
) -> List[Lemma]:
    """Find lemmas whose derivative forms match across multiple languages.

    Args:
        session: Database session
        forms_by_language: {language_code: declined_form} for a single word slot
        min_languages: Minimum number of languages that must match

    Returns:
        List of matching Lemma objects
    """
    # lemma_id -> set of matching language codes
    lemma_lang_matches: Dict[int, set[str]] = {}

    for lang_code, declined_form in forms_by_language.items():
        if not declined_form:
            continue

        if lang_code in SUBSTRING_MATCH_LANGUAGES:
            matching_forms = (
                session.query(DerivativeForm)
                .filter(
                    DerivativeForm.language_code == lang_code,
                    or_(
                        DerivativeForm.derivative_form_text == declined_form,
                        DerivativeForm.derivative_form_text.contains(declined_form),
                        literal(declined_form).contains(DerivativeForm.derivative_form_text),
                    ),
                )
                .all()
            )
        else:
            matching_forms = (
                session.query(DerivativeForm)
                .filter(
                    DerivativeForm.language_code == lang_code,
                    func.lower(DerivativeForm.derivative_form_text) == declined_form.lower(),
                )
                .all()
            )

        for df in matching_forms:
            if df.lemma_id not in lemma_lang_matches:
                lemma_lang_matches[df.lemma_id] = set()
            lemma_lang_matches[df.lemma_id].add(lang_code)

    # Filter to lemmas matching in enough languages
    qualifying_ids = [
        lemma_id for lemma_id, langs in lemma_lang_matches.items() if len(langs) >= min_languages
    ]

    if not qualifying_ids:
        return []

    lemmas: List[Lemma] = session.query(Lemma).filter(Lemma.id.in_(qualifying_ids)).all()
    return lemmas


def _llm_disambiguate(
    candidates: List[Lemma],
    english_text: str,
    sentence_context: Optional[str] = None,
    disambiguation_hint: Optional[str] = None,
) -> Optional[Lemma]:
    """Use an LLM to pick the best lemma from candidates.

    Delegates to agents.bebras.disambiguation.disambiguate_lemma() to avoid
    duplicating LLM prompt logic.

    Args:
        candidates: Candidate lemmas to choose from
        english_text: The English word being disambiguated
        sentence_context: Full sentence for context
        disambiguation_hint: Additional disambiguation hint

    Returns:
        Best matching Lemma, or None if disambiguation fails
    """
    try:
        from agents.bebras.disambiguation import disambiguate_lemma

        hint_parts = []
        if sentence_context:
            hint_parts.append(f'Used in sentence: "{sentence_context}"')
        if disambiguation_hint:
            hint_parts.append(disambiguation_hint)
        combined_hint = "; ".join(hint_parts) if hint_parts else english_text

        return disambiguate_lemma(
            candidates=candidates,
            lemma_text=english_text,
            disambiguation_hint=combined_hint,
        )
    except Exception as e:
        logger.error("LLM disambiguation failed for '%s': %s", english_text, e)
        return None
