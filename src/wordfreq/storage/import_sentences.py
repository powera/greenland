#!/usr/bin/python3

"""
Import sentences from JSON files into the database.

Expected JSON format:
{
  "sentences": [
    {
      "english": "I saw the bank.",
      "lithuanian": "Aš mačiau banką.",
      "pattern": "SVO",
      "tense": "past",
      "words_used": [
        {
          "english": "I",
          "lithuanian": "aš",
          "type": "pronoun"
        },
        {
          "english": "see",
          "lithuanian": "matyti",
          "type": "verb",
          "form": "1s_past"
        },
        {
          "english": "bank",
          "lithuanian": "bankas",
          "type": "object",
          "guid": "N07_008",
          "case": "accusative",
          "declined_form": "banką"
        }
      ],
      "filename": "sentence_a1_1"
    }
  ]
}
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from wordfreq.storage.database import create_database_session
from wordfreq.storage.crud.sentence import add_sentence, calculate_minimum_level
from wordfreq.storage.crud.sentence_translation import add_sentence_translation
from wordfreq.storage.crud.sentence_word import add_sentence_word, find_lemma_by_guid

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def import_sentence_from_dict(session, sentence_data: dict, source_file: Optional[str] = None) -> int:
    """
    Import a single sentence from a dictionary.

    Args:
        session: Database session
        sentence_data: Dictionary containing sentence data
        source_file: Optional source filename for tracking

    Returns:
        Sentence ID of the created sentence
    """
    # Extract metadata
    pattern_type = sentence_data.get('pattern')
    tense = sentence_data.get('tense')
    source_filename = sentence_data.get('filename') or source_file

    # Create the sentence
    sentence = add_sentence(
        session=session,
        pattern_type=pattern_type,
        tense=tense,
        source_filename=source_filename,
        verified=False
    )
    logger.debug(f"Created sentence {sentence.id} (pattern={pattern_type}, tense={tense})")

    # Add translations
    translations_added = 0
    for lang_key in ['english', 'lithuanian', 'chinese', 'french', 'spanish', 'german', 'portuguese', 'korean', 'swahili', 'vietnamese']:
        if lang_key in sentence_data and sentence_data[lang_key]:
            # Map full language names to ISO codes
            lang_code_map = {
                'english': 'en',
                'lithuanian': 'lt',
                'chinese': 'zh',
                'french': 'fr',
                'spanish': 'es',
                'german': 'de',
                'portuguese': 'pt',
                'korean': 'ko',
                'swahili': 'sw',
                'vietnamese': 'vi'
            }
            lang_code = lang_code_map.get(lang_key)
            if lang_code:
                add_sentence_translation(
                    session=session,
                    sentence=sentence,
                    language_code=lang_code,
                    translation_text=sentence_data[lang_key],
                    verified=False
                )
                translations_added += 1
                logger.debug(f"  Added {lang_code} translation: {sentence_data[lang_key][:50]}...")

    # Add words
    words_used = sentence_data.get('words_used', [])
    words_linked = 0
    words_unlinked = 0

    for position, word_data in enumerate(words_used):
        # Try to find the lemma by GUID if available
        lemma = None
        guid = word_data.get('guid')
        if guid:
            lemma = find_lemma_by_guid(session, guid)
            if lemma:
                words_linked += 1
                logger.debug(f"  Linked word at position {position} to lemma {guid} ({lemma.lemma_text})")
            else:
                logger.warning(f"  GUID {guid} not found in database for word at position {position}")
                words_unlinked += 1
        else:
            words_unlinked += 1

        # Create the sentence word record
        add_sentence_word(
            session=session,
            sentence=sentence,
            position=position,
            word_role=word_data.get('type', 'unknown'),
            lemma=lemma,
            english_text=word_data.get('english'),
            target_language_text=word_data.get('lithuanian'),  # Could be made dynamic based on target language
            grammatical_form=word_data.get('form'),
            grammatical_case=word_data.get('case'),
            declined_form=word_data.get('declined_form')
        )

    logger.debug(f"  Added {len(words_used)} words ({words_linked} linked to lemmas, {words_unlinked} unlinked)")

    # Calculate minimum difficulty level
    min_level = calculate_minimum_level(session, sentence)
    if min_level is not None:
        logger.info(f"✓ Sentence {sentence.id}: {translations_added} translations, "
                   f"{len(words_used)} words, difficulty level {min_level}")
    else:
        logger.info(f"✓ Sentence {sentence.id}: {translations_added} translations, "
                   f"{len(words_used)} words, no difficulty level (missing word data)")

    return sentence.id


def import_sentences_from_json(session, json_path: str) -> Dict[str, int]:
    """
    Import sentences from a JSON file.

    Args:
        session: Database session
        json_path: Path to JSON file containing sentences

    Returns:
        Dictionary with import statistics
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    logger.info(f"Loading sentences from {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    sentences_data = data.get('sentences', [])
    if not sentences_data:
        logger.warning("No sentences found in JSON file")
        return {'imported': 0, 'failed': 0}

    logger.info(f"Found {len(sentences_data)} sentences to import")

    imported = 0
    failed = 0

    for i, sentence_data in enumerate(sentences_data, 1):
        try:
            sentence_id = import_sentence_from_dict(
                session=session,
                sentence_data=sentence_data,
                source_file=path.stem
            )
            imported += 1

            # Commit after each sentence to avoid losing progress on errors
            session.commit()

        except Exception as e:
            logger.error(f"Failed to import sentence {i}: {e}", exc_info=True)
            session.rollback()
            failed += 1

    logger.info(f"\nImport complete: {imported} imported, {failed} failed")

    return {
        'imported': imported,
        'failed': failed
    }


def import_sentences_from_directory(session, directory_path: str, pattern: str = "*.json") -> Dict[str, int]:
    """
    Import all sentence JSON files from a directory.

    Args:
        session: Database session
        directory_path: Path to directory containing JSON files
        pattern: Glob pattern for files to import (default: "*.json")

    Returns:
        Dictionary with import statistics
    """
    directory = Path(directory_path)
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory_path}")

    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory_path}")

    # Find all matching JSON files
    json_files = list(directory.glob(pattern))

    if not json_files:
        logger.warning(f"No JSON files found in {directory_path} matching pattern {pattern}")
        return {'files': 0, 'imported': 0, 'failed': 0}

    logger.info(f"Found {len(json_files)} JSON files to import")

    total_imported = 0
    total_failed = 0

    for json_file in sorted(json_files):
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing: {json_file.name}")
        logger.info(f"{'='*60}")

        try:
            stats = import_sentences_from_json(session, str(json_file))
            total_imported += stats['imported']
            total_failed += stats['failed']
        except Exception as e:
            logger.error(f"Failed to process file {json_file}: {e}", exc_info=True)

    logger.info(f"\n{'='*60}")
    logger.info(f"Total: {len(json_files)} files, {total_imported} sentences imported, {total_failed} failed")
    logger.info(f"{'='*60}")

    return {
        'files': len(json_files),
        'imported': total_imported,
        'failed': total_failed
    }


def main():
    """Main entry point for sentence import script."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Import sentences from JSON files into the database'
    )
    parser.add_argument(
        'path',
        help='Path to JSON file or directory containing JSON files'
    )
    parser.add_argument(
        '--pattern',
        default='*.json',
        help='Glob pattern for files to import (when path is a directory)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose debug logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    session = create_database_session()

    try:
        path = Path(args.path)

        if path.is_file():
            stats = import_sentences_from_json(session, str(path))
        elif path.is_dir():
            stats = import_sentences_from_directory(session, str(path), args.pattern)
        else:
            logger.error(f"Path not found: {args.path}")
            return 1

        # Report final statistics
        if 'imported' in stats:
            success_rate = stats['imported'] / (stats['imported'] + stats['failed']) * 100 if (stats['imported'] + stats['failed']) > 0 else 0
            logger.info(f"\nSuccess rate: {success_rate:.1f}%")

        return 0

    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
        session.rollback()
        return 1
    finally:
        session.close()


if __name__ == '__main__':
    exit(main())
