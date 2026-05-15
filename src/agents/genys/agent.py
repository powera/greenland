#!/usr/bin/env python3
"""Genys agent: document parser + PendingImport staging.

The translate/decompose pipeline itself lives in
``sentences.translate_and_decompose``. This module is responsible only for:

- Splitting an input document into sentences.
- Choosing which target languages to translate into.
- Calling the shared pipeline once per sentence.
- Storing sentences and SentenceWord rows when requested.
- Staging missing English glosses to ``PendingImport`` for later review,
  deduplicating against existing lemmas, derivative forms, and prior pending
  imports.
"""

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, literal, or_

from clients.unified_client import UnifiedLLMClient
from langtools.grammatical_words import is_function_word
from langtools.tokenizer import tokenize
from sentences.analysis import SUBSTRING_MATCH_LANGUAGES
from sentences.candidate_lookup import DEFAULT_PIVOT_LANGUAGES
from sentences.translate_and_decompose import (
    SYNTHETIC_GUID_PREFIX,
    TranslateAndDecomposeResult,
    translate_and_decompose,
)
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.crud.sentence import add_sentence
from storage.crud.sentence_translation import add_sentence_translation
from storage.crud.sentence_word import add_sentence_word
from storage.models.imports import PendingImport
from storage.models.schema import DerivativeForm, Lemma
from storage.translation_helpers import normalize_llm_language_codes

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

_PUNCTUATION_STRIP = ".,!?;:\"'()[]{}—-"


