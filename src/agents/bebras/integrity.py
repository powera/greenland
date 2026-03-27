#!/usr/bin/env python3
"""
Database Integrity Checker

Checks database structural integrity and identifies data quality issues like
orphaned records, missing required fields, and constraint violations.
"""

import argparse
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, cast

import constants
from sqlalchemy import or_
from ipa import has_ipa_characters
from storage.database import create_database_session
from storage.models.schema import (
    Corpus,
    DerivativeForm,
    Lemma,
    Sentence,
    SentenceTranslation,
    WordFrequency,
    WordToken,
)

logger = logging.getLogger(__name__)


class IntegrityChecker:
    """Database integrity checker."""

    _PROMPT_LEAK_HINTS: Tuple[str, ...] = (
        "the user wants",
        "i should provide",
        "pronunciation of the word",
        "simplified phonetic representation",
        "ipa pronunciation",
    )

    def __init__(self, db_path: Optional[str] = None, debug: bool = False):
        """
        Initialize the integrity checker.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        """Get database session."""
        return create_database_session(self.db_path)

    def check_orphaned_derivative_forms(self) -> Dict[str, Any]:
        """Check for derivative forms with invalid lemma_id references."""
        logger.info("Checking for orphaned derivative forms...")

        session = self.get_session()
        try:
            valid_lemma_ids = set(lemma_id for lemma_id, in session.query(Lemma.id).all())
            logger.info(f"Found {len(valid_lemma_ids)} valid lemma IDs")

            derivative_forms = session.query(DerivativeForm).all()
            orphaned = [
                {
                    "id": form.id,
                    "derivative_form_text": form.derivative_form_text,
                    "language_code": form.language_code,
                    "invalid_lemma_id": form.lemma_id,
                }
                for form in derivative_forms
                if form.lemma_id not in valid_lemma_ids
            ]

            logger.info(f"Found {len(orphaned)} orphaned derivative forms")

            return {
                "total_checked": len(derivative_forms),
                "orphaned_count": len(orphaned),
                "orphaned_forms": orphaned,
            }

        except Exception as e:
            logger.error(f"Error checking orphaned derivative forms: {e}")
            return {"error": str(e), "total_checked": 0, "orphaned_count": 0, "orphaned_forms": []}
        finally:
            session.close()

    def check_derivative_form_word_tokens(self) -> Dict[str, Any]:
        """Check for derivative forms with invalid word_token_id references or mismatched text."""
        logger.info("Checking derivative form word token references...")

        session = self.get_session()
        try:
            word_tokens_dict = {
                token_id: token_text
                for token_id, token_text in session.query(WordToken.id, WordToken.token).all()
            }
            logger.info(f"Found {len(word_tokens_dict)} valid word tokens")

            derivative_forms = (
                session.query(DerivativeForm).filter(DerivativeForm.word_token_id.isnot(None)).all()
            )

            issues = []
            for form in derivative_forms:
                form_issues = []
                if form.word_token_id not in word_tokens_dict:
                    form_issues.append(f"invalid_word_token_id: {form.word_token_id}")
                elif form.derivative_form_text != word_tokens_dict[form.word_token_id]:
                    expected_token = word_tokens_dict[form.word_token_id]
                    form_issues.append(
                        f"text_mismatch: derivative_form_text='{form.derivative_form_text}' "
                        f"but word_token.token='{expected_token}'"
                    )

                if form_issues:
                    issues.append(
                        {
                            "id": form.id,
                            "derivative_form_text": form.derivative_form_text,
                            "word_token_id": form.word_token_id,
                            "lemma_id": form.lemma_id,
                            "language_code": form.language_code,
                            "issues": form_issues,
                        }
                    )

            logger.info(f"Found {len(issues)} derivative forms with word token issues")

            return {
                "total_checked": len(derivative_forms),
                "issue_count": len(issues),
                "issues": issues,
            }

        except Exception as e:
            logger.error(f"Error checking derivative form word tokens: {e}")
            return {"error": str(e), "total_checked": 0, "issue_count": 0, "issues": []}
        finally:
            session.close()

    def check_orphaned_word_frequencies(self) -> Dict[str, Any]:
        """Check for word frequencies with invalid word_token_id or corpus_id."""
        logger.info("Checking for orphaned word frequencies...")

        session = self.get_session()
        try:
            valid_token_ids = set(token_id for token_id, in session.query(WordToken.id).all())
            valid_corpus_ids = set(corpus_id for corpus_id, in session.query(Corpus.id).all())

            logger.info(
                f"Found {len(valid_token_ids)} valid token IDs and {len(valid_corpus_ids)} valid corpus IDs"
            )

            frequencies = session.query(WordFrequency).all()
            orphaned = []

            for freq in frequencies:
                issues = []
                if freq.word_token_id not in valid_token_ids:
                    issues.append(f"invalid_word_token_id: {freq.word_token_id}")
                if freq.corpus_id not in valid_corpus_ids:
                    issues.append(f"invalid_corpus_id: {freq.corpus_id}")

                if issues:
                    orphaned.append(
                        {
                            "id": freq.id,
                            "word_token_id": freq.word_token_id,
                            "corpus_id": freq.corpus_id,
                            "issues": issues,
                        }
                    )

            logger.info(f"Found {len(orphaned)} orphaned word frequencies")

            return {
                "total_checked": len(frequencies),
                "orphaned_count": len(orphaned),
                "orphaned_frequencies": orphaned,
            }

        except Exception as e:
            logger.error(f"Error checking orphaned word frequencies: {e}")
            return {
                "error": str(e),
                "total_checked": 0,
                "orphaned_count": 0,
                "orphaned_frequencies": [],
            }
        finally:
            session.close()

    def check_missing_required_fields(self) -> Dict[str, Any]:
        """Check for records with missing required fields."""
        logger.info("Checking for missing required fields...")

        session = self.get_session()
        try:
            issues = []

            # Check Lemmas for missing fields
            for lemma in (
                session.query(Lemma)
                .filter((Lemma.definition_text.is_(None)) | (Lemma.definition_text == ""))
                .all()
            ):
                issues.append(
                    {
                        "table": "lemmas",
                        "id": lemma.id,
                        "guid": lemma.guid,
                        "lemma_text": lemma.lemma_text,
                        "missing_field": "definition_text",
                        "severity": "high",
                    }
                )

            for lemma in (
                session.query(Lemma)
                .filter((Lemma.pos_type.is_(None)) | (Lemma.pos_type == ""))
                .all()
            ):
                issues.append(
                    {
                        "table": "lemmas",
                        "id": lemma.id,
                        "guid": lemma.guid,
                        "lemma_text": lemma.lemma_text,
                        "missing_field": "pos_type",
                        "severity": "high",
                    }
                )

            for lemma in (
                session.query(Lemma)
                .filter(Lemma.guid.isnot(None), Lemma.difficulty_level.is_(None))
                .all()
            ):
                issues.append(
                    {
                        "table": "lemmas",
                        "id": lemma.id,
                        "guid": lemma.guid,
                        "lemma_text": lemma.lemma_text,
                        "missing_field": "difficulty_level",
                        "severity": "medium",
                    }
                )

            logger.info(f"Found {len(issues)} records with missing required fields")

            high_severity = [i for i in issues if i["severity"] == "high"]
            medium_severity = [i for i in issues if i["severity"] == "medium"]

            return {
                "total_issues": len(issues),
                "high_severity_count": len(high_severity),
                "medium_severity_count": len(medium_severity),
                "high_severity_issues": high_severity,
                "medium_severity_issues": medium_severity,
            }

        except Exception as e:
            logger.error(f"Error checking missing required fields: {e}")
            return {
                "error": str(e),
                "total_issues": 0,
                "high_severity_count": 0,
                "medium_severity_count": 0,
                "high_severity_issues": [],
                "medium_severity_issues": [],
            }
        finally:
            session.close()

    def check_lemmas_without_derivatives(self) -> Dict[str, Any]:
        """Check for lemmas that have no derivative forms at all."""
        logger.info("Checking for lemmas without derivative forms...")

        session = self.get_session()
        try:
            all_lemma_ids = set(lemma.id for lemma in session.query(Lemma).all())
            lemmas_with_forms = set(
                lemma_id for lemma_id, in session.query(DerivativeForm.lemma_id).distinct().all()
            )
            lemmas_without_forms_ids = all_lemma_ids - lemmas_with_forms

            lemmas_without_forms = [
                {
                    "id": lemma.id,
                    "guid": lemma.guid,
                    "lemma_text": lemma.lemma_text,
                    "pos_type": lemma.pos_type,
                    "difficulty_level": lemma.difficulty_level,
                }
                for lemma_id in lemmas_without_forms_ids
                if (lemma := session.query(Lemma).filter(Lemma.id == lemma_id).first())
            ]

            logger.info(f"Found {len(lemmas_without_forms)} lemmas without derivative forms")

            return {
                "total_lemmas": len(all_lemma_ids),
                "without_forms_count": len(lemmas_without_forms),
                "lemmas_without_forms": lemmas_without_forms,
            }

        except Exception as e:
            logger.error(f"Error checking lemmas without derivative forms: {e}")
            return {
                "error": str(e),
                "total_lemmas": 0,
                "without_forms_count": 0,
                "lemmas_without_forms": [],
            }
        finally:
            session.close()

    def check_duplicate_guids(self) -> Dict[str, Any]:
        """Check for duplicate GUIDs in lemmas table."""
        logger.info("Checking for duplicate GUIDs...")

        session = self.get_session()
        try:
            from sqlalchemy import func

            guid_counts = (
                session.query(Lemma.guid, func.count(Lemma.id).label("count"))
                .filter(Lemma.guid.isnot(None))
                .group_by(Lemma.guid)
                .having(func.count(Lemma.id) > 1)
                .all()
            )

            duplicates = []
            for guid, count in guid_counts:
                lemmas = session.query(Lemma).filter(Lemma.guid == guid).all()
                duplicate_entry = {
                    "guid": guid,
                    "count": count,
                    "lemmas": [
                        {
                            "id": lemma.id,
                            "lemma_text": lemma.lemma_text,
                            "pos_type": lemma.pos_type,
                            "difficulty_level": lemma.difficulty_level,
                        }
                        for lemma in lemmas
                    ],
                }
                duplicates.append(duplicate_entry)

            logger.info(f"Found {len(duplicates)} duplicate GUIDs")

            return {"duplicate_count": len(duplicates), "duplicates": duplicates}

        except Exception as e:
            logger.error(f"Error checking duplicate GUIDs: {e}")
            return {"error": str(e), "duplicate_count": 0, "duplicates": []}
        finally:
            session.close()

    def check_duplicate_words(self) -> Dict[str, Any]:
        """Check for duplicate lemmas sharing the same text and part of speech.

        Finds groups of lemmas that have the same (lemma_text, pos_type) and
        either both lack a disambiguation or share the same disambiguation.
        These are likely unintentional duplicates that should be merged.

        Lemmas that differ only in disambiguation (e.g. "mouse (animal)" vs
        "mouse (computer)") are intentional and excluded from this check.
        """
        logger.info("Checking for duplicate words...")

        session = self.get_session()
        try:
            from sqlalchemy import func

            # Find (lemma_text, pos_type, disambiguation) groups with more
            # than one lemma.  We coalesce NULL disambiguation to empty string
            # so that two NULL disambiguations are treated as equal.
            coalesced_disambig = func.coalesce(Lemma.disambiguation, "")

            dup_groups = (
                session.query(
                    Lemma.lemma_text,
                    Lemma.pos_type,
                    coalesced_disambig.label("disambig"),
                    func.count(Lemma.id).label("cnt"),
                )
                .group_by(Lemma.lemma_text, Lemma.pos_type, coalesced_disambig)
                .having(func.count(Lemma.id) > 1)
                .all()
            )

            duplicates: List[Dict[str, Any]] = []
            for lemma_text, pos_type, disambig, cnt in dup_groups:
                # Fetch the actual lemmas in this group
                query = session.query(Lemma).filter(
                    Lemma.lemma_text == lemma_text,
                    Lemma.pos_type == pos_type,
                )
                if disambig:
                    query = query.filter(Lemma.disambiguation == disambig)
                else:
                    query = query.filter(
                        (Lemma.disambiguation.is_(None)) | (Lemma.disambiguation == "")
                    )

                lemmas = query.all()
                duplicates.append(
                    {
                        "lemma_text": lemma_text,
                        "pos_type": pos_type,
                        "disambiguation": disambig or None,
                        "count": len(lemmas),
                        "lemmas": [
                            {
                                "id": lemma.id,
                                "guid": lemma.guid,
                                "definition_text": lemma.definition_text,
                                "difficulty_level": lemma.difficulty_level,
                                "verified": lemma.verified,
                            }
                            for lemma in lemmas
                        ],
                    }
                )

            logger.info(
                f"Found {len(duplicates)} groups of duplicate words "
                f"({sum(d['count'] for d in duplicates)} total lemmas)"
            )

            return {
                "duplicate_group_count": len(duplicates),
                "total_duplicate_lemmas": sum(d["count"] for d in duplicates),
                "duplicates": duplicates,
            }

        except Exception as e:
            logger.error(f"Error checking duplicate words: {e}")
            return {
                "error": str(e),
                "duplicate_group_count": 0,
                "total_duplicate_lemmas": 0,
                "duplicates": [],
            }
        finally:
            session.close()

    def check_invalid_difficulty_levels(self) -> Dict[str, Any]:
        """Check for difficulty levels outside the valid range (1-20)."""
        logger.info("Checking for invalid difficulty levels...")

        session = self.get_session()
        try:
            invalid_lemmas = (
                session.query(Lemma)
                .filter(
                    Lemma.difficulty_level.isnot(None),
                    ((Lemma.difficulty_level < 1) | (Lemma.difficulty_level > 20)),
                )
                .all()
            )

            invalid_entries = [
                {
                    "id": lemma.id,
                    "guid": lemma.guid,
                    "lemma_text": lemma.lemma_text,
                    "invalid_level": lemma.difficulty_level,
                }
                for lemma in invalid_lemmas
            ]

            logger.info(f"Found {len(invalid_entries)} lemmas with invalid difficulty levels")

            return {"invalid_count": len(invalid_entries), "invalid_entries": invalid_entries}

        except Exception as e:
            logger.error(f"Error checking invalid difficulty levels: {e}")
            return {"error": str(e), "invalid_count": 0, "invalid_entries": []}
        finally:
            session.close()

    def _get_max_pronunciation_length(self, lemma_text: Optional[str]) -> int:
        """Return a max pronunciation length based on source text length."""
        if not lemma_text:
            return 40

        source_len = len(lemma_text.strip())
        # Single words stay fairly strict; phrases/sentences get proportionally more room.
        return max(20, source_len * 4 + 8)

    def _is_suspicious_pronunciation_text(
        self,
        pronunciation_text: str,
        source_text: Optional[str],
        field_name: str,
    ) -> Tuple[bool, List[str]]:
        """Return whether pronunciation text looks like leaked instructions/bad content."""
        reasons: List[str] = []
        normalized_text = pronunciation_text.strip()
        lowercase_text = normalized_text.lower()
        ascii_word_matches = re.findall(r"[A-Za-z]{3,}", normalized_text)

        max_length = self._get_max_pronunciation_length(source_text)
        if len(normalized_text) > max_length:
            reasons.append(f"too_long_for_source_text:max={max_length}")

        for hint in self._PROMPT_LEAK_HINTS:
            if hint in lowercase_text:
                reasons.append(f"contains_prompt_phrase:{hint}")

        if len(ascii_word_matches) >= 4 and not self._looks_like_phonetic_syllables(
            normalized_text, field_name
        ):
            reasons.append("contains_many_ascii_words")

        if "\n" in normalized_text:
            reasons.append("contains_newline")

        if field_name == "ipa":
            slash_count = normalized_text.count("/")
            has_ipa_like_characters = has_ipa_characters(normalized_text)
            if slash_count < 2 and not has_ipa_like_characters and len(ascii_word_matches) >= 2:
                reasons.append("lacks_ipa_delimiters_or_symbols")
        else:
            if re.search(r"[{}[\]<>]", normalized_text):
                reasons.append("contains_structural_characters")
            if ":" in normalized_text and len(ascii_word_matches) >= 2:
                reasons.append("contains_colon_with_words")

        return (len(reasons) > 0, reasons)

    def _looks_like_phonetic_syllables(self, pronunciation_text: str, field_name: str) -> bool:
        """Return whether text resembles syllabified English-friendly phonetics."""
        if field_name != "phonetic" or "-" not in pronunciation_text:
            return False

        letter_tokens = re.findall(r"[A-Za-z]+", pronunciation_text)
        if len(letter_tokens) < 2:
            return False

        long_token_count = sum(1 for token in letter_tokens if len(token) > 6)
        if long_token_count > 0:
            return False

        punctuation_stripped = pronunciation_text.replace("(", "").replace(")", "")
        punctuation_stripped = punctuation_stripped.replace("/", "").replace(" ", "")
        has_expected_characters = bool(re.fullmatch(r"[A-Za-z'–—-]+", punctuation_stripped))

        return has_expected_characters

    def check_pronunciation_fields(self, fix: bool = False) -> Dict[str, Any]:
        """Check IPA/phonetic fields for clearly invalid prompt-leak content.

        If fix=True and either IPA or phonetic is suspicious for a form,
        both pronunciation fields are cleared.
        """
        logger.info("Checking pronunciation fields for suspicious content...")

        session = self.get_session()
        try:
            forms_with_pronunciations = (
                session.query(DerivativeForm)
                .filter(
                    or_(
                        (DerivativeForm.ipa_pronunciation.isnot(None))
                        & (DerivativeForm.ipa_pronunciation != ""),
                        (DerivativeForm.phonetic_pronunciation.isnot(None))
                        & (DerivativeForm.phonetic_pronunciation != ""),
                    )
                )
                .all()
            )

            suspicious_entries: List[Dict[str, Any]] = []
            fixed_count = 0
            for form in forms_with_pronunciations:
                ipa_value = str(form.ipa_pronunciation or "")
                phonetic_value = str(form.phonetic_pronunciation or "")
                source_text = form.derivative_form_text or (
                    form.lemma.lemma_text if form.lemma else None
                )

                ipa_is_suspicious = False
                ipa_reasons: List[str] = []
                if ipa_value:
                    ipa_is_suspicious, ipa_reasons = self._is_suspicious_pronunciation_text(
                        ipa_value,
                        source_text,
                        "ipa",
                    )

                phonetic_is_suspicious = False
                phonetic_reasons: List[str] = []
                if phonetic_value:
                    phonetic_is_suspicious, phonetic_reasons = (
                        self._is_suspicious_pronunciation_text(
                            phonetic_value,
                            source_text,
                            "phonetic",
                        )
                    )

                if not ipa_is_suspicious and not phonetic_is_suspicious:
                    continue

                bad_fields: List[str] = []
                reasons: Dict[str, List[str]] = {}
                if ipa_is_suspicious:
                    bad_fields.append("ipa")
                    reasons["ipa"] = ipa_reasons
                if phonetic_is_suspicious:
                    bad_fields.append("phonetic")
                    reasons["phonetic"] = phonetic_reasons

                suspicious_entries.append(
                    {
                        "id": form.id,
                        "guid": form.lemma.guid if form.lemma else None,
                        "lemma_text": form.lemma.lemma_text if form.lemma else None,
                        "derivative_form_text": form.derivative_form_text,
                        "grammatical_form": form.grammatical_form,
                        "language_code": form.language_code,
                        "ipa_pronunciation": ipa_value,
                        "phonetic_pronunciation": phonetic_value,
                        "bad_fields": bad_fields,
                        "reasons": reasons,
                    }
                )

                if fix:
                    form.ipa_pronunciation = None
                    form.phonetic_pronunciation = None
                    fixed_count += 1

            if fix and fixed_count > 0:
                session.commit()

            logger.info(
                f"Found {len(suspicious_entries)} suspicious pronunciation entries "
                f"(out of {len(forms_with_pronunciations)} forms with pronunciations)"
            )

            return {
                "total_checked": len(forms_with_pronunciations),
                "suspicious_count": len(suspicious_entries),
                "fixed_count": fixed_count if fix else 0,
                "suspicious_entries": suspicious_entries,
            }

        except Exception as e:
            logger.error(f"Error checking pronunciation fields: {e}")
            if fix:
                session.rollback()
            return {
                "error": str(e),
                "total_checked": 0,
                "suspicious_count": 0,
                "fixed_count": 0,
                "suspicious_entries": [],
            }
        finally:
            session.close()

    def _get_period_for_language(self, language_code: str) -> str:
        """Return the appropriate period character for a language.

        Args:
            language_code: ISO language code (e.g., 'en', 'zh', 'ja')

        Returns:
            The period character to use ('。' for CJK languages, '.' otherwise)
        """
        # CJK languages use fullwidth period
        if language_code in ("zh", "ja"):
            return "。"
        return "."

    def check_sentence_levels(self, fix: bool = False) -> Dict[str, Any]:
        """Check for sentences with incorrect or missing minimum_level.

        The minimum_level should be:
        - The second-highest word difficulty level if the sentence has 3+ words
        - The highest word difficulty level if the sentence has 1-2 words

        This ensures sentences are shown once most (but not all) words are learned,
        providing some challenge while keeping sentences accessible.

        Args:
            fix: If True, update the minimum_level for sentences with incorrect values
        """
        logger.info("Checking sentence minimum_level values...")

        session = self.get_session()
        try:
            from storage.models.schema import SentencePatternWord

            # Get all non-rejected sentences
            sentences = (
                session.query(Sentence).filter(Sentence.rejected == False).all()  # noqa: E712
            )

            issues: List[Dict[str, Any]] = []
            fixed_count = 0

            for sentence in sentences:
                # Get pattern words with their lemmas' difficulty levels
                pattern_words = (
                    session.query(SentencePatternWord, Lemma)
                    .join(Lemma, SentencePatternWord.lemma_id == Lemma.id)
                    .filter(SentencePatternWord.sentence_id == sentence.id)
                    .all()
                )

                # Collect difficulty levels (skip words without levels)
                # Treat -1 (excluded words) as 21 for sorting purposes
                difficulty_levels = [
                    21 if lemma.difficulty_level == -1 else lemma.difficulty_level
                    for pattern_word, lemma in pattern_words
                    if lemma.difficulty_level is not None
                ]

                if not difficulty_levels:
                    # No words with difficulty levels - skip
                    continue

                # Sort in descending order (21 = excluded words will sort highest)
                difficulty_levels.sort(reverse=True)

                # Calculate expected level
                if len(difficulty_levels) >= 3:
                    # Second-highest level
                    expected_level = difficulty_levels[1]
                else:
                    # Highest level (1 or 2 words)
                    expected_level = difficulty_levels[0]

                # Check if current level matches
                if sentence.minimum_level != expected_level:
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
                        logger.debug(
                            f"Fixed sentence {sentence.id}: "
                            f"{sentence.minimum_level} -> {expected_level}"
                        )

            if fix and fixed_count > 0:
                session.commit()
                logger.info(f"Fixed {fixed_count} sentence levels")

            logger.info(f"Found {len(issues)} sentences with incorrect minimum_level")

            return {
                "issue_count": len(issues),
                "fixed_count": fixed_count if fix else 0,
                "issues": issues,
            }

        except Exception as e:
            logger.error(f"Error checking sentence levels: {e}")
            if fix:
                session.rollback()
            return {
                "error": str(e),
                "issue_count": 0,
                "fixed_count": 0,
                "issues": [],
            }
        finally:
            session.close()

    def check_sentences_missing_punctuation(self, fix: bool = False) -> Dict[str, Any]:
        """Check for sentences that are missing terminal punctuation.

        Sentences should end with a period (. or 。), question mark (? or ？),
        or exclamation mark (! or ！). This check finds sentences that don't
        have any of these terminal punctuation marks.

        Args:
            fix: If True, append the appropriate period to sentences missing punctuation
        """
        logger.info("Checking for sentences missing terminal punctuation...")

        session = self.get_session()
        try:
            # Terminal punctuation for various languages
            terminal_punctuation = ".。?？!！"

            # Get all non-rejected sentences with their translations
            sentences = (
                session.query(Sentence).filter(Sentence.rejected == False).all()  # noqa: E712
            )

            missing_punctuation: List[Dict[str, Any]] = []
            fixed_count = 0

            for sentence in sentences:
                # Get all translations for this sentence
                translations = (
                    session.query(SentenceTranslation)
                    .filter(SentenceTranslation.sentence_id == sentence.id)
                    .all()
                )

                for trans in translations:
                    text = trans.translation_text.strip()
                    if not text:
                        continue

                    # Check if the sentence ends with terminal punctuation
                    if text[-1] not in terminal_punctuation:
                        missing_punctuation.append(
                            {
                                "sentence_id": sentence.id,
                                "translation_id": trans.id,
                                "language_code": trans.language_code,
                                "text": text,
                                "last_char": text[-1] if text else "",
                            }
                        )

                        if fix:
                            period = self._get_period_for_language(trans.language_code)
                            trans.translation_text = text + period
                            fixed_count += 1
                            logger.debug(
                                f"Fixed sentence {sentence.id} ({trans.language_code}): "
                                f"added '{period}'"
                            )

            if fix and fixed_count > 0:
                session.commit()
                logger.info(f"Fixed {fixed_count} sentence translations")

            logger.info(
                f"Found {len(missing_punctuation)} sentence translations missing terminal punctuation"
            )

            # Group by language for summary
            by_language: Dict[str, int] = {}
            for item in missing_punctuation:
                lang = item["language_code"]
                by_language[lang] = by_language.get(lang, 0) + 1

            return {
                "missing_count": len(missing_punctuation),
                "fixed_count": fixed_count if fix else 0,
                "by_language": by_language,
                "missing_punctuation": missing_punctuation,
            }

        except Exception as e:
            logger.error(f"Error checking sentences missing punctuation: {e}")
            if fix:
                session.rollback()
            return {
                "error": str(e),
                "missing_count": 0,
                "fixed_count": 0,
                "by_language": {},
                "missing_punctuation": [],
            }
        finally:
            session.close()

    def check_audio_translation_mismatches(self, fix: bool = False) -> Dict[str, Any]:
        """Check for audio records whose expected_text no longer matches the current translation.

        Compares every AudioQualityReview record's expected_text against the
        translation currently stored in the database for the same
        guid + language_code pair.  Mismatches indicate audio that was generated
        for a previous translation and is now stale.

        Args:
            fix: If True, mark mismatched records as 'needs_replacement' with
                 a 'translation_mismatch' quality issue.
        """
        logger.info("Checking for audio-translation mismatches...")

        session = self.get_session()
        try:
            from storage.models.schema import AudioQualityReview
            from storage.translation_helpers import get_translation

            # Only check lemma audio (guid is set, sentence_id is not)
            audio_records = (
                session.query(AudioQualityReview)
                .filter(
                    AudioQualityReview.guid.isnot(None),
                    AudioQualityReview.sentence_id.is_(None),
                )
                .all()
            )

            mismatches: List[Dict[str, Any]] = []
            fixed_count = 0

            for audio in audio_records:
                lemma = session.query(Lemma).filter_by(guid=audio.guid).first()
                if not lemma:
                    # Orphaned audio record — no matching lemma
                    mismatches.append(
                        {
                            "audio_id": audio.id,
                            "guid": audio.guid,
                            "language_code": audio.language_code,
                            "voice_name": audio.voice_name,
                            "expected_text": audio.expected_text,
                            "current_translation": None,
                            "status": audio.status,
                            "reason": "no_matching_lemma",
                        }
                    )
                    continue

                current_translation = get_translation(session, lemma, audio.language_code)

                if current_translation is None:
                    # Translation was removed entirely
                    mismatches.append(
                        {
                            "audio_id": audio.id,
                            "guid": audio.guid,
                            "lemma_text": lemma.lemma_text,
                            "language_code": audio.language_code,
                            "voice_name": audio.voice_name,
                            "expected_text": audio.expected_text,
                            "current_translation": None,
                            "status": audio.status,
                            "reason": "translation_removed",
                        }
                    )
                elif audio.expected_text != current_translation:
                    mismatches.append(
                        {
                            "audio_id": audio.id,
                            "guid": audio.guid,
                            "lemma_text": lemma.lemma_text,
                            "language_code": audio.language_code,
                            "voice_name": audio.voice_name,
                            "expected_text": audio.expected_text,
                            "current_translation": current_translation,
                            "status": audio.status,
                            "reason": "text_mismatch",
                        }
                    )

                if fix and mismatches and mismatches[-1]["audio_id"] == audio.id:
                    if audio.status != "needs_replacement":
                        import json as _json

                        audio.status = "needs_replacement"
                        existing_issues: List[str] = []
                        if audio.quality_issues:
                            try:
                                existing_issues = _json.loads(audio.quality_issues)
                            except (ValueError, TypeError):
                                existing_issues = []
                        if "translation_mismatch" not in existing_issues:
                            existing_issues.append("translation_mismatch")
                            audio.quality_issues = _json.dumps(existing_issues)
                        fixed_count += 1

            if fix and fixed_count > 0:
                session.commit()
                logger.info(f"Fixed {fixed_count} audio records")

            logger.info(
                f"Found {len(mismatches)} audio-translation mismatches "
                f"out of {len(audio_records)} audio records checked"
            )

            # Group by language for summary
            by_language: Dict[str, int] = {}
            for item in mismatches:
                lang = item["language_code"]
                by_language[lang] = by_language.get(lang, 0) + 1

            return {
                "total_checked": len(audio_records),
                "mismatch_count": len(mismatches),
                "fixed_count": fixed_count if fix else 0,
                "by_language": by_language,
                "mismatches": mismatches,
            }

        except Exception as e:
            logger.error(f"Error checking audio-translation mismatches: {e}")
            if fix:
                session.rollback()
            return {
                "error": str(e),
                "total_checked": 0,
                "mismatch_count": 0,
                "fixed_count": 0,
                "by_language": {},
                "mismatches": [],
            }
        finally:
            session.close()

    def run_full_check(self, output_file: Optional[str] = None) -> Dict[str, Any]:
        """Run all integrity checks and generate a comprehensive report."""
        logger.info("Starting full database integrity check...")
        start_time = datetime.now()

        results: Dict[str, Any] = {
            "timestamp": start_time.isoformat(),
            "database_path": self.db_path,
            "checks": {
                "orphaned_derivative_forms": self.check_orphaned_derivative_forms(),
                "derivative_form_word_tokens": self.check_derivative_form_word_tokens(),
                "orphaned_word_frequencies": self.check_orphaned_word_frequencies(),
                "missing_required_fields": self.check_missing_required_fields(),
                "lemmas_without_derivatives": self.check_lemmas_without_derivatives(),
                "duplicate_guids": self.check_duplicate_guids(),
                "duplicate_words": self.check_duplicate_words(),
                "invalid_difficulty_levels": self.check_invalid_difficulty_levels(),
                "sentences_missing_punctuation": self.check_sentences_missing_punctuation(),
                "sentence_levels": self.check_sentence_levels(),
                "audio_translation_mismatches": self.check_audio_translation_mismatches(),
                "pronunciation_fields": self.check_pronunciation_fields(),
            },
        }

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["duration_seconds"] = duration

        self._print_summary(results, start_time, duration)

        if output_file:
            import json

            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                logger.info(f"Report written to: {output_file}")
            except Exception as e:
                logger.error(f"Failed to write output file: {e}")

        return results

    def _print_summary(
        self, results: Dict[str, Any], start_time: datetime, duration: float
    ) -> None:
        """Print a summary of the check results."""
        logger.info("=" * 80)
        logger.info("BEBRAS INTEGRITY CHECK REPORT")
        logger.info("=" * 80)
        logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("")

        checks = results["checks"]

        logger.info("ORPHANED RECORDS:")
        logger.info(
            f"  Derivative forms (invalid lemma_id): {checks['orphaned_derivative_forms']['orphaned_count']}"
        )
        logger.info(
            f"  Derivative forms (invalid/mismatched word_token): {checks['derivative_form_word_tokens']['issue_count']}"
        )
        logger.info(f"  Word frequencies: {checks['orphaned_word_frequencies']['orphaned_count']}")
        logger.info("")

        missing_fields = checks["missing_required_fields"]
        logger.info("MISSING REQUIRED FIELDS:")
        logger.info(f"  High severity: {missing_fields['high_severity_count']}")
        logger.info(f"  Medium severity: {missing_fields['medium_severity_count']}")
        logger.info("")

        logger.info("LEMMAS WITHOUT DERIVATIVE FORMS:")
        logger.info(f"  Count: {checks['lemmas_without_derivatives']['without_forms_count']}")
        logger.info("")

        logger.info("DUPLICATE GUIDs:")
        logger.info(f"  Count: {checks['duplicate_guids']['duplicate_count']}")
        logger.info("")

        dup_words = checks["duplicate_words"]
        logger.info("DUPLICATE WORDS:")
        logger.info(f"  Groups: {dup_words['duplicate_group_count']}")
        logger.info(f"  Total duplicate lemmas: {dup_words['total_duplicate_lemmas']}")
        logger.info("")

        logger.info("INVALID DIFFICULTY LEVELS:")
        logger.info(f"  Count: {checks['invalid_difficulty_levels']['invalid_count']}")
        logger.info("")

        logger.info("SENTENCES MISSING PUNCTUATION:")
        missing_punct = checks["sentences_missing_punctuation"]
        logger.info(f"  Count: {missing_punct['missing_count']}")
        if missing_punct.get("by_language"):
            for lang, count in sorted(missing_punct["by_language"].items()):
                logger.info(f"    {lang}: {count}")
        logger.info("")

        logger.info("SENTENCE LEVELS:")
        sentence_levels = checks["sentence_levels"]
        logger.info(f"  Incorrect: {sentence_levels['issue_count']}")
        logger.info("")

        audio_mismatches = checks["audio_translation_mismatches"]
        logger.info("AUDIO-TRANSLATION MISMATCHES:")
        logger.info(
            f"  Mismatches: {audio_mismatches['mismatch_count']} "
            f"(out of {audio_mismatches['total_checked']} audio records)"
        )
        if audio_mismatches.get("by_language"):
            for lang, count in sorted(audio_mismatches["by_language"].items()):
                logger.info(f"    {lang}: {count}")
        logger.info("")

        pronunciation_issues = checks["pronunciation_fields"]
        logger.info("PRONUNCIATION FIELD ISSUES:")
        logger.info(
            f"  Suspicious entries: {pronunciation_issues['suspicious_count']} "
            f"(out of {pronunciation_issues['total_checked']} forms with pronunciations)"
        )

        total_issues = (
            checks["orphaned_derivative_forms"]["orphaned_count"]
            + checks["derivative_form_word_tokens"]["issue_count"]
            + checks["orphaned_word_frequencies"]["orphaned_count"]
            + missing_fields["total_issues"]
            + checks["lemmas_without_derivatives"]["without_forms_count"]
            + checks["duplicate_guids"]["duplicate_count"]
            + dup_words["duplicate_group_count"]
            + checks["invalid_difficulty_levels"]["invalid_count"]
            + missing_punct["missing_count"]
            + sentence_levels["issue_count"]
            + audio_mismatches["mismatch_count"]
            + pronunciation_issues["suspicious_count"]
        )

        logger.info("")
        logger.info(f"TOTAL ISSUES FOUND: {total_issues}")
        logger.info("=" * 80)


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(description="Bebras Database Integrity Checker")
    parser.add_argument("--db-path", help="Database path (uses default if not specified)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--output", help="Output JSON file for report")
    parser.add_argument(
        "--check",
        choices=[
            "orphaned",
            "missing-fields",
            "no-derivatives",
            "duplicates",
            "duplicate-words",
            "invalid-levels",
            "missing-punctuation",
            "sentence-levels",
            "audio-mismatches",
            "pronunciation-fields",
            "all",
        ],
        default="all",
        help="Which check to run (default: all)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help=(
            "Fix issues where possible "
            "(missing-punctuation, sentence-levels, audio-mismatches, pronunciation-fields)"
        ),
    )

    return parser


def main() -> None:
    """Main entry point for the integrity checker."""
    parser = get_argument_parser()
    args = parser.parse_args()

    checker = IntegrityChecker(db_path=args.db_path, debug=args.debug)

    if args.check == "orphaned":
        results = {
            "derivative_forms": checker.check_orphaned_derivative_forms(),
            "derivative_form_word_tokens": checker.check_derivative_form_word_tokens(),
            "word_frequencies": checker.check_orphaned_word_frequencies(),
        }
        total = (
            results["derivative_forms"]["orphaned_count"]
            + results["derivative_form_word_tokens"]["issue_count"]
            + results["word_frequencies"]["orphaned_count"]
        )
        print(f"\nTotal orphaned records: {total}")

    elif args.check == "missing-fields":
        results = checker.check_missing_required_fields()
        print(
            f"\nMissing required fields: {results['total_issues']} "
            + f"(High: {results['high_severity_count']}, Medium: {results['medium_severity_count']})"
        )

    elif args.check == "no-derivatives":
        results = checker.check_lemmas_without_derivatives()
        print(
            f"\nLemmas without derivative forms: {results['without_forms_count']} out of {results['total_lemmas']}"
        )

    elif args.check == "duplicates":
        results = checker.check_duplicate_guids()
        print(f"\nDuplicate GUIDs: {results['duplicate_count']}")

    elif args.check == "duplicate-words":
        results = checker.check_duplicate_words()
        print(
            f"\nDuplicate word groups: {results['duplicate_group_count']} "
            f"({results['total_duplicate_lemmas']} total lemmas)"
        )
        dup_list = cast(List[Dict[str, Any]], results.get("duplicates") or [])
        if dup_list:
            print("\nDuplicate groups:")
            for group in dup_list[:20]:
                disambig_str = (
                    f" ({group['disambiguation']})" if group.get("disambiguation") else ""
                )
                print(
                    f"  '{group['lemma_text']}' [{group['pos_type']}]{disambig_str} "
                    f"x{group['count']}:"
                )
                for lem in group["lemmas"]:
                    guid_str = lem["guid"] or "no GUID"
                    print(f"    id={lem['id']} {guid_str}: {lem['definition_text'][:60]}")

    elif args.check == "invalid-levels":
        results = checker.check_invalid_difficulty_levels()
        print(f"\nInvalid difficulty levels: {results['invalid_count']}")

    elif args.check == "missing-punctuation":
        results = checker.check_sentences_missing_punctuation(fix=args.fix)
        print(f"\nSentences missing terminal punctuation: {results['missing_count']}")
        if args.fix:
            print(f"Fixed: {results.get('fixed_count', 0)}")
        if results.get("by_language"):
            for lang, count in sorted(results["by_language"].items()):
                print(f"  {lang}: {count}")
        # Print first few examples (only if not fixing, since text would be pre-fix)
        if not args.fix:
            missing_items = cast(List[Dict[str, Any]], results.get("missing_punctuation") or [])
            if missing_items:
                print("\nExamples:")
                for item in missing_items[:10]:
                    text = str(item.get("text", ""))
                    text_preview = text[:60] + "..." if len(text) > 60 else text
                    print(
                        f"  [{item.get('language_code')}] "
                        f"id={item.get('sentence_id')}: {text_preview}"
                    )

    elif args.check == "sentence-levels":
        results = checker.check_sentence_levels(fix=args.fix)
        print(f"\nSentences with incorrect minimum_level: {results['issue_count']}")
        if args.fix:
            print(f"Fixed: {results.get('fixed_count', 0)}")
        # Print first few examples
        if not args.fix:
            issues = cast(List[Dict[str, Any]], results.get("issues") or [])
            if issues:
                print("\nExamples:")
                for item in issues[:10]:
                    print(
                        f"  id={item.get('sentence_id')}: "
                        f"current={item.get('current_level')} "
                        f"expected={item.get('expected_level')} "
                        f"(words: {item.get('word_count')}, levels: {item.get('difficulty_levels')})"
                    )

    elif args.check == "audio-mismatches":
        results = checker.check_audio_translation_mismatches(fix=args.fix)
        print(
            f"\nAudio-translation mismatches: {results['mismatch_count']} "
            f"(out of {results['total_checked']} audio records)"
        )
        if args.fix:
            print(f"Fixed: {results.get('fixed_count', 0)}")
        if results.get("by_language"):
            for lang, count in sorted(results["by_language"].items()):
                print(f"  {lang}: {count}")
        # Print first few examples
        if not args.fix:
            mismatch_list = cast(List[Dict[str, Any]], results.get("mismatches") or [])
            if mismatch_list:
                print("\nExamples:")
                for item in mismatch_list[:10]:
                    print(
                        f"  [{item.get('language_code')}] "
                        f"{item.get('guid')}: "
                        f"audio={item.get('expected_text')!r} "
                        f"db={item.get('current_translation')!r} "
                        f"({item.get('reason')})"
                    )

    elif args.check == "pronunciation-fields":
        results = checker.check_pronunciation_fields(fix=args.fix)
        print(
            f"\nSuspicious pronunciation entries: {results['suspicious_count']} "
            f"(out of {results['total_checked']} forms with pronunciations)"
        )
        if args.fix:
            print(f"Fixed: {results.get('fixed_count', 0)}")
        suspicious_entries = cast(List[Dict[str, Any]], results.get("suspicious_entries") or [])
        if suspicious_entries:
            print("\nExamples:")
            for item in suspicious_entries[:10]:
                ipa_preview = str(item.get("ipa_pronunciation", ""))
                if len(ipa_preview) > 90:
                    ipa_preview = f"{ipa_preview[:90]}..."
                phonetic_preview = str(item.get("phonetic_pronunciation", ""))
                if len(phonetic_preview) > 90:
                    phonetic_preview = f"{phonetic_preview[:90]}..."
                print(
                    f"  [{item.get('language_code')}] "
                    f"{item.get('guid') or 'no-guid'} "
                    f"{item.get('derivative_form_text')!r}: "
                    f"ipa={ipa_preview!r} "
                    f"phonetic={phonetic_preview!r} "
                    f"bad_fields={item.get('bad_fields')} "
                    f"reasons={item.get('reasons')}"
                )

    else:  # all
        checker.run_full_check(output_file=args.output)


if __name__ == "__main__":
    main()
