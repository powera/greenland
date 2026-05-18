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
2. **Phase 2 (DB)** — produce a flat ranked list of candidate lemmas for the
   sentence by matching tokens in every available translation, scored by the
   number of languages that confirm each lemma. Pure database work, no LLM.
3. **Phase 3 (LLM, combined)** — one call decomposes every requested target
   translation into per-word entries, with the candidate lemmas surfaced as
   disambiguation hints. (A per-language helper, :func:`decompose_language`,
   remains defined but unused for callers that may want to fan out later.)
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from clients.unified_client import UnifiedLLMClient
from langtools.dialect_overrides import get_dialect_display_name, get_llm_prompt_note
from langtools.directions import get_language_direction_note
from sentences.candidate_lookup import (
    DEFAULT_SOURCE_LANGUAGES,
    CandidateLemma,
    find_candidate_lemmas_from_translations,
)
from sentences.decomposition import (
    build_multi_language_decomposition_context,
    build_multi_language_decomposition_prompt,
    build_multi_language_decomposition_schema,
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
    missing_surface_forms: List[str] = field(default_factory=list)


# Languages that don't separate words with whitespace; per-word coverage cannot
# be reliably verified by tokenizing the translation string.
_NO_WHITESPACE_TOKENIZATION_LANGUAGES = frozenset({"zh", "ja", "th", "lo", "km", "my"})


def _tokenize_translation(text: str) -> List[str]:
    """Whitespace+punctuation tokenization used for coverage checks.

    Returns a list of normalized lowercase tokens. Punctuation-only tokens and
    empty strings are dropped. Used purely for diagnostic comparison against
    the LLM's per-word breakdown — it does not have to match the LLM's exact
    tokenization (e.g., the LLM may merge "in the evening" into one entry), so
    callers compare *multiset coverage* and treat absent surface forms as a
    signal, not a hard failure.
    """
    if not text:
        return []
    normalized = unicodedata.normalize("NFC", text)
    raw_tokens = re.split(r"\s+", normalized.strip())
    tokens: List[str] = []
    for token in raw_tokens:
        stripped = token.strip(
            "".join(ch for ch in token if unicodedata.category(ch).startswith("P"))
        )
        if stripped:
            tokens.append(stripped.lower())
    return tokens


def _normalize_surface_form(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize("NFC", text).strip().lower()


def _find_missing_surface_forms(
    *,
    target_language: str,
    target_translation: str,
    words: List[Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    """Return (translation_tokens, missing_tokens).

    A translation token is "covered" when it equals one of the whitespace-
    split sub-tokens of some returned ``surface_form`` (after NFC + lowercase
    normalization and stripping leading/trailing punctuation). This lets
    multi-word surface forms like "in the evening" cover the input tokens
    "in", "the", "evening" without one-letter surface forms (e.g., Spanish
    "a", French "à") spuriously matching every token that contains that
    letter.

    Returns empty lists for languages in
    :data:`_NO_WHITESPACE_TOKENIZATION_LANGUAGES` since whitespace tokenization
    isn't meaningful there.
    """
    if target_language.lower() in _NO_WHITESPACE_TOKENIZATION_LANGUAGES:
        return [], []

    translation_tokens = _tokenize_translation(target_translation)
    if not translation_tokens:
        return [], []

    surface_forms = [_normalize_surface_form(str(w.get("surface_form", ""))) for w in words]
    surface_forms = [s for s in surface_forms if s]

    surface_token_set: set[str] = set()
    for surface in surface_forms:
        for piece in re.split(r"\s+", surface):
            piece = piece.strip(
                "".join(ch for ch in piece if unicodedata.category(ch).startswith("P"))
            )
            if piece:
                surface_token_set.add(piece)

    missing: List[str] = []
    for token in translation_tokens:
        if token in surface_token_set:
            continue
        missing.append(token)
    return translation_tokens, missing


@dataclass
class TranslateAndDecomposeResult:
    """Aggregate output of the 3-phase pipeline for a single sentence."""

    source_sentence: str
    source_language: str
    translations: Dict[str, str] = field(default_factory=dict)
    candidate_lemmas: List[CandidateLemma] = field(default_factory=list)
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


def build_phase1_prompt(
    *,
    sentence_text: str,
    source_language: str,
    target_languages: Sequence[str],
) -> Optional[Tuple[str, str, str, Dict[str, Any], List[str]]]:
    """Build the Phase-1 sentence-translation prompt.

    Returns ``(context, prompt, full_prompt, schema, normalized_targets)`` so both
    the synchronous path and the batch submit handler can reuse it without
    duplicating the prompt-assembly logic. Returns ``None`` when there are no
    usable targets after normalization.

    ``full_prompt`` is the concatenation ``f"{context}\\n\\n{prompt}"`` used by
    OpenAI Batch (which takes a single ``messages[0].content`` string).
    """
    normalized_targets = normalize_llm_language_codes(
        list(target_languages), operation_name="Phase 1 translation"
    )
    if not normalized_targets:
        return None

    target_language_lines: List[str] = []
    for lang in normalized_targets:
        display_name = get_dialect_display_name(lang)
        notes: List[str] = []
        direction_note = get_language_direction_note(lang)
        if direction_note:
            notes.append(direction_note.lstrip("- ").strip())
        dialect_note = get_llm_prompt_note(lang)
        if dialect_note:
            notes.append(dialect_note)
        line = f"- {display_name} ({lang})"
        if notes:
            line += ": " + "; ".join(notes)
        target_language_lines.append(line)

    prompt = get_prompt("sentence_decomposition", "translate_only").format(
        sentence=sentence_text,
        source_language=get_dialect_display_name(source_language),
        target_languages_with_notes="\n".join(target_language_lines),
    )
    context = get_context("sentence_decomposition", "translate_only")
    schema = _phase1_schema(normalized_targets)
    full_prompt = f"{context}\n\n{prompt}"
    return context, prompt, full_prompt, schema, normalized_targets


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
    built = build_phase1_prompt(
        sentence_text=sentence_text,
        source_language=source_language,
        target_languages=target_languages,
    )
    if built is None:
        return {}
    context, prompt, _full_prompt, schema, normalized_targets = built

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
    translations: Dict[str, str],
    source_languages: Sequence[str],
) -> List[CandidateLemma]:
    """Phase 2: produce a flat ranked candidate-lemma list for the sentence.

    Candidates are sourced from tokens in every available translation in
    ``source_languages`` and ranked by the number of those languages that
    confirm the lemma. Pure DB; no LLM. Empty list when no usable translation
    is provided.
    """
    if not translations:
        return []
    return find_candidate_lemmas_from_translations(
        session,
        translations=translations,
        source_languages=list(source_languages),
    )


# --------------------------------------------------------------------------- #
# Phase 3: per-language decomposition                                          #
# --------------------------------------------------------------------------- #


def _candidates_for_prompt(
    candidates: List[CandidateLemma],
) -> List[Dict[str, Any]]:
    """Adapt CandidateLemma dataclasses to the dict shape expected by the prompt builder."""
    return [
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


def decompose_language(
    *,
    source_sentence: str,
    source_language: str,
    target_language: str,
    target_translation: str,
    helper_translations: List[Dict[str, str]],
    candidate_lemmas: List[CandidateLemma],
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
        candidate_lemmas=_candidates_for_prompt(candidate_lemmas),
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
    reported_word_count: Optional[int] = None
    if isinstance(languages, list) and languages:
        first = languages[0]
        if isinstance(first, dict):
            raw_words = first.get("words")
            if isinstance(raw_words, list):
                words = [w for w in raw_words if isinstance(w, dict)]
            raw_count = first.get("word_count")
            if isinstance(raw_count, int):
                reported_word_count = raw_count

    translation_tokens, missing_tokens = _find_missing_surface_forms(
        target_language=target_language,
        target_translation=target_translation,
        words=words,
    )

    if missing_tokens:
        usage = result.get("_usage") if isinstance(result, dict) else None
        tokens_out: Any = usage.get("tokens_out") if isinstance(usage, dict) else None
        tokens_in: Any = usage.get("tokens_in") if isinstance(usage, dict) else None
        # tokens_out near the model's output cap is a strong hint that the
        # response was truncated mid-array, which manifests as the trailing
        # surface tokens being absent from the breakdown.
        logger.warning(
            "Sentence decomposition missing surface forms for language=%s "
            "(translation=%r): missing=%s | translation_tokens=%d, "
            "returned_words=%d, llm_reported_word_count=%s, model=%s, "
            "tokens_in=%s, tokens_out=%s",
            target_language,
            target_translation,
            missing_tokens,
            len(translation_tokens),
            len(words),
            reported_word_count,
            model,
            tokens_in,
            tokens_out,
        )
        if words:
            last_surface = words[-1].get("surface_form")
            last_position = words[-1].get("position")
            logger.warning(
                "  Last returned word for %s: position=%s, surface_form=%r "
                "(if this is mid-sentence the LLM likely truncated)",
                target_language,
                last_position,
                last_surface,
            )

    return DecomposedLanguage(
        language_code=target_language,
        translation=target_translation,
        words=words,
        success=True,
        missing_surface_forms=missing_tokens,
    )


def decompose_languages_combined(
    *,
    source_sentence: str,
    source_language: str,
    target_translations: Dict[str, str],
    helper_translations: List[Dict[str, str]],
    candidate_lemmas: List[CandidateLemma],
    client: UnifiedLLMClient,
    model: str = DEFAULT_MODEL,
) -> Dict[str, DecomposedLanguage]:
    """Phase 3 (combined): decompose every provided translation in a single LLM call.

    ``target_translations`` maps language_code -> already-known translation; the
    LLM is instructed not to retranslate. Returns one ``DecomposedLanguage`` per
    requested language. On LLM failure every language is returned with
    ``success=False`` and the same error string.
    """
    if not target_translations:
        return {}

    target_languages = list(target_translations.keys())

    prompt = build_multi_language_decomposition_prompt(
        source_sentence=source_sentence,
        source_language=source_language,
        target_translations=target_translations,
        helper_translations=helper_translations,
        candidate_lemmas=_candidates_for_prompt(candidate_lemmas),
    )
    context = build_multi_language_decomposition_context()
    schema = build_multi_language_decomposition_schema(target_languages=target_languages)

    result = query_sentence_decomposition(
        prompt=prompt,
        client=client,
        model=model,
        json_schema=schema,
        context=context,
    )
    if not result.get("success"):
        error = str(result.get("error", "unknown error"))
        return {
            lang: DecomposedLanguage(
                language_code=lang,
                translation=text,
                success=False,
                error=error,
            )
            for lang, text in target_translations.items()
        }

    decompositions: Dict[str, DecomposedLanguage] = {}
    for lang, target_translation in target_translations.items():
        raw_words = result.get(f"words_{lang}")
        words: List[Dict[str, Any]] = []
        if isinstance(raw_words, list):
            words = [w for w in raw_words if isinstance(w, dict)]

        translation_tokens, missing_tokens = _find_missing_surface_forms(
            target_language=lang,
            target_translation=target_translation,
            words=words,
        )

        if missing_tokens:
            usage = result.get("_usage") if isinstance(result, dict) else None
            tokens_out: Any = usage.get("tokens_out") if isinstance(usage, dict) else None
            tokens_in: Any = usage.get("tokens_in") if isinstance(usage, dict) else None
            logger.warning(
                "Sentence decomposition missing surface forms for language=%s "
                "(translation=%r): missing=%s | translation_tokens=%d, "
                "returned_words=%d, model=%s, tokens_in=%s, tokens_out=%s",
                lang,
                target_translation,
                missing_tokens,
                len(translation_tokens),
                len(words),
                model,
                tokens_in,
                tokens_out,
            )
            if words:
                last_surface = words[-1].get("surface_form")
                last_position = words[-1].get("position")
                logger.warning(
                    "  Last returned word for %s: position=%s, surface_form=%r "
                    "(if this is mid-sentence the LLM likely truncated)",
                    lang,
                    last_position,
                    last_surface,
                )

        decompositions[lang] = DecomposedLanguage(
            language_code=lang,
            translation=target_translation,
            words=words,
            success=True,
            missing_surface_forms=missing_tokens,
        )
    return decompositions


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
        pivot_languages: Extra languages added to the Phase 2 candidate-lookup
            pool alongside the targets. Defaults to ``DEFAULT_SOURCE_LANGUAGES``.
            Languages already in ``target_languages`` or equal to
            ``source_language`` are dropped. Phase 1 also translates into these
            so Phase 2 has data to work with.
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
    pivot_input = pivot_languages if pivot_languages is not None else DEFAULT_SOURCE_LANGUAGES
    for lang in pivot_input:
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
    # Source language pool: every translation we have plus the source itself.
    lookup_translations: Dict[str, str] = dict(translations)
    if normalized_source not in lookup_translations:
        lookup_translations[normalized_source] = sentence_text
    source_language_pool: List[str] = list(lookup_translations.keys())
    result.candidate_lemmas = lookup_candidate_lemmas(
        session=session,
        translations=lookup_translations,
        source_languages=source_language_pool,
    )
    english_for_lookup = sentence_text if normalized_source == "en" else translations.get("en", "")

    # ── Phase 3 ────────────────────────────────────────────────────────────
    if decompose_languages is None:
        languages_to_decompose: List[str] = ["en"]
    else:
        languages_to_decompose = [lang.strip().lower() for lang in decompose_languages if lang]

    all_known: Dict[str, str] = dict(translations)
    if normalized_source not in all_known:
        all_known[normalized_source] = sentence_text

    # Anchor sentence is the English text when available, else the source.
    anchor_text = english_for_lookup or sentence_text
    anchor_language = "en" if english_for_lookup else normalized_source

    target_translations: Dict[str, str] = {}
    for target_language in languages_to_decompose:
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
        target_translations[target_language] = target_translation

    if target_translations:
        helper_translations = [
            {"language_code": lang, "translation": text}
            for lang, text in all_known.items()
            if lang not in target_translations and lang != anchor_language
        ]

        combined = decompose_languages_combined(
            source_sentence=anchor_text,
            source_language=anchor_language,
            target_translations=target_translations,
            helper_translations=helper_translations,
            candidate_lemmas=result.candidate_lemmas,
            client=client,
            model=model,
        )
        result.decompositions.update(combined)

    return result
