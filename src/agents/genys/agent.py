#!/usr/bin/env python3
"""Genys agent core logic for document parsing and pending import staging."""

import logging
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, literal, or_

from clients.unified_client import UnifiedLLMClient
from langtools.dialect_overrides import get_dialect_display_name, get_llm_prompt_note
from langtools.grammatical_words import is_function_word
from langtools.tokenizer import tokenize
from sentences.analysis import SUBSTRING_MATCH_LANGUAGES
from sentences.decomposition import (
    build_sentence_decomposition_context,
    build_sentence_decomposition_prompt,
    build_single_language_decomposition_schema,
    query_sentence_decomposition,
)
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.crud.sentence import add_sentence
from storage.crud.sentence_translation import add_sentence_translation
from storage.crud.sentence_word import add_sentence_word
from storage.models.imports import PendingImport
from storage.models.schema import DerivativeForm, Lemma
from storage.translation_helpers import (
    LANGUAGE_NAMES,
    get_translation,
    normalize_llm_language_codes,
)
from util.prompt_loader import get_context, get_prompt

logger = logging.getLogger(__name__)

ROLE_POS_MAP: Dict[str, str] = {
    "noun": "noun",
    "verb": "verb",
    "adjective": "adjective",
    "adverb": "adverb",
}
SKIPPED_ROLES: Set[str] = {"article", "preposition", "conjunction", "determiner", "particle"}

# Languages always requested in Phase 1 (sentence-level translation only).
# The doc language is excluded at runtime.
_PHASE1_LANGUAGES: List[str] = ["en", "fr", "zh", "lt"]

# Synthetic GUID prefix — do not resolve these to DB lemmas
_SYNTHETIC_GUID_PREFIX = "SYN"


