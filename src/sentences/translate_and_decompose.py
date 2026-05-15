#!/usr/bin/python3

"""Three-phase sentence translate-and-decompose pipeline.

This module is the canonical "GENYS" algorithm for taking a single sentence
in some source language and producing translations + per-language word-level
decompositions. It is shared between:

- The GENYS document-ingestion agent (which then stages missing words for review).
- The barsukas HTTP path that translates an already-stored Sentence on acceptance.

Phases
------
1. **Phase 1 (LLM)** — sentence-level translation of the source sentence into
   every requested target + pivot language. No word breakdown.
2. **Phase 2 (DB)** — for each English surface word, look up candidate lemmas
   ranked by pivot-language agreement. Pure database work, no LLM.
3. **Phase 3 (LLM, per target language)** — word-by-word decomposition of one
   translation, with the candidate lemmas surfaced as disambiguation hints.

Why per-language Phase 3?
-------------------------
Asking the LLM to decompose every language in one call (the previous shape of
``sentences.translation.translate_sentence``) muddies the grammar slots: the
model averages across languages and produces lower-quality per-word entries
for morphologically rich languages. One call per language is more LLM-expensive
but yields cleaner SentenceWord rows.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from clients.unified_client import UnifiedLLMClient
from langtools.dialect_overrides import get_dialect_display_name, get_llm_prompt_note
from sentences.candidate_lookup import (
    DEFAULT_PIVOT_LANGUAGES,
    CandidateLemma,
    find_candidate_lemmas_from_translations,
)
from sentences.decomposition import (
    build_sentence_decomposition_context,
    build_sentence_decomposition_prompt,
    build_single_language_decomposition_schema,
    query_sentence_decomposition,
)
from storage.translation_helpers import LANGUAGE_NAMES, normalize_llm_language_codes
from util.prompt_loader import get_context, get_prompt

logger = logging.getLogger(__name__)

DEFAULT_MODEL: str = "gpt-5.4-mini"

# Synthetic GUID prefix — LLM-emitted placeholder for "no DB lemma matched".
SYNTHETIC_GUID_PREFIX: str = "SYN"


@dataclass
class DecomposedLanguage:
    """Phase 3 result for one target language."""

    language_code: str
    translation: str
    words: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


@dataclass
class TranslateAndDecomposeResult:
    """Aggregate output of the 3-phase pipeline for a single sentence."""

    source_sentence: str
    source_language: str
    translations: Dict[str, str] = field(default_factory=dict)
    candidate_lemmas: Dict[str, List[CandidateLemma]] = field(default_factory=dict)
    decompositions: Dict[str, DecomposedLanguage] = field(default_factory=dict)
    phase1_error: Optional[str] = None

    @property
    def phase1_ok(self) -> bool:
        return self.phase1_error is None and bool(self.translations)


# --------------------------------------------------------------------------- #
# Phase 1: sentence-level translation                                          #
# --------------------------------------------------------------------------- #


def _phase1_schema(target_languages: Sequence[str]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {
        lang: {
            "type": "string",
            "description": f"{LANGUAGE_NAMES.get(lang, lang)} translation",
        }
        for lang in target_languages
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(target_languages),
        "additionalProperties": False,
    }


def translate_sentence_text(
    *,
    sentence_text: str,
    source_language: str,
    target_languages: Sequence[str],
    client: UnifiedLLMClient,
    model: str = DEFAULT_MODEL,
) -> Dict[str, str]:
    """Phase 1: ask the LLM for sentence-level translations only.

    Returns a dict mapping language_code -> translated sentence string. Languages
    the LLM omits or returns empty are dropped silently. On LLM failure returns
    an empty dict and logs a warning.
    """
    normalized_targets = normalize_llm_language_codes(
        list(target_languages), operation_name="Phase 1 translation"
    )
    if not normalized_targets:
        return {}

    target_language_lines: List[str] = []
    for lang in normalized_targets:
        display_name = get_dialect_display_name(lang)
        note = get_llm_prompt_note(lang)
        line = f"- {display_name} ({lang})"
        if note:
            line += f": {note}"
        target_language_lines.append(line)

    prompt = get_prompt("sentence_decomposition", "translate_only").format(
        sentence=sentence_text,
        source_language=get_dialect_display_name(source_language),
        target_languages_with_notes="\n".join(target_language_lines),
    )
    context = get_context("sentence_decomposition", "translate_only")
    schema = _phase1_schema(normalized_targets)

    result = query_sentence_decomposition(
        prompt=prompt,
        client=client,
        model=model,
        json_schema=schema,
        context=context,
    )
    if not result.get("success"):
        logger.warning("Phase 1 translation failed: %s", result.get("error", "unknown"))
        return {}

    translations: Dict[str, str] = {}
    for lang in normalized_targets:
        value = result.get(lang)
        if isinstance(value, str) and value.strip():
            translations[lang] = value.strip()
    return translations


# --------------------------------------------------------------------------- #
# Phase 2: DB candidate lemma lookup                                           #
# --------------------------------------------------------------------------- #


def lookup_candidate_lemmas(
    *,
    session: Session,
    english_text: str,
    translations: Dict[str, str],
    pivot_languages: Sequence[str],
    target_languages: Sequence[str],
) -> Dict[str, List[CandidateLemma]]:
    """Phase 2: rank candidate lemmas for each English content word.

    Pivot translations disambiguate ambiguous English words. Pure DB; no LLM.
    Returns ``{english_word: [CandidateLemma, ...]}``. Empty dict if no English
    text is available.
    """
    if not english_text.strip():
        return {}
    pivot_subset = {lang: text for lang, text in translations.items() if lang in pivot_languages}
    return find_candidate_lemmas_from_translations(
        session,
        english_text=english_text,
        pivot_translations=pivot_subset,
        pivot_languages=list(pivot_languages),
        target_languages=list(target_languages),
    )


# --------------------------------------------------------------------------- #
# Phase 3: per-language decomposition                                          #
# --------------------------------------------------------------------------- #


def _candidates_for_prompt(
    candidates_by_english_word: Dict[str, List[CandidateLemma]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Adapt CandidateLemma dataclasses to the dict shape expected by the prompt builder."""
    return {
        english_word: [
            {
                "guid": candidate.guid,
                "lemma": candidate.lemma_text,
                "disambiguation": candidate.disambiguation,
                "pos": candidate.pos,
                "definition": candidate.definition,
                "translations": candidate.translations,
            }
            for candidate in candidates
        ]
        for english_word, candidates in candidates_by_english_word.items()
    }


