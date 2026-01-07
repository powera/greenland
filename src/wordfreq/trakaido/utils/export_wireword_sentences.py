#!/usr/bin/env python3
"""
WireWord sentences exporter for Trakaido app.

This module exports sentences to JSON format for the Trakaido language learning app.
Exports all sentences with level != -1 that have a translation in the target language.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
import sys

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import (
    Sentence,
    SentenceTranslation,
    SentenceWord,
    AudioQualityReview,
)
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.tools.chinese_converter import to_simplified

# Configure logging
logger = logging.getLogger(__name__)


class WirewordSentenceExporter:
    """Exporter for sentences in WireWord format."""

    def __init__(
        self,
        db_path: str = None,
        debug: bool = False,
        language: str = "lt",
        simplified_chinese: bool = True,
    ):
        """
        Initialize the WirewordSentenceExporter.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
            language: Target language code ('lt', 'zh', etc.)
            simplified_chinese: If True and language is 'zh', convert to Simplified Chinese (default: True)
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.language = language
        self.simplified_chinese = simplified_chinese

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def get_audio_for_sentence(
        self, session, sentence: Sentence, language_code: str
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

    def export_sentences(self, include_all_languages: bool = False) -> Dict[str, Any]:
        """
        Export sentences to wireword format.

        Exports all sentences where:
        - minimum_level is not -1 (i.e., not excluded; NULL/None is OK)
        - A translation exists for the target language

        Args:
            include_all_languages: Include all translations (default: False, only target + English)

        Returns:
            Dictionary with exported sentence data
        """
        session = self.get_session()
        try:
            # Build query: get all sentences EXCEPT those with level = -1
            # This includes NULL/None levels
            query = session.query(Sentence).filter(
                (Sentence.minimum_level != -1) | (Sentence.minimum_level == None)
            )

            all_sentences = query.all()
            logger.info(f"Found {len(all_sentences)} sentences (excluding level = -1)")

            # Filter to only sentences that have a translation in the target language
            sentences = []
            for sentence in all_sentences:
                has_target_translation = any(
                    trans.language_code == self.language for trans in sentence.translations
                )
                if has_target_translation:
                    sentences.append(sentence)

            logger.info(f"Exporting {len(sentences)} sentences with {self.language} translation")

            # Build output structure
            output = {
                "language": self.language,
                "generated_date": datetime.now().isoformat(),
                "sentences": [],
            }

            for sentence in sentences:
                # Get all translations
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

                # Filter to only include requested language + English
                if not include_all_languages:
                    filtered_translations = {"en": translations.get("en", "")}
                    if self.language != "en" and self.language in translations:
                        filtered_translations[self.language] = translations[self.language]
                    translations = filtered_translations

                # Get audio for target language (optional)
                audio_dict = self.get_audio_for_sentence(session, sentence, self.language)

                # Get linked words (GUIDs) for the target language only
                linked_words = []
                sentence_words = (
                    session.query(SentenceWord)
                    .filter_by(sentence_id=sentence.id, language_code=self.language)
                    .filter(SentenceWord.lemma_id.isnot(None))
                    .all()
                )

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
                sentence_entry = {
                    "sentence_id": sentence.id,
                    "translations": translations,
                    "linked_words": linked_words,
                }

                # Include optional metadata
                if sentence.source_filename:
                    sentence_entry["source"] = sentence.source_filename
                if sentence.minimum_level is not None:
                    sentence_entry["minimum_level"] = sentence.minimum_level

                # Only include audio if present
                if audio_dict:
                    sentence_entry["audio"] = audio_dict

                output["sentences"].append(sentence_entry)

            return output

        finally:
            session.close()

    def export_to_file(
        self,
        output_path: str,
        include_all_languages: bool = False,
    ) -> int:
        """
        Export sentences to a JSON file.

        Args:
            output_path: Path to output JSON file
            include_all_languages: Include all translations

        Returns:
            Number of sentences exported
        """
        data = self.export_sentences(include_all_languages=include_all_languages)

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

        grammatical_form = sentence_word.grammatical_form
        if grammatical_form and grammatical_form in GrammaticalForm._value2member_map_:
            return grammatical_form

        return None


def main():
    """CLI entry point for wireword sentence export."""
    import argparse

    parser = argparse.ArgumentParser(description="Export sentences to wireword format")
    parser.add_argument("--db-path", help="Database path (uses default if not specified)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
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

    # Create exporter
    exporter = WirewordSentenceExporter(
        db_path=args.db_path, debug=args.debug, language=args.language
    )

    # Export
    count = exporter.export_to_file(output_path=args.output, include_all_languages=False)
    logger.info("=" * 60)
    logger.info("EXPORT COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Sentences exported: {count}")
    logger.info(f"Output file: {args.output}")


if __name__ == "__main__":
    main()
