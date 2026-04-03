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
from langtools.grammatical_words import is_function_word
from sentences.analysis import SUBSTRING_MATCH_LANGUAGES
from sentences.decomposition import build_decomposition_schema, query_sentence_decomposition
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.crud.sentence import add_sentence
from storage.crud.sentence_translation import add_sentence_translation
from storage.crud.sentence_word import add_sentence_word
from storage.models.imports import PendingImport
from storage.models.schema import DerivativeForm, Lemma
from storage.translation_helpers import (
    LANGUAGE_NAMES,
    get_tier_1_and_tier_2_languages,
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
        """Choose exactly 3 target languages for decomposition output."""
        normalized_document_language = document_language.strip().lower()
        preferred_languages = ["en", "zh", "fr"]
        fallback_pool = get_tier_1_and_tier_2_languages()
        selection_pool = preferred_languages + fallback_pool
        selected_languages = [
            language_code
            for language_code in selection_pool
            if language_code != normalized_document_language
        ]

        return normalize_llm_language_codes(
            selected_languages[:3],
            operation_name="Genys document decomposition",
        )

    def _build_decompose_prompt(
        self,
        sentence_text: str,
        target_languages: Sequence[str],
    ) -> Tuple[str, str]:
        """Build context+prompt for translate_and_decompose template."""
        target_language_names = [
            LANGUAGE_NAMES.get(language_code, language_code) for language_code in target_languages
        ]

        prompt = get_prompt("sentence_decomposition", "translate_and_decompose").format(
            template_sentence=sentence_text,
            word_translations="- (none provided)",
            target_language_names=", ".join(target_language_names),
            english_instruction=(
                "IMPORTANT: Also provide a grammatically correct English version "
                "(fixing issues like singular/plural, articles, etc.)."
            ),
        )
        context = get_context("sentence_decomposition", "translate_and_decompose")
        return context, prompt

    @staticmethod
    def _normalize_word_role(raw_role: Any) -> str:
        role_value = str(raw_role or "").strip().lower()
        return role_value

    @staticmethod
    def _normalize_surface_form(raw_word: Any) -> str:
        return str(raw_word or "").strip()

    @staticmethod
    def _normalize_english_gloss(raw_gloss: Any) -> str:
        return str(raw_gloss or "").strip()

    def _query_decomposition(
        self,
        sentence_text: str,
        target_languages: Sequence[str],
    ) -> Dict[str, Any]:
        context, prompt = self._build_decompose_prompt(sentence_text, target_languages)
        schema = build_decomposition_schema(
            target_languages=list(target_languages), include_english=False
        )
        result = query_sentence_decomposition(
            prompt=prompt,
            client=self.get_llm_client(),
            model=self.config.model or "gpt-5.4-mini",
            json_schema=schema,
            context=context,
        )
        return result

    @staticmethod
    def _get_words_for_language(
        decomposition_data: Dict[str, Any], language_code: str
    ) -> List[Dict[str, Any]]:
        key = f"words_{language_code}"
        words = decomposition_data.get(key, [])
        if isinstance(words, list):
            return [word for word in words if isinstance(word, dict)]
        return []

    def _load_pending_glosses(self, session: Any) -> Set[str]:
        pending_rows = session.query(PendingImport.english_word).all()
        return {str(row[0]).strip().lower() for row in pending_rows if row[0]}

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
        lemma_ids = {lemma_row[0] for lemma_row in lemma_rows}
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

        lemma_ids = {row[0] for row in rows}
        cache[cache_key] = lemma_ids
        return lemma_ids

    def process_document(
        self,
        input_path: str,
        document_language: str,
        store_sentences: bool = False,
        dry_run: bool = False,
        throttle_seconds: float = 1.0,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Process a document and stage missing words to PendingImport."""
        document_path = Path(input_path)
        source_name = document_path.name
        document_text = document_path.read_text(encoding="utf-8")
        all_sentences = self.split_sentences(document_text, document_language)
        if limit is not None:
            selected_sentences = all_sentences[:limit]
        else:
            selected_sentences = all_sentences

        target_languages = self.choose_target_languages(document_language)

        stats: Dict[str, Any] = {
            "document": source_name,
            "document_language": document_language,
            "sentences_parsed": len(selected_sentences),
            "estimated_llm_calls": len(selected_sentences),
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
            return stats

        session = self.get_session()
        processed_glosses: Set[str] = set()
        lemma_gloss_cache: Dict[str, Set[int]] = {}
        derivative_cache: Dict[Tuple[str, str], Set[int]] = {}

        try:
            existing_pending_glosses = self._load_pending_glosses(session)

            for sentence_index, sentence_text in enumerate(selected_sentences):
                decomposition_result = self._query_decomposition(sentence_text, target_languages)
                if not decomposition_result.get("success"):
                    logger.warning(
                        "Sentence decomposition failed at sentence %d: %s",
                        sentence_index,
                        decomposition_result.get("error", "unknown error"),
                    )
                    stats["errors"] += 1
                    continue

                sentence_words_for_storage: Optional[List[Dict[str, Any]]] = None
                if store_sentences:
                    sentence_words_for_storage = self._get_words_for_language(
                        decomposition_result,
                        document_language,
                    )
                    if not sentence_words_for_storage and target_languages:
                        sentence_words_for_storage = self._get_words_for_language(
                            decomposition_result,
                            target_languages[0],
                        )

                concepts_by_gloss: Dict[str, Dict[str, Any]] = defaultdict(
                    lambda: {
                        "forms_by_language": {},
                        "surface_document": None,
                        "pos_type": None,
                        "role": None,
                        "english_gloss": None,
                    }
                )

                for language_code in target_languages:
                    words = self._get_words_for_language(decomposition_result, language_code)
                    for word_entry in words:
                        stats["total_words_extracted"] += 1
                        surface_form = self._normalize_surface_form(word_entry.get("word"))
                        english_gloss = self._normalize_english_gloss(word_entry.get("english"))
                        role = self._normalize_word_role(word_entry.get("role"))

                        if not surface_form or not english_gloss:
                            continue

                        if role in SKIPPED_ROLES:
                            stats["function_words_skipped"] += 1
                            continue

                        if is_function_word(surface_form, language_code):
                            stats["function_words_skipped"] += 1
                            continue

                        concept_row = concepts_by_gloss[english_gloss.lower()]
                        concept_row["forms_by_language"][language_code] = surface_form
                        concept_row["role"] = concept_row["role"] or role
                        concept_row["english_gloss"] = concept_row["english_gloss"] or english_gloss
                        mapped_pos_type = ROLE_POS_MAP.get(role)
                        concept_row["pos_type"] = concept_row["pos_type"] or mapped_pos_type

                for normalized_gloss, concept in concepts_by_gloss.items():
                    if normalized_gloss in processed_glosses:
                        continue
                    processed_glosses.add(normalized_gloss)

                    forms_by_language: Dict[str, str] = concept["forms_by_language"]
                    english_gloss_value = str(
                        concept.get("english_gloss") or normalized_gloss
                    ).strip()
                    for language_code in target_languages:
                        if (
                            language_code == document_language
                            and language_code in forms_by_language
                        ):
                            concept["surface_document"] = forms_by_language[language_code]
                            break
                    if concept["surface_document"] is None:
                        concept["surface_document"] = next(iter(forms_by_language.values()), "")

                    lemma_ids_for_gloss = self._lemma_ids_for_english_gloss(
                        session,
                        normalized_gloss,
                        lemma_gloss_cache,
                    )

                    matched_languages_by_lemma: Dict[int, Set[str]] = defaultdict(set)
                    for language_code, surface_form in forms_by_language.items():
                        derivative_lemma_ids = self._lemma_ids_for_derivative(
                            session,
                            language_code,
                            surface_form,
                            derivative_cache,
                        )
                        for lemma_id in lemma_ids_for_gloss.intersection(derivative_lemma_ids):
                            matched_languages_by_lemma[lemma_id].add(language_code)

                    exists_in_database = any(
                        len(language_matches) >= 2
                        for language_matches in matched_languages_by_lemma.values()
                    )
                    if exists_in_database:
                        stats["already_in_database"] += 1
                        continue

                    if normalized_gloss in existing_pending_glosses:
                        stats["existing_pending"] += 1
                        continue

                    pending_import = PendingImport(
                        english_word=english_gloss_value,
                        definition=english_gloss_value,
                        disambiguation_translation=concept["surface_document"] or normalized_gloss,
                        disambiguation_language=document_language,
                        pos_type=concept["pos_type"],
                        pos_subtype=None,
                        source=f"genys/{source_name}",
                        frequency_rank=None,
                        notes=f"From document: {source_name}",
                    )

                    stats["staged_for_review"] += 1
                    if not dry_run:
                        session.add(pending_import)
                        existing_pending_glosses.add(normalized_gloss)

                if store_sentences and sentence_words_for_storage is not None and not dry_run:
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

                    for word_position, word_entry in enumerate(sentence_words_for_storage):
                        word_role = self._normalize_word_role(word_entry.get("role")) or "unknown"
                        add_sentence_word(
                            session,
                            sentence=sentence_row,
                            position=word_position,
                            word_role=word_role,
                            language_code=document_language,
                            lemma=None,
                            english_text=self._normalize_english_gloss(word_entry.get("english"))
                            or None,
                            target_language_text=self._normalize_surface_form(
                                word_entry.get("word")
                            )
                            or None,
                            grammatical_form=(
                                str(word_entry.get("grammatical_form")).strip()
                                if word_entry.get("grammatical_form") is not None
                                else None
                            ),
                            declined_form=self._normalize_surface_form(word_entry.get("word"))
                            or None,
                        )

                if throttle_seconds > 0 and sentence_index < len(selected_sentences) - 1:
                    time.sleep(throttle_seconds)

            if not dry_run:
                session.commit()

        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        return stats