class GenysAgent:
    """Agent that decomposes documents and stages missing words for review."""

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.debug = config.debug
        self._llm_client: Optional[UnifiedLLMClient] = None

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        """Get database session from backend config."""
        return create_backend_session(self.config)

    def get_llm_client(self) -> UnifiedLLMClient:
        """Get lazily initialized LLM client."""
        if self._llm_client is None:
            self._llm_client = UnifiedLLMClient.from_config(self.config)
            if self.config.model:
                self._llm_client.warm_model(self.config.model)
        return self._llm_client

    @staticmethod
    def split_sentences(text: str, language_code: str) -> List[str]:
        """Split text into sentence strings preserving sentence punctuation."""
        normalized_language_code = language_code.strip().lower()
        compact_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not compact_text:
            return []

        if normalized_language_code in {"zh", "ja", "ko"}:
            split_pattern = r"(?<=[。！？])\s*"
        else:
            split_pattern = r"(?<=[.!?…])\s+"

        parts = [
            segment.strip() for segment in re.split(split_pattern, compact_text) if segment.strip()
        ]
        return parts

    @staticmethod
    def choose_target_languages(document_language: str) -> List[str]:
        """Choose up to 3 target languages for Phase 1 translation.

        Always uses [en, fr, zh, lt] minus the document language.
        """
        normalized_document_language = document_language.strip().lower()
        selected_languages = [
            lang for lang in _PHASE1_LANGUAGES if lang != normalized_document_language
        ]
        return normalize_llm_language_codes(
            selected_languages[:3],
            operation_name="Genys Phase 1 translation",
        )

    # ------------------------------------------------------------------ #
    # Phase 1: sentence-level translation (no word breakdown)             #
    # ------------------------------------------------------------------ #

    def _build_phase1_schema(self, target_languages: Sequence[str]) -> Dict[str, Any]:
        """JSON schema for Phase 1: sentence translations only, no words_ fields."""
        properties: Dict[str, Any] = {}
        for lang in target_languages:
            lang_name = LANGUAGE_NAMES.get(lang, lang)
            properties[lang] = {"type": "string", "description": f"{lang_name} translation"}
        return {
            "type": "object",
            "properties": properties,
            "required": list(target_languages),
            "additionalProperties": False,
        }

    def _phase1_translate(
        self,
        sentence_text: str,
        document_language: str,
        target_languages: Sequence[str],
    ) -> Dict[str, str]:
        """Phase 1: ask the LLM for sentence-level translations only.

        Returns a dict mapping language_code -> translated sentence string.
        On failure returns an empty dict.
        """
        source_language_name = get_dialect_display_name(document_language)
        target_language_lines: List[str] = []
        for lang in target_languages:
            display_name = get_dialect_display_name(lang)
            note = get_llm_prompt_note(lang)
            line = f"- {display_name} ({lang})"
            if note:
                line += f": {note}"
            target_language_lines.append(line)
        prompt = get_prompt("sentence_decomposition", "translate_only").format(
            sentence=sentence_text,
            source_language=source_language_name,
            target_languages_with_notes="\n".join(target_language_lines),
        )
        context = get_context("sentence_decomposition", "translate_only")
        schema = self._build_phase1_schema(target_languages)

        result = query_sentence_decomposition(
            prompt=prompt,
            client=self.get_llm_client(),
            model=self.config.model or "gpt-5.4-mini",
            json_schema=schema,
            context=context,
        )
        if not result.get("success"):
            logger.warning("Phase 1 translation failed: %s", result.get("error", "unknown"))
            return {}

        translations: Dict[str, str] = {}
        for lang in target_languages:
            value = result.get(lang)
            if isinstance(value, str) and value.strip():
                translations[lang] = value.strip()
        return translations

    # ------------------------------------------------------------------ #
    # Phase 2: DB candidate lemma lookup (no LLM)                        #
    # ------------------------------------------------------------------ #

    def _lemma_ids_for_english_gloss(
        self,
        session: Any,
        english_gloss: str,
        cache: Dict[str, Set[int]],
    ) -> Set[int]:
        normalized_gloss = english_gloss.strip().lower()
        if normalized_gloss in cache:
            return cache[normalized_gloss]

        lemma_rows = (
            session.query(Lemma.id).filter(func.lower(Lemma.lemma_text) == normalized_gloss).all()
        )
        lemma_ids: Set[int] = {row[0] for row in lemma_rows}
        cache[normalized_gloss] = lemma_ids
        return lemma_ids

    def _lemma_ids_for_derivative(
        self,
        session: Any,
        language_code: str,
        surface_form: str,
        cache: Dict[Tuple[str, str], Set[int]],
    ) -> Set[int]:
        normalized_surface = surface_form.strip().lower()
        cache_key = (language_code, normalized_surface)
        if cache_key in cache:
            return cache[cache_key]

        if language_code in SUBSTRING_MATCH_LANGUAGES:
            rows = (
                session.query(DerivativeForm.lemma_id)
                .filter(
                    DerivativeForm.language_code == language_code,
                    or_(
                        DerivativeForm.derivative_form_text == surface_form,
                        DerivativeForm.derivative_form_text.contains(surface_form),
                        literal(surface_form).contains(DerivativeForm.derivative_form_text),
                    ),
                )
                .all()
            )
        else:
            rows = (
                session.query(DerivativeForm.lemma_id)
                .filter(
                    DerivativeForm.language_code == language_code,
                    func.lower(DerivativeForm.derivative_form_text) == normalized_surface,
                )
                .all()
            )

        lemma_ids: Set[int] = {row[0] for row in rows}
        cache[cache_key] = lemma_ids
        return lemma_ids

    def _phase2_candidate_lemmas(
        self,
        session: Any,
        sentence_text: str,
        document_language: str,
        translations: Dict[str, str],
        derivative_cache: Dict[Tuple[str, str], Set[int]],
        gloss_cache: Dict[str, Set[int]],
        all_languages: Sequence[str],
    ) -> List[Dict[str, Any]]:
        """Phase 2: tokenize the sentence and translations, query DB for candidate lemmas.

        Returns a list of candidate dicts in the format expected by
        build_sentence_decomposition_prompt:
          {guid, lemma, disambiguation, pos, definition, translations: {lang: form}}
        """
        # Collect tokens per language
        tokens_by_language: Dict[str, List[str]] = {}
        tokens_by_language[document_language] = tokenize(sentence_text, document_language)
        for lang, translation_text in translations.items():
            tokens_by_language[lang] = tokenize(translation_text, lang)

        # Gather all candidate lemma IDs and which languages matched them
        matched_languages_by_lemma: Dict[int, Set[str]] = defaultdict(set)

        for lang, tokens in tokens_by_language.items():
            for token in tokens:
                token_stripped = token.strip()
                if not token_stripped:
                    continue
                lemma_ids = self._lemma_ids_for_derivative(
                    session, lang, token_stripped, derivative_cache
                )
                # For English tokens also try gloss lookup
                if lang == "en":
                    lemma_ids = lemma_ids | self._lemma_ids_for_english_gloss(
                        session, token_stripped, gloss_cache
                    )
                for lemma_id in lemma_ids:
                    matched_languages_by_lemma[lemma_id].add(lang)

        if not matched_languages_by_lemma:
            return []

        # Load lemma objects and build candidate list
        all_lemma_ids = list(matched_languages_by_lemma.keys())
        lemmas: List[Lemma] = session.query(Lemma).filter(Lemma.id.in_(all_lemma_ids)).all()

        candidates: List[Dict[str, Any]] = []
        for lemma in lemmas:
            if lemma.guid is None:
                continue
            trans_map: Dict[str, str] = {}
            for lang in all_languages:
                try:
                    translation_value = get_translation(session, lemma, lang)
                    if translation_value:
                        trans_map[lang] = translation_value
                except (ValueError, KeyError):
                    pass
            candidates.append(
                {
                    "guid": lemma.guid,
                    "lemma": lemma.lemma_text,
                    "disambiguation": lemma.disambiguation or "",
                    "pos": lemma.pos_type,
                    "definition": lemma.definition_text,
                    "translations": trans_map,
                }
            )

        logger.debug(
            "Phase 2: found %d candidate lemmas from %d tokens across %d languages",
            len(candidates),
            sum(len(t) for t in tokens_by_language.values()),
            len(tokens_by_language),
        )
        return candidates

    # ------------------------------------------------------------------ #
    # Phase 3: per-word decomposition with candidate lemmas (LLM)        #
    # ------------------------------------------------------------------ #

    def _phase3_decompose(
        self,
        sentence_text: str,
        document_language: str,
        translations: Dict[str, str],
        candidate_lemmas: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Phase 3: decompose the English translation into per-word breakdown.

        Uses the other language translations only as helper context for
        candidate lemma selection (already done in Phase 2). The decomposition
        is always for English, since that is the language of the lemma database.
        """
        # If the document is English, use the original sentence directly.
        # Otherwise use the Phase 1 English translation.
        if document_language == "en":
            english_text = sentence_text
        else:
            english_text = translations.get("en", "")
        if not english_text:
            logger.warning("Phase 3: no English translation available, cannot decompose")
            return {"success": False, "error": "No English translation from Phase 1"}

        # All other translations serve as helpers for disambiguation
        helper_translations = [
            {"language_code": lang, "translation": translation_text}
            for lang, translation_text in translations.items()
            if lang != "en"
        ]
        # Include the original document-language sentence as a helper too
        if document_language != "en":
            helper_translations.insert(
                0, {"language_code": document_language, "translation": sentence_text}
            )

        prompt = build_sentence_decomposition_prompt(
            source_sentence=english_text,
            source_language="en",
            target_language="en",
            target_translation=english_text,
            helper_translations=helper_translations,
            candidate_lemmas=candidate_lemmas,
        )
        context = build_sentence_decomposition_context()
        schema = build_single_language_decomposition_schema()

        result = query_sentence_decomposition(
            prompt=prompt,
            client=self.get_llm_client(),
            model=self.config.model or "gpt-5.4-mini",
            json_schema=schema,
            context=context,
        )
        return result

    @staticmethod
    def _extract_words_from_phase3(result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract the flat word list from the single-language decomposition schema result."""
        languages = result.get("languages")
        if not isinstance(languages, list) or not languages:
            return []
        first_lang = languages[0]
        if not isinstance(first_lang, dict):
            return []
        words = first_lang.get("words")
        if not isinstance(words, list):
            return []
        return [w for w in words if isinstance(w, dict)]

    @staticmethod
    def _check_decomposition_completeness(
        english_text: str, words: List[Dict[str, Any]], sentence_label: str
    ) -> None:
        """Warn if any token in *english_text* is absent from the decomposition surface forms."""
        surface_forms: Set[str] = set()
        for w in words:
            sf = str(w.get("surface_form") or "").strip().lower()
            # Also cover multi-word surface forms by adding each sub-token
            for part in re.split(r"\s+", sf):
                part = part.strip(".,!?;:\"'()[]{}—-")
                if part:
                    surface_forms.add(part)

        tokens = tokenize(english_text, "en")
        missing = []
        for token in tokens:
            normalized = token.strip(".,!?;:\"'()[]{}—-").lower()
            if normalized and normalized not in surface_forms:
                missing.append(token)

        if missing:
            logger.warning(
                "Phase 3 completeness check FAILED at %s: %d token(s) missing from decomposition: %s",
                sentence_label,
                len(missing),
                ", ".join(missing),
            )

    # ------------------------------------------------------------------ #
    # Shared helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_word_role(raw_role: Any) -> str:
        return str(raw_role or "").strip().lower()

    @staticmethod
    def _normalize_surface_form(raw_word: Any) -> str:
        return str(raw_word or "").strip()

    @staticmethod
    def _normalize_english_gloss(raw_gloss: Any) -> str:
        return str(raw_gloss or "").strip()

    def _load_pending_glosses(self, session: Any) -> Set[str]:
        pending_rows = session.query(PendingImport.english_word).all()
        return {str(row[0]).strip().lower() for row in pending_rows if row[0]}

    # ------------------------------------------------------------------ #
    # Main processing loop                                                #
    # ------------------------------------------------------------------ #

    def process_document(
        self,
        input_path: str,
        document_language: str,
        store_sentences: bool = False,
        dry_run: bool = False,
        throttle_seconds: float = 1.0,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Process a document and stage missing words to PendingImport.

        Three phases per sentence:
          1. LLM: sentence-level translation into target languages only.
          2. DB: tokenize all translations and query for candidate lemmas.
          3. LLM: per-word decomposition with candidate lemmas as context.
        """
        logger.debug("Phase: initialization - loading input document")
        document_path = Path(input_path)
        source_name = document_path.name
        document_text = document_path.read_text(encoding="utf-8")
        all_sentences = self.split_sentences(document_text, document_language)
        selected_sentences = all_sentences[:limit] if limit is not None else all_sentences

        target_languages = self.choose_target_languages(document_language)
        # All languages available for candidate lemma translation lookup
        all_languages = [document_language] + list(target_languages)

        logger.debug(
            "Phase: initialization complete - document=%s language=%s "
            "total_sentences=%d selected_sentences=%d target_languages=%s",
            source_name,
            document_language,
            len(all_sentences),
            len(selected_sentences),
            ",".join(target_languages),
        )

        stats: Dict[str, Any] = {
            "document": source_name,
            "document_language": document_language,
            "sentences_parsed": len(selected_sentences),
            "estimated_llm_calls": len(selected_sentences) * 2,
            "total_words_extracted": 0,
            "function_words_skipped": 0,
            "already_in_database": 0,
            "staged_for_review": 0,
            "existing_pending": 0,
            "errors": 0,
            "target_languages": target_languages,
            "dry_run": dry_run,
        }

        if not selected_sentences:
            logger.debug("Phase: complete - no sentences selected for processing")
            return stats

        logger.debug("Phase: database session - opening session and loading pending imports")
        session = self.get_session()
        processed_glosses: Set[str] = set()
        gloss_cache: Dict[str, Set[int]] = {}
        derivative_cache: Dict[Tuple[str, str], Set[int]] = {}

        try:
            existing_pending_glosses = self._load_pending_glosses(session)
            logger.debug(
                "Phase: sentence processing - loaded existing pending imports: %d entries",
                len(existing_pending_glosses),
            )

            for sentence_index, sentence_text in enumerate(selected_sentences):
                sentence_label = f"sentence {sentence_index + 1}/{len(selected_sentences)}"

                # ── Phase 1: translate ──────────────────────────────────
                logger.debug("Phase 1 start - %s - sentence=%r", sentence_label, sentence_text)
                translations = self._phase1_translate(
                    sentence_text, document_language, target_languages
                )
                if not translations:
                    logger.warning("Phase 1 failed for %s, skipping", sentence_label)
                    stats["errors"] += 1
                    continue
                logger.debug("Phase 1 complete - %s", sentence_label)

                # ── Phase 2: candidate lemmas ───────────────────────────
                logger.debug("Phase 2 start - %s", sentence_label)
                candidate_lemmas = self._phase2_candidate_lemmas(
                    session,
                    sentence_text,
                    document_language,
                    translations,
                    derivative_cache,
                    gloss_cache,
                    all_languages,
                )
                logger.debug(
                    "Phase 2 complete - %s - %d candidates", sentence_label, len(candidate_lemmas)
                )

                # ── Phase 3: per-word decomposition ────────────────────
                logger.debug("Phase 3 start - %s", sentence_label)
                decomposition_result = self._phase3_decompose(
                    sentence_text,
                    document_language,
                    translations,
                    candidate_lemmas,
                )
                if not decomposition_result.get("success"):
                    logger.warning(
                        "Phase 3 decomposition failed at %s: %s",
                        sentence_label,
                        decomposition_result.get("error", "unknown error"),
                    )
                    stats["errors"] += 1
                    continue
                logger.debug("Phase 3 complete - %s", sentence_label)

                words = self._extract_words_from_phase3(decomposition_result)

                # ── Sanity-check decomposition completeness ─────────────
                english_text_for_check = (
                    sentence_text if document_language == "en" else translations.get("en", "")
                )
                if english_text_for_check:
                    self._check_decomposition_completeness(
                        english_text_for_check, words, sentence_label
                    )

                # ── Store sentence (optional) ───────────────────────────
                sentence_has_db_changes = False
                sentence_new_pending_glosses: Set[str] = set()

                if store_sentences and not dry_run:
                    sentence_row = add_sentence(
                        session,
                        source_filename=source_name,
                        notes=f"Imported by genys from {source_name}",
                    )
                    add_sentence_translation(
                        session,
                        sentence=sentence_row,
                        language_code=document_language,
                        translation_text=sentence_text,
                        verified=False,
                    )
                    for lang, translation_text in translations.items():
                        add_sentence_translation(
                            session,
                            sentence=sentence_row,
                            language_code=lang,
                            translation_text=translation_text,
                            verified=False,
                        )

                    for word_position, word_entry in enumerate(words):
                        word_role = self._normalize_word_role(word_entry.get("role")) or "unknown"
                        surface = self._normalize_surface_form(word_entry.get("surface_form"))
                        english_gloss = self._normalize_english_gloss(
                            word_entry.get("english_gloss")
                        )
                        grammatical_form_raw = word_entry.get("grammatical_form")
                        grammatical_form = (
                            str(grammatical_form_raw).strip()
                            if grammatical_form_raw is not None
                            else None
                        )

                        # Resolve lemma from guid if present and not synthetic
                        word_lemma: Optional[Lemma] = None
                        lemma_guid = str(word_entry.get("lemma_guid") or "").strip()
                        if (
                            lemma_guid
                            and not lemma_guid.startswith(_SYNTHETIC_GUID_PREFIX)
                            and lemma_guid.lower() not in {"", "none", "null"}
                        ):
                            word_lemma = (
                                session.query(Lemma).filter(Lemma.guid == lemma_guid).first()
                            )

                        add_sentence_word(
                            session,
                            sentence=sentence_row,
                            position=word_position,
                            word_role=word_role,
                            language_code="en",
                            lemma=word_lemma,
                            english_text=english_gloss or None,
                            target_language_text=surface or None,
                            grammatical_form=grammatical_form,
                            declined_form=surface or None,
                        )
                    sentence_has_db_changes = True

                # ── Stage pending imports ───────────────────────────────
                for word_entry in words:
                    stats["total_words_extracted"] += 1
                    surface_form = self._normalize_surface_form(word_entry.get("surface_form"))
                    english_gloss = self._normalize_english_gloss(word_entry.get("english_gloss"))
                    role = self._normalize_word_role(word_entry.get("role"))
                    lemma_guid = self._normalize_surface_form(word_entry.get("lemma_guid"))

                    if not surface_form or not english_gloss:
                        continue

                    if role in SKIPPED_ROLES:
                        stats["function_words_skipped"] += 1
                        continue

                    if is_function_word(surface_form, document_language):
                        stats["function_words_skipped"] += 1
                        continue

                    # Words with real (non-synthetic) guids are already in the DB
                    is_synthetic = (
                        lemma_guid.startswith(_SYNTHETIC_GUID_PREFIX)
                        and lemma_guid[len(_SYNTHETIC_GUID_PREFIX) :].isdigit()
                    )
                    has_real_guid = (
                        bool(lemma_guid)
                        and lemma_guid.lower() not in {"", "none", "null"}
                        and not is_synthetic
                    )
                    if has_real_guid:
                        stats["already_in_database"] += 1
                        logger.debug(
                            "Phase 3 - %s - word already in database (guid=%s): %s",
                            sentence_label,
                            lemma_guid,
                            english_gloss,
                        )
                        continue

                    concept_key = f"gloss:{english_gloss.lower()}"
                    if concept_key in processed_glosses:
                        logger.debug(
                            "Phase 3 - %s - skipping concept already processed: %s",
                            sentence_label,
                            concept_key,
                        )
                        continue
                    processed_glosses.add(concept_key)

                    normalized_gloss = english_gloss.strip().lower()
                    if normalized_gloss in existing_pending_glosses:
                        stats["existing_pending"] += 1
                        logger.debug(
                            "Phase 3 - %s - concept already in pending imports: %s",
                            sentence_label,
                            normalized_gloss,
                        )
                        continue

                    mapped_pos_type = ROLE_POS_MAP.get(role)
                    # Use the English sentence text as context for LLM disambiguation
                    english_sentence = (
                        sentence_text if document_language == "en" else translations.get("en", "")
                    )
                    pending_import = PendingImport(
                        english_word=english_gloss,
                        definition=english_gloss,
                        disambiguation_translation=surface_form,
                        disambiguation_language=document_language,
                        pos_type=mapped_pos_type,
                        pos_subtype=None,
                        source=f"genys/{source_name}",
                        frequency_rank=None,
                        notes=f"From document: {source_name}",
                        example_sentence=english_sentence or None,
                    )

                    stats["staged_for_review"] += 1
                    logger.debug(
                        "Phase 3 - %s - staged pending import - gloss=%s pos=%s surface=%r",
                        sentence_label,
                        english_gloss,
                        mapped_pos_type,
                        surface_form,
                    )
                    if not dry_run:
                        session.add(pending_import)
                        sentence_has_db_changes = True
                        sentence_new_pending_glosses.add(normalized_gloss)

                if not dry_run and sentence_has_db_changes:
                    logger.debug("Phase: %s - committing transaction", sentence_label)
                    session.commit()
                    existing_pending_glosses.update(sentence_new_pending_glosses)
                elif dry_run:
                    logger.debug("Phase: %s - dry run, skipping commit", sentence_label)

                if throttle_seconds > 0 and sentence_index < len(selected_sentences) - 1:
                    logger.debug("Phase: %s - throttling %.2fs", sentence_label, throttle_seconds)
                    time.sleep(throttle_seconds)

        except Exception:
            logger.exception("Phase: error - rolling back transaction")
            session.rollback()
            raise
        finally:
            logger.debug("Phase: cleanup - closing database session")
            session.close()

        logger.debug("Phase: complete - processing finished")
        return stats
