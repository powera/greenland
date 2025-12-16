#!/usr/bin/env python3
"""
WireWord sentences exporter for pattern-based simple sentences.

This module exports pattern-generated sentences to JSON format for the
Trakaido language learning app.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
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
from wordfreq.patterns.simple_patterns import SIMPLE_PATTERNS

# Configure logging
logger = logging.getLogger(__name__)


class WirewordSentenceExporter:
    """Exporter for pattern sentences in WireWord format."""

    def __init__(
        self,
        db_path: str = None,
        debug: bool = False,
        language: str = "lt",
    ):
        """
        Initialize the WirewordSentenceExporter.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
            language: Target language code ('lt', 'zh', etc.)
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.language = language

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def get_audio_for_sentence(self, session, sentence: Sentence, language_code: str) -> Dict[str, str]:
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

    def export_pattern_sentences(
        self, pattern_id: Optional[str] = None, include_all_languages: bool = True
    ) -> Dict[str, Any]:
        """
        Export pattern sentences to wireword format.

        Args:
            pattern_id: Optional specific pattern to export (None for all)
            include_all_languages: Include all translations (default: True)

        Returns:
            Dictionary with exported sentence data
        """
        session = self.get_session()
        try:
            # Build query
            query = session.query(Sentence).filter(Sentence.source_filename.like("pattern:%"))

            # Filter by pattern if specified
            if pattern_id:
                query = query.filter(Sentence.source_filename == f"pattern:{pattern_id}")

            sentences = query.all()
            logger.info(f"Exporting {len(sentences)} pattern sentences")

            # Build output structure
            output = {
                "language": self.language,
                "generated_date": datetime.now().isoformat(),
                "pattern_sentences": [],
            }

            for sentence in sentences:
                # Extract pattern_id from source_filename
                source_pattern_id = sentence.source_filename.replace("pattern:", "")

                # Get all translations
                translations = {}
                for trans in sentence.translations:
                    translations[trans.language_code] = trans.translation_text

                # Filter to only include requested language + English
                if not include_all_languages:
                    filtered_translations = {"en": translations.get("en", "")}
                    if self.language != "en" and self.language in translations:
                        filtered_translations[self.language] = translations[self.language]
                    translations = filtered_translations

                # Get audio for target language
                audio_dict = self.get_audio_for_sentence(session, sentence, self.language)

                # Get linked words (GUIDs)
                linked_words = []
                sentence_words = (
                    session.query(SentenceWord)
                    .filter_by(sentence_id=sentence.id)
                    .filter(SentenceWord.lemma_id.isnot(None))
                    .all()
                )

                # Deduplicate by lemma (same word may appear in multiple languages)
                seen_lemmas = set()
                for sw in sentence_words:
                    if sw.lemma and sw.lemma.guid and sw.lemma.id not in seen_lemmas:
                        seen_lemmas.add(sw.lemma.id)
                        linked_words.append(
                            {
                                "guid": sw.lemma.guid,
                                "en": sw.lemma.lemma_text,
                                "role": sw.word_role,
                            }
                        )

                # Build sentence entry
                sentence_entry = {
                    "pattern_id": source_pattern_id,
                    "sentence_id": sentence.id,
                    "translations": translations,
                    "linked_words": linked_words,
                }

                # Only include audio if present
                if audio_dict:
                    sentence_entry["audio"] = audio_dict

                output["pattern_sentences"].append(sentence_entry)

            return output

        finally:
            session.close()

    def export_to_file(
        self,
        output_path: str,
        pattern_id: Optional[str] = None,
        include_all_languages: bool = True,
    ) -> int:
        """
        Export pattern sentences to a JSON file.

        Args:
            output_path: Path to output JSON file
            pattern_id: Optional specific pattern to export
            include_all_languages: Include all translations

        Returns:
            Number of sentences exported
        """
        data = self.export_pattern_sentences(
            pattern_id=pattern_id, include_all_languages=include_all_languages
        )

        # Create output directory if needed
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        sentence_count = len(data["pattern_sentences"])
        logger.info(f"Exported {sentence_count} sentences to {output_path}")

        return sentence_count

    def export_by_pattern(self, output_dir: str) -> Dict[str, int]:
        """
        Export sentences grouped by pattern to separate files.

        Args:
            output_dir: Directory to write pattern files

        Returns:
            Dictionary mapping pattern_id to sentence count
        """
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        results = {}

        for pattern in SIMPLE_PATTERNS:
            pattern_id = pattern["pattern_id"]
            output_file = output_dir_path / f"pattern_{pattern_id}.json"

            count = self.export_to_file(
                output_path=str(output_file), pattern_id=pattern_id, include_all_languages=True
            )

            results[pattern_id] = count
            logger.info(f"Exported pattern {pattern_id}: {count} sentences")

        return results


def main():
    """CLI entry point for wireword sentence export."""
    import argparse

    parser = argparse.ArgumentParser(description="Export pattern sentences to wireword format")
    parser.add_argument(
        "--db-path", help="Database path (uses default if not specified)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--language",
        default="lt",
        choices=["lt", "zh", "ko", "fr", "de", "es", "pt"],
        help="Target language (default: lt)",
    )
    parser.add_argument(
        "--output", required=True, help="Output file or directory path"
    )
    parser.add_argument(
        "--pattern", help="Export only specific pattern (default: all patterns)"
    )
    parser.add_argument(
        "--by-pattern",
        action="store_true",
        help="Export each pattern to a separate file (output is directory)",
    )

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
    if args.by_pattern:
        results = exporter.export_by_pattern(args.output)
        total = sum(results.values())
        logger.info("=" * 60)
        logger.info("EXPORT COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total sentences exported: {total}")
        logger.info(f"Patterns: {len(results)}")
        logger.info(f"Output directory: {args.output}")
    else:
        count = exporter.export_to_file(
            output_path=args.output, pattern_id=args.pattern, include_all_languages=True
        )
        logger.info("=" * 60)
        logger.info("EXPORT COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Sentences exported: {count}")
        logger.info(f"Output file: {args.output}")


if __name__ == "__main__":
    main()