class GenysAgent:
    """Decompose documents and stage missing words for review."""

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.debug = config.debug
        self._llm_client: Optional[UnifiedLLMClient] = None

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        return create_backend_session(self.config)

    def get_llm_client(self) -> UnifiedLLMClient:
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

        return [
            segment.strip() for segment in re.split(split_pattern, compact_text) if segment.strip()
        ]

    @staticmethod
    def choose_target_languages(document_language: str) -> List[str]:
        """Pick up to 3 target languages: [en, fr, zh, lt] minus the doc language."""
        normalized = document_language.strip().lower()
        selected = [lang for lang in _PHASE1_LANGUAGES if lang != normalized]
        return normalize_llm_language_codes(
            selected[:3],
            operation_name="Genys Phase 1 translation",
        )

    # ------------------------------------------------------------------ #
    # DB dedup helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _lemma_ids_for_english_gloss(
        session: Any, english_gloss: str, cache: Dict[str, Set[int]]
    ) -> Set[int]:
        normalized = english_gloss.strip().lower()
        if normalized in cache:
            return cache[normalized]
        rows = session.query(Lemma.id).filter(func.lower(Lemma.lemma_text) == normalized).all()
        ids = {row[0] for row in rows}
        cache[normalized] = ids
        return ids

    @staticmethod
    def _lemma_ids_for_derivative(
        session: Any,
        language_code: str,
        surface_form: str,
        cache: Dict[Tuple[str, str], Set[int]],
    ) -> Set[int]:
        normalized = surface_form.strip().lower()
        cache_key = (language_code, normalized)
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
                    func.lower(DerivativeForm.derivative_form_text) == normalized,
                )
                .all()
            )
        ids = {row[0] for row in rows}
        cache[cache_key] = ids
        return ids

    @staticmethod
    def _check_decomposition_completeness(
        english_text: str, words: List[Dict[str, Any]], sentence_label: str
    ) -> None:
        """Warn if any token in ``english_text`` is missing from decomposition surface forms."""
        surface_forms: Set[str] = set()
        for word_entry in words:
            raw_surface = str(word_entry.get("surface_form") or "").strip().lower()
            for part in re.split(r"\s+", raw_surface):
                stripped = part.strip(_PUNCTUATION_STRIP)
                if stripped:
                    surface_forms.add(stripped)

        missing: List[str] = []
        for token in tokenize(english_text, "en"):
            normalized = token.strip(_PUNCTUATION_STRIP).lower()
            if normalized and normalized not in surface_forms:
                missing.append(token)

        if missing:
            logger.warning(
                "Decomposition completeness check FAILED at %s: %d token(s) missing: %s",
                sentence_label,
                len(missing),
                ", ".join(missing),
            )

    @staticmethod
    def _is_real_guid(lemma_guid: str) -> bool:
        if not lemma_guid:
            return False
        lowered = lemma_guid.lower()
        if lowered in {"", "none", "null"}:
            return False
        synthetic = (
            lemma_guid.startswith(SYNTHETIC_GUID_PREFIX)
            and lemma_guid[len(SYNTHETIC_GUID_PREFIX) :].isdigit()
        )
        return not synthetic

    @staticmethod
    def _load_pending_glosses(session: Any) -> Set[str]:
        rows = session.query(PendingImport.english_word).all()
        return {str(row[0]).strip().lower() for row in rows if row[0]}

    # ------------------------------------------------------------------ #
    # Per-sentence persistence                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _store_sentence(
        session: Any,
        *,
        source_name: str,
        document_language: str,
        sentence_text: str,
        translations: Dict[str, str],
        english_words: List[Dict[str, Any]],
    ) -> None:
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

        for position, word_entry in enumerate(english_words):
            role = str(word_entry.get("role") or "").strip().lower() or "unknown"
            surface = str(word_entry.get("surface_form") or "").strip()
            english_gloss = str(word_entry.get("english_gloss") or "").strip()
            grammatical_form_raw = word_entry.get("grammatical_form")
            grammatical_form = (
                str(grammatical_form_raw).strip() if grammatical_form_raw is not None else None
            )

            word_lemma: Optional[Lemma] = None
            lemma_guid = str(word_entry.get("lemma_guid") or "").strip()
            if GenysAgent._is_real_guid(lemma_guid):
                word_lemma = session.query(Lemma).filter(Lemma.guid == lemma_guid).first()

            add_sentence_word(
                session,
                sentence=sentence_row,
                position=position,
                word_role=role,
                language_code="en",
                lemma=word_lemma,
                english_text=english_gloss or None,
                target_language_text=surface or None,
                grammatical_form=grammatical_form,
                declined_form=surface or None,
            )

    # ------------------------------------------------------------------ #
    # Main loop                                                           #
    # ------------------------------------------------------------------ #

    def process_document(
        self,
        input_path: str,
        document_language: str,
        store_sentences: bool = False,
        dry_run: bool = False,
        throttle_seconds: float = 1.0,
        limit: Optional[int] = None,
        pivot_languages: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Process a document and stage missing English words to ``PendingImport``."""
        document_path = Path(input_path)
        source_name = document_path.name
        document_text = document_path.read_text(encoding="utf-8")
        all_sentences = self.split_sentences(document_text, document_language)
        selected_sentences = all_sentences[:limit] if limit is not None else all_sentences

        target_languages = self.choose_target_languages(document_language)
        effective_pivots: List[str] = [
            lang
            for lang in (
                pivot_languages if pivot_languages is not None else DEFAULT_PIVOT_LANGUAGES
            )
            if lang != document_language.strip().lower() and lang not in target_languages
        ]

        logger.debug(
            "Genys init - document=%s language=%s total=%d selected=%d targets=%s pivots=%s",
            source_name,
            document_language,
            len(all_sentences),
            len(selected_sentences),
            ",".join(target_languages),
            ",".join(effective_pivots),
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
            "pivot_languages": effective_pivots,
            "dry_run": dry_run,
        }

        if not selected_sentences:
            return stats

        session = self.get_session()
        client = self.get_llm_client()
        model = self.config.model or "gpt-5.4-mini"

        processed_glosses: Set[str] = set()
        gloss_cache: Dict[str, Set[int]] = {}
        derivative_cache: Dict[Tuple[str, str], Set[int]] = {}

        try:
            existing_pending_glosses = self._load_pending_glosses(session)

            for sentence_index, sentence_text in enumerate(selected_sentences):
                sentence_label = f"sentence {sentence_index + 1}/{len(selected_sentences)}"
                logger.debug("Genys start - %s - %r", sentence_label, sentence_text)

                pipeline_result: TranslateAndDecomposeResult = translate_and_decompose(
                    sentence_text=sentence_text,
                    source_language=document_language,
                    session=session,
                    client=client,
                    target_languages=target_languages,
                    pivot_languages=effective_pivots,
                    decompose_languages=["en"],
                    model=model,
                )

                if not pipeline_result.phase1_ok:
                    logger.warning(
                        "Phase 1 failed at %s: %s",
                        sentence_label,
                        pipeline_result.phase1_error,
                    )
                    stats["errors"] += 1
                    continue

                english_decomposition = pipeline_result.decompositions.get("en")
                if english_decomposition is None or not english_decomposition.success:
                    err = (
                        english_decomposition.error
                        if english_decomposition is not None
                        else "no English decomposition"
                    )
                    logger.warning("Phase 3 failed at %s: %s", sentence_label, err)
                    stats["errors"] += 1
                    continue

                words = english_decomposition.words
                english_text_for_check = (
                    sentence_text
                    if document_language == "en"
                    else pipeline_result.translations.get("en", "")
                )
                if english_text_for_check:
                    self._check_decomposition_completeness(
                        english_text_for_check, words, sentence_label
                    )

                sentence_has_db_changes = False
                sentence_new_pending_glosses: Set[str] = set()

                if store_sentences and not dry_run:
                    self._store_sentence(
                        session,
                        source_name=source_name,
                        document_language=document_language,
                        sentence_text=sentence_text,
                        translations=pipeline_result.translations,
                        english_words=words,
                    )
                    sentence_has_db_changes = True

                # ── Stage pending imports ─────────────────────────────────
                english_sentence_for_context = (
                    sentence_text
                    if document_language == "en"
                    else pipeline_result.translations.get("en", "")
                )

                for word_entry in words:
                    stats["total_words_extracted"] += 1
                    surface_form = str(word_entry.get("surface_form") or "").strip()
                    english_gloss = str(word_entry.get("english_gloss") or "").strip()
                    role = str(word_entry.get("role") or "").strip().lower()
                    lemma_guid = str(word_entry.get("lemma_guid") or "").strip()

                    if not surface_form or not english_gloss:
                        continue

                    if role in SKIPPED_ROLES:
                        stats["function_words_skipped"] += 1
                        continue

                    if is_function_word(surface_form, document_language):
                        stats["function_words_skipped"] += 1
                        continue

                    if self._is_real_guid(lemma_guid):
                        stats["already_in_database"] += 1
                        continue

                    concept_key = f"gloss:{english_gloss.lower()}"
                    if concept_key in processed_glosses:
                        continue
                    processed_glosses.add(concept_key)

                    normalized_gloss = english_gloss.strip().lower()
                    if normalized_gloss in existing_pending_glosses:
                        stats["existing_pending"] += 1
                        continue

                    mapped_pos_type = ROLE_POS_MAP.get(role)

                    direct_lemma_ids = self._lemma_ids_for_english_gloss(
                        session, normalized_gloss, gloss_cache
                    )
                    if mapped_pos_type:
                        direct_lemma_ids = {
                            lid
                            for lid in direct_lemma_ids
                            if session.query(Lemma.id)
                            .filter(Lemma.id == lid, Lemma.pos_type == mapped_pos_type)
                            .first()
                        }
                    if direct_lemma_ids:
                        stats["already_in_database"] += 1
                        continue

                    form_lemma_ids = self._lemma_ids_for_derivative(
                        session, "en", normalized_gloss, derivative_cache
                    )
                    if mapped_pos_type:
                        form_lemma_ids = {
                            lid
                            for lid in form_lemma_ids
                            if session.query(Lemma.id)
                            .filter(Lemma.id == lid, Lemma.pos_type == mapped_pos_type)
                            .first()
                        }
                    if form_lemma_ids:
                        stats["already_in_database"] += 1
                        continue

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
                        example_sentence=english_sentence_for_context or None,
                    )

                    stats["staged_for_review"] += 1
                    if not dry_run:
                        session.add(pending_import)
                        sentence_has_db_changes = True
                        sentence_new_pending_glosses.add(normalized_gloss)

                if not dry_run and sentence_has_db_changes:
                    session.commit()
                    existing_pending_glosses.update(sentence_new_pending_glosses)

                if throttle_seconds > 0 and sentence_index < len(selected_sentences) - 1:
                    time.sleep(throttle_seconds)

        except Exception:
            logger.exception("Genys aborted - rolling back transaction")
            session.rollback()
            raise
        finally:
            session.close()

        return stats
