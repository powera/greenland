#!/usr/bin/env python3
"""
WireWord conversations exporter for Trakaido app.

This module exports conversations to JSONL format for the Trakaido language learning app.
Each line is a complete conversation with ordered sentences and speaker attribution.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.backend.factory import create_session
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.storage.models.schema import (
    AudioQualityReview,
    Conversation,
    ConversationSentence,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from langtools.zh.converter import to_simplified
from langtools.zh.pinyin_helper import generate_pinyin

# Configure logging
logger = logging.getLogger(__name__)


class WirewordConversationExporter:
    """Exporter for conversations in WireWord JSONL format."""

    def __init__(
        self,
        config: Optional[DataSourceConfig] = None,
        debug: bool = False,
        language: str = "lt",
        simplified_chinese: bool = True,
    ):
        """
        Initialize the WirewordConversationExporter.

        Args:
            config: DataSourceConfig with backend settings (uses default SQLite if None)
            debug: Enable debug logging
            language: Target language code ('lt', 'zh', etc.)
            simplified_chinese: If True and language is 'zh', convert to Simplified Chinese
        """
        # Use provided config or create default SQLite config
        if config is None:
            config = DataSourceConfig(backend_type=BackendType.SQLITE)
        self.config = config
        self.debug = debug
        self.language = language
        self.simplified_chinese = simplified_chinese

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        """Get database session."""
        return create_session(self.config)

    def export_conversations(self, include_all_languages: bool = False) -> List[Dict[str, Any]]:
        """
        Export conversations to wireword format.

        Exports all non-rejected conversations where:
        - A translation exists for the target language in at least one sentence

        Optimized for remote databases: uses bulk queries to minimize round trips.

        Args:
            include_all_languages: Include all translations (default: False, only target + English)

        Returns:
            List of conversation dictionaries
        """
        from sqlalchemy.orm import joinedload

        session = self.get_session()
        try:
            # Query non-rejected conversations with eager loading
            conversations = (
                session.query(Conversation)
                .filter(Conversation.rejected == False)  # noqa: E712
                .options(
                    joinedload(Conversation.conversation_sentences)
                    .joinedload(ConversationSentence.sentence)
                    .joinedload(Sentence.translations)
                )
                .all()
            )
            logger.info(f"Found {len(conversations)} non-rejected conversations")

            # Filter to only conversations that have target language translations
            filtered_conversations = []
            for conv in conversations:
                has_target_translation = False
                for cs in conv.conversation_sentences:
                    if any(t.language_code == self.language for t in cs.sentence.translations):
                        has_target_translation = True
                        break
                if has_target_translation:
                    filtered_conversations.append(conv)

            logger.info(
                f"Exporting {len(filtered_conversations)} conversations with {self.language} translation"
            )

            # Collect all sentence IDs for bulk queries
            all_sentence_ids: Set[int] = set()
            for conv in filtered_conversations:
                for cs in conv.conversation_sentences:
                    all_sentence_ids.add(cs.sentence_id)

            # OPTIMIZATION: Bulk fetch sentence words for all sentences
            all_sentence_words = (
                session.query(SentenceWord)
                .options(joinedload(SentenceWord.lemma))
                .filter(
                    SentenceWord.sentence_id.in_(all_sentence_ids),
                    SentenceWord.language_code == self.language,
                    SentenceWord.lemma_id.isnot(None),
                )
                .all()
            )
            sentence_words_by_sentence: Dict[int, List[SentenceWord]] = {}
            for sw in all_sentence_words:
                if sw.sentence_id not in sentence_words_by_sentence:
                    sentence_words_by_sentence[sw.sentence_id] = []
                sentence_words_by_sentence[sw.sentence_id].append(sw)
            logger.info(f"Bulk fetched {len(all_sentence_words)} sentence words")

            # OPTIMIZATION: Bulk fetch audio records for target language sentences
            # First collect all translation texts
            translation_texts_by_sentence: Dict[int, str] = {}
            for conv in filtered_conversations:
                for cs in conv.conversation_sentences:
                    for trans in cs.sentence.translations:
                        if trans.language_code == self.language:
                            translation_texts_by_sentence[cs.sentence_id] = trans.translation_text
                            break

            translation_texts = list(translation_texts_by_sentence.values())
            all_audio_records = (
                session.query(AudioQualityReview)
                .filter(
                    AudioQualityReview.expected_text.in_(translation_texts),
                    AudioQualityReview.language_code == self.language,
                    AudioQualityReview.status.in_(["approved", "pending_review"]),
                )
                .all()
            )
            audio_by_text: Dict[str, Dict[str, str]] = {}
            for record in all_audio_records:
                if record.voice_name and record.manifest_md5:
                    if record.expected_text not in audio_by_text:
                        audio_by_text[record.expected_text] = {}
                    audio_by_text[record.expected_text][record.voice_name] = record.manifest_md5
            logger.info(f"Bulk fetched {len(all_audio_records)} audio records")

            # Build output list
            output = []

            for conv in filtered_conversations:
                # Sort sentences by position
                sorted_sentences = sorted(conv.conversation_sentences, key=lambda cs: cs.position)

                conversation_entry: Dict[str, Any] = {
                    "conversation_id": conv.id,
                    "sentences": [],
                }

                # Add optional metadata
                if conv.title:
                    conversation_entry["title"] = conv.title
                if conv.theme:
                    conversation_entry["theme"] = conv.theme
                if conv.minimum_level is not None:
                    conversation_entry["minimum_level"] = conv.minimum_level

                for cs in sorted_sentences:
                    sentence = cs.sentence

                    # Build translations dict
                    translations = {}
                    for trans in sentence.translations:
                        translation_text = trans.translation_text
                        if (
                            trans.language_code == "zh"
                            and self.language == "zh"
                            and self.simplified_chinese
                        ):
                            translation_text = to_simplified(translation_text)
                        translations[trans.language_code] = translation_text

                    # Filter to requested languages
                    if not include_all_languages:
                        filtered_translations = {"en": translations.get("en", "")}
                        if self.language != "en" and self.language in translations:
                            filtered_translations[self.language] = translations[self.language]
                        translations = filtered_translations

                    # Get audio from pre-fetched data
                    target_text = translation_texts_by_sentence.get(sentence.id)
                    audio_dict = audio_by_text.get(target_text, {}) if target_text else {}

                    # Get linked words from pre-fetched data
                    linked_words = []
                    sentence_words = sentence_words_by_sentence.get(sentence.id, [])

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
                        "sentence_id": sentence.id,
                        "position": cs.position,
                        "speaker": cs.speaker,
                        "translations": translations,
                        "linked_words": linked_words,
                    }

                    # Add pinyin for Chinese translations
                    if self.language == "zh" and self.language in translations:
                        pinyin = generate_pinyin(translations[self.language])
                        if pinyin:
                            sentence_entry["pinyin"] = pinyin

                    if sentence.minimum_level is not None:
                        sentence_entry["minimum_level"] = sentence.minimum_level

                    if audio_dict:
                        sentence_entry["audio"] = audio_dict

                    conversation_entry["sentences"].append(sentence_entry)

                output.append(conversation_entry)

            return output

        finally:
            session.close()

    def export_to_file(
        self,
        output_path: str,
        include_all_languages: bool = False,
    ) -> int:
        """Export conversations to a JSONL file.

        Args:
            output_path: Path to output JSONL file
            include_all_languages: Include all translations

        Returns:
            Number of conversations exported
        """
        conversations = self.export_conversations(include_all_languages=include_all_languages)

        # Create output directory if needed
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Write to JSONL file (one JSON object per line)
        with open(output_path, "w", encoding="utf-8") as f:
            for conv in conversations:
                f.write(json.dumps(conv, ensure_ascii=False) + "\n")

        conversation_count = len(conversations)
        logger.info(f"Exported {conversation_count} conversations to {output_path}")

        return conversation_count

    def _get_sentence_word_grammatical_form(self, sentence_word: SentenceWord) -> Optional[str]:
        """Return the WireWord grammatical form value for a sentence word."""
        grammatical_form: Optional[str] = sentence_word.grammatical_form
        if grammatical_form and grammatical_form in GrammaticalForm._value2member_map_:
            return grammatical_form

        return None


def main() -> None:
    """CLI entry point for wireword conversation export."""
    import argparse

    from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config

    parser = argparse.ArgumentParser(description="Export conversations to wireword JSONL format")
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
    exporter = WirewordConversationExporter(config=config, debug=args.debug, language=args.language)

    # Export
    count = exporter.export_to_file(output_path=args.output, include_all_languages=False)
    logger.info("=" * 60)
    logger.info("EXPORT COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Conversations exported: {count}")
    logger.info(f"Output file: {args.output}")


if __name__ == "__main__":
    main()
