#!/usr/bin/env python3
"""
WireWord sentences exporter for Trakaido app.

This module exports sentences to JSON format for the Trakaido language learning app.
Exports all sentences with level != -1 that have a translation in the target language.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from barsukas.config import Config
import constants
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import create_session
from storage.models.enums import GrammaticalForm
from storage.models.schema import (
    AudioQualityReview,
    ConversationSentence,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from langtools.zh.converter import to_simplified
from langtools.zh.pinyin_helper import generate_pinyin

# Configure logging
logger = logging.getLogger(__name__)


class WirewordSentenceExporter:
    """Exporter for sentences in WireWord format."""

    def __init__(
        self,
        config: Optional[DataSourceConfig] = None,
        debug: bool = False,
        language: str = "lt",
        simplified_chinese: bool = True,
        include_unreviewed_audio: bool = False,
        source_language: str = "en",
    ):
        """
        Initialize the WirewordSentenceExporter.

        Args:
            config: DataSourceConfig with backend settings (uses default SQLite if None)
            debug: Enable debug logging
            language: Target language code ('lt', 'zh', etc.)
            simplified_chinese: If True and language is 'zh', convert to Simplified Chinese (default: True)
            include_unreviewed_audio: If True, include audio that exists in staging but hasn't been
                reviewed yet.
            source_language: Source language code (default: 'en'). The language the learner already
                knows. When not 'en', source language translations are included instead of English.
        """
        # Use provided config or create default SQLite config
        if config is None:
            config = DataSourceConfig(backend_type=BackendType.SQLITE)
        self.config = config
        self.debug = debug
        self.language = language
        self.simplified_chinese = simplified_chinese
        self.include_unreviewed_audio = include_unreviewed_audio
        self.source_language = source_language

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        """Get database session."""
        return create_session(self.config)

    def get_audio_for_sentence(
        self, session: Any, sentence: Sentence, language_code: str
    ) -> Dict[str, str]:
        """
        Get audio MD5 hashes for a sentence in a specific language.

        Args:
            session: Database session
            sentence: Sentence object
            language_code: Language code

        Returns:
            Dictionary mapping voice names to MD5 hashes
        """
        # Get translation text for this sentence
        translation = (
            session.query(SentenceTranslation)
            .filter_by(sentence_id=sentence.id, language_code=language_code)
            .first()
        )

        if not translation:
            return {}

        # Query audio records by text matching
        # Note: This assumes audio has been generated with expected_text matching the sentence
        audio_records = (
            session.query(AudioQualityReview)
            .filter(
                AudioQualityReview.expected_text == translation.translation_text,
                AudioQualityReview.language_code == language_code,
                AudioQualityReview.status.in_(["approved", "pending_review"]),
            )
            .all()
        )

        # Build voice -> MD5 mapping
        audio_dict = {}
        for record in audio_records:
            if record.voice_name and record.manifest_md5:
                audio_dict[record.voice_name] = record.manifest_md5

        return audio_dict

    def export_sentences(
        self,
        include_all_languages: bool = False,
        exclude_conversation_sentences: bool = True,
    ) -> Dict[str, Any]:
        """
        Export sentences to wireword format.

        Exports all sentences where:
        - minimum_level is not -1 (i.e., not excluded; NULL/None is OK)
        - A translation exists for the target language
        - Not part of a conversation (if exclude_conversation_sentences=True)

        Optimized for remote databases: uses bulk queries to minimize round trips.

        Args:
            include_all_languages: Include all translations (default: False, only target + English)
            exclude_conversation_sentences: Exclude sentences that are part of conversations
                (default: True). These are exported separately in wireword_conversations.jsonl.

        Returns:
            Dictionary with exported sentence data
        """
        from sqlalchemy.orm import joinedload

        session = self.get_session()
        try:
            # Build query: get all sentences
            # OPTIMIZATION: Eager load translations to avoid N+1 queries
            query = session.query(Sentence).options(joinedload(Sentence.translations))

            all_sentences = query.all()
            logger.info(f"Found {len(all_sentences)} sentences")

            # Optionally exclude sentences that are part of conversations
            if exclude_conversation_sentences:
                conversation_sentence_ids = set(
                    row[0]
                    for row in session.query(ConversationSentence.sentence_id).distinct().all()
                )
                original_count = len(all_sentences)
                all_sentences = [s for s in all_sentences if s.id not in conversation_sentence_ids]
                excluded_count = original_count - len(all_sentences)
                if excluded_count > 0:
                    logger.info(
                        f"Excluded {excluded_count} sentences that are part of conversations"
                    )

            # Filter to only sentences that have a translation in the target language
            sentences = []
            for sentence in all_sentences:
                has_target_translation = any(
                    trans.language_code == self.language for trans in sentence.translations
                )
                if has_target_translation:
                    sentences.append(sentence)

            logger.info(f"Exporting {len(sentences)} sentences with {self.language} translation")

            # OPTIMIZATION: Bulk fetch all sentence words for all sentences in one query
            sentence_ids = [s.id for s in sentences]
            all_sentence_words = (
                session.query(SentenceWord)
                .options(joinedload(SentenceWord.lemma))
                .filter(
                    SentenceWord.sentence_id.in_(sentence_ids),
                    SentenceWord.language_code == self.language,
                    SentenceWord.lemma_id.isnot(None),
                )
                .all()
            )
            # Index by sentence_id for quick lookup
            sentence_words_by_sentence: Dict[int, List[SentenceWord]] = {}
            for sw in all_sentence_words:
                if sw.sentence_id not in sentence_words_by_sentence:
                    sentence_words_by_sentence[sw.sentence_id] = []
                sentence_words_by_sentence[sw.sentence_id].append(sw)
            logger.info(f"Bulk fetched {len(all_sentence_words)} sentence words")

            # OPTIMIZATION: Bulk fetch audio records for all sentences
            # Get translation texts for all sentences to match against audio
            target_translations = {}
            for sentence in sentences:
                for trans in sentence.translations:
                    if trans.language_code == self.language:
                        target_translations[sentence.id] = trans.translation_text
                        break

            translation_texts = list(target_translations.values())
            all_audio_records = (
                session.query(AudioQualityReview)
                .filter(
                    AudioQualityReview.expected_text.in_(translation_texts),
                    AudioQualityReview.language_code == self.language,
                )
                .all()
            )
            # Index by expected_text for quick lookup
            audio_by_text: Dict[str, Dict[str, str]] = {}
            for record in all_audio_records:
                # Always exclude rejected audio
                if record.status == "needs_replacement":
                    continue

                # Include if in production OR (if flag is True and in staging)
                if record.s3_prod_url or (self.include_unreviewed_audio and record.s3_staging_url):
                    if record.voice_name and record.manifest_md5:
                        if record.expected_text not in audio_by_text:
                            audio_by_text[record.expected_text] = {}
                        audio_by_text[record.expected_text][record.voice_name] = record.manifest_md5
            logger.info(f"Bulk fetched {len(all_audio_records)} audio records")

            # Build output structure
            # Note: No generated_date here - that belongs in the manifest file only,
            # so the MD5 checksum stays stable when content hasn't changed.
            output: Dict[str, Any] = {
                "language": self.language,
                "sentences": [],
            }
            if self.source_language != "en":
                output["source_language"] = self.source_language

            skipped_no_source = 0
            for sentence in sentences:
                # Get all translations (already loaded via joinedload)
                translations = {}
                for trans in sentence.translations:
                    translation_text = trans.translation_text
                    # Convert Chinese to simplified if needed
                    if (
                        trans.language_code == "zh"
                        and self.language == "zh"
                        and self.simplified_chinese
                    ):
                        translation_text = to_simplified(translation_text)
                    translations[trans.language_code] = translation_text

                # Skip sentences missing a source language translation
                if self.source_language != "en" and not translations.get(self.source_language):
                    skipped_no_source += 1
                    continue

                # Filter to only include requested language + source language
                if not include_all_languages:
                    filtered_translations = {
                        self.source_language: translations.get(self.source_language, "")
                    }
                    if self.language != self.source_language and self.language in translations:
                        filtered_translations[self.language] = translations[self.language]
                    translations = filtered_translations

                # Get audio for target language from pre-fetched data
                target_text = target_translations.get(sentence.id)
                audio_dict = audio_by_text.get(target_text, {}) if target_text else {}

                # Get linked words from pre-fetched data
                linked_words = []
                sentence_words = sentence_words_by_sentence.get(sentence.id, [])

                # Deduplicate by lemma + grammatical form (same word may appear multiple times)
                seen_forms: Set[Tuple[int, Optional[str]]] = set()
                for sw in sentence_words:
                    if not (sw.lemma and sw.lemma.guid):
                        continue

                    grammatical_form = self._get_sentence_word_grammatical_form(sw)
                    key = (sw.lemma.id, grammatical_form)

                    if key in seen_forms:
                        continue

                    seen_forms.add(key)
                    linked_words.append(
                        {
                            "guid": sw.lemma.guid,
                            "grammatical_form": grammatical_form,
                        }
                    )

                # Build sentence entry
                sentence_entry: Dict[str, Any] = {
                    "sentence_id": f"S_{sentence.id:05d}",
                    "translations": translations,
                    "linked_words": linked_words,
                }

                # Add pinyin for Chinese translations (inside translations dict
                # so apps can access it as translations["pinyin"])
                if self.language == "zh" and self.language in translations:
                    pinyin = generate_pinyin(translations[self.language])
                    if pinyin:
                        translations["pinyin"] = pinyin

                # Include optional metadata
                if sentence.source_filename:
                    sentence_entry["source"] = sentence.source_filename
                # TODO: Remove level=21 fallback once wireword consumers no longer require
                # minimum_level field. Currently they compute sentence levels from word levels.
                if sentence.minimum_level is not None and sentence.minimum_level != -1:
                    sentence_entry["minimum_level"] = sentence.minimum_level
                else:
                    sentence_entry["minimum_level"] = Config.MAX_DIFFICULTY_LEVEL + 1

                # Only include audio if present
                if audio_dict:
                    sentence_entry["audio"] = audio_dict

                output["sentences"].append(sentence_entry)

            if skipped_no_source > 0:
                logger.info(
                    f"Skipped {skipped_no_source} sentences missing "
                    f"{self.source_language} translation"
                )

            return output

        finally:
            session.close()

    def export_to_file(
        self,
        output_path: str,
        include_all_languages: bool = False,
        exclude_conversation_sentences: bool = True,
    ) -> int:
        """Export sentences to a JSON file.

        Args:
            output_path: Path to output JSON file
            include_all_languages: Include all translations
            exclude_conversation_sentences: Exclude sentences that are part of conversations
                (default: True). These are exported separately in wireword_conversations.jsonl.

        Returns:
            Number of sentences exported
        """
        data = self.export_sentences(
            include_all_languages=include_all_languages,
            exclude_conversation_sentences=exclude_conversation_sentences,
        )

        # Create output directory if needed
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        sentence_count = len(data["sentences"])
        logger.info(f"Exported {sentence_count} sentences to {output_path}")

        return sentence_count

    def _get_sentence_word_grammatical_form(self, sentence_word: SentenceWord) -> Optional[str]:
        """Return the WireWord grammatical form value for a sentence word.

        Prefers the stored grammatical_form when it matches an existing
        GrammaticalForm enum value used by wireword nouns/verbs exports. Falls
        back to None if no compatible form is available.
        """
        grammatical_form: Optional[str] = sentence_word.grammatical_form
        if grammatical_form and grammatical_form in GrammaticalForm._value2member_map_:
            return grammatical_form

        return None


def main() -> None:
    """CLI entry point for wireword sentence export."""
    import argparse

    from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config

    parser = argparse.ArgumentParser(description="Export sentences to wireword format")
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument(
        "--language",
        default="lt",
        choices=["lt", "zh", "ko", "fr", "de", "es", "pt"],
        help="Target language (default: lt)",
    )
    parser.add_argument("--output", required=True, help="Output file path")

    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create config from args
    config = get_data_source_config(args)

    # Create exporter
    exporter = WirewordSentenceExporter(config=config, debug=args.debug, language=args.language)

    # Export
    count = exporter.export_to_file(output_path=args.output, include_all_languages=False)
    logger.info("=" * 60)
    logger.info("EXPORT COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Sentences exported: {count}")
    logger.info(f"Output file: {args.output}")


if __name__ == "__main__":
    main()
