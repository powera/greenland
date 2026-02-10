#!/usr/bin/env python3
"""
Erelis Agent - Core logic for false lemma match detection.

This module detects cases where a sentence has a linked lemma, but the lemma's
translation doesn't appear in the sentence translation, indicating a semantic
mismatch.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.models.schema import (
    DerivativeForm,
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)


@dataclass
class FalseLemmaMatch:
    """Represents a detected false lemma match."""

    sentence_id: int
    sentence_word_id: int
    lemma_id: int
    lemma_guid: str
    lemma_english: str
    lemma_translation: str
    sentence_english: str
    sentence_translation: str
    language_code: str
    word_role: str
    position: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sentence_id": self.sentence_id,
            "sentence_word_id": self.sentence_word_id,
            "lemma_id": self.lemma_id,
            "lemma_guid": self.lemma_guid,
            "lemma_english": self.lemma_english,
            "lemma_translation": self.lemma_translation,
            "sentence_english": self.sentence_english,
            "sentence_translation": self.sentence_translation,
            "language_code": self.language_code,
            "word_role": self.word_role,
            "position": self.position,
        }


class ErelisAgent:
    """Agent for detecting false lemma matches in sentences."""

    def __init__(self, config: DataSourceConfig):
        """
        Initialize the Erelis agent.

        Args:
            config: DataSourceConfig with backend settings
        """
        self.config = config
        self.debug = config.debug

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def check_sentence(
        self,
        session: Session,
        sentence_id: int,
        target_language: str,
    ) -> List[FalseLemmaMatch]:
        """
        Check a single sentence for false lemma matches.

        Args:
            session: Database session
            sentence_id: ID of the sentence to check
            target_language: Language code to check (e.g., 'zh', 'lt')

        Returns:
            List of FalseLemmaMatch objects for detected mismatches
        """
        matches: List[FalseLemmaMatch] = []

        # Get sentence with translations
        sentence = session.query(Sentence).filter(Sentence.id == sentence_id).first()
        if not sentence:
            logger.warning(f"Sentence {sentence_id} not found")
            return matches

        # Get sentence translations
        english_trans = (
            session.query(SentenceTranslation)
            .filter(
                SentenceTranslation.sentence_id == sentence_id,
                SentenceTranslation.language_code == "en",
            )
            .first()
        )
        target_trans = (
            session.query(SentenceTranslation)
            .filter(
                SentenceTranslation.sentence_id == sentence_id,
                SentenceTranslation.language_code == target_language,
            )
            .first()
        )

        if not target_trans:
            logger.debug(f"Sentence {sentence_id} has no {target_language} translation, skipping")
            return matches

        sentence_english = english_trans.translation_text if english_trans else ""
        sentence_target = target_trans.translation_text

        # Get sentence words with linked lemmas
        sentence_words = (
            session.query(SentenceWord)
            .filter(
                SentenceWord.sentence_id == sentence_id,
                SentenceWord.lemma_id.isnot(None),
            )
            .options(joinedload(SentenceWord.lemma))
            .all()
        )

        for sw in sentence_words:
            lemma = sw.lemma
            if not lemma:
                continue

            # Get lemma translation in target language
            lemma_trans = get_translation(session, lemma, target_language)
            if not lemma_trans:
                logger.debug(
                    f"Lemma {lemma.guid} ({lemma.lemma_text}) has no {target_language} "
                    "translation, skipping"
                )
                continue

            # Get all derivative forms for this lemma in target language
            derivative_forms = (
                session.query(DerivativeForm.derivative_form_text)
                .filter(
                    DerivativeForm.lemma_id == lemma.id,
                    DerivativeForm.language_code == target_language,
                )
                .all()
            )
            all_forms = [lemma_trans] + [df[0] for df in derivative_forms]

            # Check if lemma translation or any derivative form appears in sentence
            if not self._check_forms_match(all_forms, sentence_target, target_language):
                match = FalseLemmaMatch(
                    sentence_id=sentence_id,
                    sentence_word_id=sw.id,
                    lemma_id=lemma.id,
                    lemma_guid=lemma.guid or "",
                    lemma_english=lemma.lemma_text,
                    lemma_translation=lemma_trans,
                    sentence_english=sentence_english,
                    sentence_translation=sentence_target,
                    language_code=target_language,
                    word_role=sw.word_role,
                    position=sw.position,
                )
                matches.append(match)
                logger.info(
                    f"False match: sentence {sentence_id}, lemma '{lemma.lemma_text}' "
                    f"({lemma_trans}) not in '{sentence_target}'"
                )

        return matches

    def _check_forms_match(self, forms: List[str], sentence_trans: str, lang_code: str) -> bool:
        """
        Check if any form (base lemma or derivative) appears in the sentence.

        Args:
            forms: List of forms to check (base translation + derivative forms)
            sentence_trans: The sentence's translation
            lang_code: Language code for language-specific handling

        Returns:
            True if any form matches, False otherwise
        """
        for form in forms:
            if self._check_translation_match(form, sentence_trans, lang_code):
                return True
        return False

    def _check_translation_match(
        self, lemma_trans: str, sentence_trans: str, lang_code: str
    ) -> bool:
        """
        Check if a lemma translation appears in a sentence translation.

        This handles language-specific matching, e.g., for Chinese we check
        character-by-character for any common characters.

        Args:
            lemma_trans: The lemma's translation
            sentence_trans: The sentence's translation
            lang_code: Language code for language-specific handling

        Returns:
            True if the lemma translation appears to match, False otherwise
        """
        # Normalize whitespace
        lemma_trans = lemma_trans.strip()
        sentence_trans = sentence_trans.strip()

        # Simple substring check first
        if lemma_trans in sentence_trans:
            return True

        # For CJK languages, check for any common characters
        # This handles cases where the form might differ but the root is present
        if lang_code in ("zh", "ja", "ko"):
            # Check if any character from lemma appears in sentence
            # (at least one meaningful character match)
            for char in lemma_trans:
                # Skip punctuation and common particles
                if char in "的了是在有和与或等个人我你他她它们这那" "。，、；：！？" "''（）【】":
                    continue
                if char in sentence_trans:
                    return True
            return False

        # For languages with spaces, also try word-level matching
        lemma_words = set(lemma_trans.lower().split())
        sentence_words = set(sentence_trans.lower().split())

        # Check if any lemma word appears in sentence
        if lemma_words & sentence_words:
            return True

        return False

    def check_all_sentences(
        self,
        target_language: str,
        limit: Optional[int] = None,
        sentence_id: Optional[int] = None,
        lemma_guid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check all sentences (or filtered subset) for false lemma matches.

        Args:
            target_language: Language code to check (e.g., 'zh', 'lt')
            limit: Maximum number of sentences to check
            sentence_id: If provided, only check this sentence
            lemma_guid: If provided, only check sentences containing this lemma

        Returns:
            Dictionary with check results and statistics
        """
        session = self.get_session()
        try:
            all_matches: List[FalseLemmaMatch] = []

            # Build query for sentence IDs to check
            if sentence_id:
                sentence_ids = [sentence_id]
            elif lemma_guid:
                # Find sentences containing this lemma
                lemma = session.query(Lemma).filter(Lemma.guid == lemma_guid).first()
                if not lemma:
                    return {
                        "success": False,
                        "error": f"Lemma with GUID {lemma_guid} not found",
                    }

                sentence_ids = [
                    sw.sentence_id
                    for sw in session.query(SentenceWord.sentence_id)
                    .filter(SentenceWord.lemma_id == lemma.id)
                    .distinct()
                    .all()
                ]
            else:
                # Get all sentences that have both:
                # 1. Linked lemmas (via SentenceWord)
                # 2. A translation in the target language
                sentence_ids_with_lemmas = (
                    select(SentenceWord.sentence_id)
                    .where(SentenceWord.lemma_id.isnot(None))
                    .distinct()
                )

                sentence_ids_with_trans = (
                    select(SentenceTranslation.sentence_id)
                    .where(SentenceTranslation.language_code == target_language)
                    .distinct()
                )

                query = (
                    session.query(Sentence.id)
                    .filter(
                        Sentence.id.in_(sentence_ids_with_lemmas),
                        Sentence.id.in_(sentence_ids_with_trans),
                    )
                    .order_by(Sentence.id)
                )

                if limit:
                    query = query.limit(limit)

                sentence_ids = [row[0] for row in query.all()]

            logger.info(f"Checking {len(sentence_ids)} sentences for false matches")

            # Check each sentence
            checked_count = 0
            for sid in sentence_ids:
                matches = self.check_sentence(session, sid, target_language)
                all_matches.extend(matches)
                checked_count += 1

                if checked_count % 100 == 0:
                    logger.info(f"Checked {checked_count} sentences...")

            # Group matches by lemma for summary
            lemma_summary: Dict[str, int] = {}
            for match in all_matches:
                key = f"{match.lemma_guid} ({match.lemma_english})"
                lemma_summary[key] = lemma_summary.get(key, 0) + 1

            return {
                "success": True,
                "target_language": target_language,
                "sentences_checked": checked_count,
                "false_matches_found": len(all_matches),
                "matches": [m.to_dict() for m in all_matches],
                "lemma_summary": lemma_summary,
            }

        except Exception as e:
            logger.error(f"Error checking sentences: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    def get_statistics(self, target_language: str) -> Dict[str, Any]:
        """
        Get statistics about sentences and lemma links.

        Args:
            target_language: Language code to get stats for

        Returns:
            Dictionary with statistics
        """
        session = self.get_session()
        try:
            total_sentences = session.query(func.count(Sentence.id)).scalar()

            sentences_with_lemmas = (
                session.query(func.count(func.distinct(SentenceWord.sentence_id)))
                .filter(SentenceWord.lemma_id.isnot(None))
                .scalar()
            )

            sentences_with_target_trans = (
                session.query(func.count(func.distinct(SentenceTranslation.sentence_id)))
                .filter(SentenceTranslation.language_code == target_language)
                .scalar()
            )

            total_sentence_words = (
                session.query(func.count(SentenceWord.id))
                .filter(SentenceWord.lemma_id.isnot(None))
                .scalar()
            )

            return {
                "total_sentences": total_sentences,
                "sentences_with_lemmas": sentences_with_lemmas,
                "sentences_with_target_translation": sentences_with_target_trans,
                "total_lemma_links": total_sentence_words,
                "target_language": target_language,
            }

        finally:
            session.close()