def decompose_language(
    *,
    source_sentence: str,
    source_language: str,
    target_language: str,
    target_translation: str,
    helper_translations: List[Dict[str, str]],
    candidate_lemmas_by_english_word: Dict[str, List[CandidateLemma]],
    client: UnifiedLLMClient,
    model: str = DEFAULT_MODEL,
) -> DecomposedLanguage:
    """Phase 3: decompose one target-language translation into per-word entries.

    ``source_sentence`` and ``source_language`` describe the sentence used as the
    primary anchor in the prompt; for the canonical GENYS flow these are the
    English sentence (translation or original). ``target_translation`` is the
    string being decomposed.
    """
    prompt = build_sentence_decomposition_prompt(
        source_sentence=source_sentence,
        source_language=source_language,
        target_language=target_language,
        target_translation=target_translation,
        helper_translations=helper_translations,
        candidate_lemmas_by_english_word=_candidates_for_prompt(candidate_lemmas_by_english_word),
    )
    context = build_sentence_decomposition_context()
    schema = build_single_language_decomposition_schema()

    result = query_sentence_decomposition(
        prompt=prompt,
        client=client,
        model=model,
        json_schema=schema,
        context=context,
    )
    if not result.get("success"):
        return DecomposedLanguage(
            language_code=target_language,
            translation=target_translation,
            success=False,
            error=str(result.get("error", "unknown error")),
        )

    languages = result.get("languages")
    words: List[Dict[str, Any]] = []
    if isinstance(languages, list) and languages:
        first = languages[0]
        if isinstance(first, dict):
            raw_words = first.get("words")
            if isinstance(raw_words, list):
                words = [w for w in raw_words if isinstance(w, dict)]

    return DecomposedLanguage(
        language_code=target_language,
        translation=target_translation,
        words=words,
        success=True,
    )


# --------------------------------------------------------------------------- #
# Orchestration                                                                #
# --------------------------------------------------------------------------- #


