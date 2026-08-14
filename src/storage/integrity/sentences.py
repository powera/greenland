"""Integrity checks and repairs for sentences.

Repairs are staged in the caller-owned session.  These functions never commit,
roll back, or close it; the caller decides the transaction boundary.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from storage.models.schema import Lemma, Sentence, SentenceTranslation, SentenceWordHint

logger = logging.getLogger(__name__)


def period_for_language(language_code: str) -> str:
    """Return the conventional full stop for a language."""
    return "。" if language_code in ("zh", "ja") else "."


def check_sentence_levels(session: Session, *, fix: bool = False) -> Dict[str, Any]:
    """Find sentence minimum levels that disagree with linked word levels."""
    try:
        sentences = session.query(Sentence).filter(Sentence.rejected == False).all()  # noqa: E712
        issues: List[Dict[str, Any]] = []
        fixed_count = 0
        for sentence in sentences:
            word_hints = (
                session.query(SentenceWordHint, Lemma)
                .join(Lemma, SentenceWordHint.lemma_id == Lemma.id)
                .filter(SentenceWordHint.sentence_id == sentence.id)
                .all()
            )
            difficulty_levels = [
                21 if lemma.difficulty_level == -1 else lemma.difficulty_level
                for _word_hint, lemma in word_hints
                if lemma.difficulty_level is not None
            ]
            if not difficulty_levels:
                continue
            difficulty_levels.sort(reverse=True)
            expected_level = (
                difficulty_levels[1] if len(difficulty_levels) >= 3 else difficulty_levels[0]
            )
            if sentence.minimum_level == expected_level:
                continue
            issues.append(
                {
                    "sentence_id": sentence.id,
                    "current_level": sentence.minimum_level,
                    "expected_level": expected_level,
                    "word_count": len(difficulty_levels),
                    "difficulty_levels": difficulty_levels,
                }
            )
            if fix:
                sentence.minimum_level = expected_level
                fixed_count += 1
        return {
            "issue_count": len(issues),
            "fixed_count": fixed_count if fix else 0,
            "issues": issues,
        }
    except Exception as error:
        logger.error("Error checking sentence levels: %s", error)
        return {"error": str(error), "issue_count": 0, "fixed_count": 0, "issues": []}


def check_sentences_missing_punctuation(session: Session, *, fix: bool = False) -> Dict[str, Any]:
    """Find translations lacking terminal punctuation and optionally stage fixes."""
    try:
        sentences = session.query(Sentence).filter(Sentence.rejected == False).all()  # noqa: E712
        missing_punctuation: List[Dict[str, Any]] = []
        fixed_count = 0
        for sentence in sentences:
            translations = (
                session.query(SentenceTranslation)
                .filter(SentenceTranslation.sentence_id == sentence.id)
                .all()
            )
            for translation in translations:
                translation_text = translation.translation_text.strip()
                if not translation_text or translation_text[-1] in ".。?？!！":
                    continue
                missing_punctuation.append(
                    {
                        "sentence_id": sentence.id,
                        "translation_id": translation.id,
                        "language_code": translation.language_code,
                        "text": translation_text,
                        "last_char": translation_text[-1],
                    }
                )
                if fix:
                    translation.translation_text = translation_text + period_for_language(
                        translation.language_code
                    )
                    fixed_count += 1
        by_language: Dict[str, int] = {}
        for item in missing_punctuation:
            language_code = item["language_code"]
            by_language[language_code] = by_language.get(language_code, 0) + 1
        return {
            "missing_count": len(missing_punctuation),
            "fixed_count": fixed_count if fix else 0,
            "by_language": by_language,
            "missing_punctuation": missing_punctuation,
        }
    except Exception as error:
        logger.error("Error checking sentences missing punctuation: %s", error)
        return {
            "error": str(error),
            "missing_count": 0,
            "fixed_count": 0,
            "by_language": {},
            "missing_punctuation": [],
        }
