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
from storage.backend.config import BackendType, DataSourceConfig
from storage.integrity import IntegrityChecker as StorageIntegrityChecker
from storage.models.schema import DerivativeForm, Lemma

logger = logging.getLogger(__name__)


class _LegacyAudioIntegrityChecker(StorageIntegrityChecker):
    """Legacy audio/pronunciation checks retained until audio is refactored."""

    _PROMPT_LEAK_HINTS: Tuple[str, ...] = (
        "the user wants",
        "i should provide",
        "pronunciation of the word",
        "simplified phonetic representation",
        "ipa pronunciation",
    )

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
            "database_path": self.config.sqlite_path or self.config.postgres_url or "configured",
            "checks": {
                "orphaned_derivative_forms": self.check_orphaned_derivative_forms(),
                "derivative_form_word_tokens": self.check_derivative_form_word_tokens(),
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


class IntegrityChecker(_LegacyAudioIntegrityChecker):
    """Compatibility facade combining canonical checks with legacy audio checks."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        debug: bool = False,
        config: Optional[DataSourceConfig] = None,
    ) -> None:
        resolved_config = config or DataSourceConfig(
            backend_type=BackendType.SQLITE,
            sqlite_path=db_path or constants.WORDFREQ_DB_PATH,
            debug=debug,
        )
        StorageIntegrityChecker.__init__(self, resolved_config)
        self.db_path = resolved_config.sqlite_path or resolved_config.postgres_url or "configured"
        self.debug = debug or resolved_config.debug


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
        }
        total = (
            results["derivative_forms"]["orphaned_count"]
            + results["derivative_form_word_tokens"]["issue_count"]
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