def translate_and_decompose(
    *,
    sentence_text: str,
    source_language: str,
    session: Session,
    client: UnifiedLLMClient,
    target_languages: Sequence[str],
    pivot_languages: Optional[Sequence[str]] = None,
    decompose_languages: Optional[Sequence[str]] = None,
    model: str = DEFAULT_MODEL,
) -> TranslateAndDecomposeResult:
    """Run the full 3-phase pipeline for one sentence.

    Args:
        sentence_text: Sentence in ``source_language``.
        source_language: ISO-ish language code (e.g., "en", "es") of the input.
        session: SQLAlchemy session (used only for Phase 2 DB lookups).
        client: Unified LLM client (already configured/warmed).
        target_languages: Languages to translate into in Phase 1. The source
            language is dropped automatically.
        pivot_languages: Pivot languages for Phase 2 disambiguation. Defaults
            to ``DEFAULT_PIVOT_LANGUAGES``. Languages already in
            ``target_languages`` or equal to ``source_language`` are dropped.
            Phase 1 also translates into these so Phase 2 has data to work with.
        decompose_languages: Languages to run Phase 3 on. Defaults to English
            only — that matches GENYS, which only needs the English breakdown
            to stage pending imports. The HTTP path passes the full target list.
            May include ``source_language``: in that case Phase 3 decomposes
            the existing source sentence (no Phase 1 retranslation), which
            backfills SentenceWord rows for the language the sentence was
            originally added in.
        model: LLM model id.

    Returns:
        A ``TranslateAndDecomposeResult`` capturing every intermediate stage.
        Callers inspect ``phase1_ok`` and per-language ``decompositions`` to
        decide what to persist.
    """
    normalized_source = source_language.strip().lower()

    seen: set[str] = set()
    targets: List[str] = []
    for lang in target_languages:
        normalized = lang.strip().lower()
        if not normalized or normalized == normalized_source or normalized in seen:
            continue
        seen.add(normalized)
        targets.append(normalized)

    pivots_effective: List[str] = []
    for lang in pivot_languages if pivot_languages is not None else DEFAULT_PIVOT_LANGUAGES:
        normalized = lang.strip().lower()
        if not normalized or normalized == normalized_source or normalized in seen:
            continue
        seen.add(normalized)
        pivots_effective.append(normalized)

    phase1_languages = targets + pivots_effective

    result = TranslateAndDecomposeResult(
        source_sentence=sentence_text,
        source_language=normalized_source,
    )

    if not phase1_languages:
        result.phase1_error = "No target or pivot languages requested"
        return result

    # ── Phase 1 ────────────────────────────────────────────────────────────
    translations = translate_sentence_text(
        sentence_text=sentence_text,
        source_language=normalized_source,
        target_languages=phase1_languages,
        client=client,
        model=model,
    )
    if not translations:
        result.phase1_error = "Phase 1 translation produced no results"
        return result
    result.translations = translations

    # ── Phase 2 ────────────────────────────────────────────────────────────
    english_for_lookup = sentence_text if normalized_source == "en" else translations.get("en", "")
    result.candidate_lemmas = lookup_candidate_lemmas(
        session=session,
        english_text=english_for_lookup,
        translations=translations,
        pivot_languages=pivots_effective,
        target_languages=targets,
    )

    # ── Phase 3 ────────────────────────────────────────────────────────────
    if decompose_languages is None:
        languages_to_decompose: List[str] = ["en"]
    else:
        languages_to_decompose = [lang.strip().lower() for lang in decompose_languages if lang]

    # Build helper translations once. The decomposition for language X uses
    # every OTHER known translation as helper context, plus the original source.
    all_known: Dict[str, str] = dict(translations)
    if normalized_source not in all_known:
        all_known[normalized_source] = sentence_text

    for target_language in languages_to_decompose:
        # For "en" Phase 3, the anchor sentence is the English text itself.
        if target_language == "en":
            anchor_text = english_for_lookup
            anchor_language = "en"
        else:
            anchor_text = english_for_lookup or sentence_text
            anchor_language = "en" if english_for_lookup else normalized_source

        target_translation = all_known.get(target_language)
        if not target_translation:
            result.decompositions[target_language] = DecomposedLanguage(
                language_code=target_language,
                translation="",
                success=False,
                error=f"No Phase 1 translation available for '{target_language}'",
            )
            continue
        if not anchor_text:
            result.decompositions[target_language] = DecomposedLanguage(
                language_code=target_language,
                translation=target_translation,
                success=False,
                error="No anchor English text available for decomposition",
            )
            continue

        helper_translations = [
            {"language_code": lang, "translation": text}
            for lang, text in all_known.items()
            if lang != target_language and lang != anchor_language
        ]

        result.decompositions[target_language] = decompose_language(
            source_sentence=anchor_text,
            source_language=anchor_language,
            target_language=target_language,
            target_translation=target_translation,
            helper_translations=helper_translations,
            candidate_lemmas_by_english_word=result.candidate_lemmas,
            client=client,
            model=model,
        )

    return result
