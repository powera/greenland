#!/usr/bin/python3

"""Generate data for benchmark 0062 (sentence decomposition) from the database.

This script queries sentences from the linguistics database that have:
- Full sentenceword data (word decomposition with lemma links)
- Translations in at least 3 foreign languages with sentenceword data
- A maximum of 2 sentences per lemma (to avoid over-representation)

The output is suitable for use as samples.json in the benchmark.
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import argparse
import json
import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

DECOMPOSITION_LANGUAGES = {"zh", "lt", "es", "fr"}


def simplify_gloss(gloss: str) -> str:
    """Strip parenthetical annotations and take only the first slash-alternative."""
    gloss = re.sub(r"\s*\([^)]*\)", "", gloss)
    gloss = gloss.split(" / ")[0]
    gloss = gloss.strip()
    if gloss and gloss[0].isupper() and not gloss.isupper():
        gloss = gloss[0].lower() + gloss[1:]
    return gloss


from sqlalchemy import func
from sqlalchemy.orm import joinedload

from storage.backend import create_session
from storage.backend.config import DataSourceConfig, BackendType
from storage.models.schema import (
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_sentences_with_full_sentenceword_data(
    config: DataSourceConfig,
    min_languages: int = 3,
    max_sentences: int = 50,
    max_per_lemma: int = 2,
) -> List[Dict[str, Any]]:
    """Query sentences with full sentenceword data from the database.

    Args:
        config: DataSourceConfig for database access
        min_languages: Minimum number of languages with sentenceword data
        max_sentences: Maximum number of sentences to return
        max_per_lemma: Maximum sentences per lemma (based on English content words)

    Returns:
        List of sentence dictionaries suitable for benchmark 0062
    """
    session = create_session(config)

    try:
        # Query sentences with sentenceword data
        # We'll count how many distinct languages have sentenceword entries
        sentences_query = (
            session.query(Sentence)
            .join(SentenceWord)
            .group_by(Sentence.id)
            .having(func.count(func.distinct(SentenceWord.language_code)) >= min_languages)
            .options(
                joinedload(Sentence.translations),
                joinedload(Sentence.words).joinedload(SentenceWord.lemma),
            )
            .filter(Sentence.rejected == False)
            .order_by(Sentence.id)
        )

        logger.info(
            "Querying sentences with sentenceword data in at least %d languages", min_languages
        )
        all_sentences = sentences_query.all()
        logger.info("Found %d candidate sentences", len(all_sentences))

        # Track lemma usage to limit sentences per lemma
        lemma_counts: Dict[str, int] = defaultdict(int)
        selected_sentences: List[Sentence] = []

        for sentence in all_sentences:
            if len(selected_sentences) >= max_sentences:
                break

            # Get English sentencewords to find content lemmas
            english_words = [
                sw for sw in sentence.words if sw.language_code == "en" and sw.lemma_id is not None
            ]

            # Check if we can add this sentence (based on lemma limits)
            lemma_guids = [sw.lemma.guid for sw in english_words if sw.lemma and sw.lemma.guid]

            # Skip if any lemma is already at max count
            if any(lemma_counts.get(guid, 0) >= max_per_lemma for guid in lemma_guids):
                continue

            # Update lemma counts
            for guid in lemma_guids:
                lemma_counts[guid] = lemma_counts.get(guid, 0) + 1

            selected_sentences.append(sentence)

        logger.info("Selected %d sentences after applying lemma limits", len(selected_sentences))

        # Convert to benchmark format
        result: List[Dict[str, Any]] = []

        for sentence in selected_sentences:
            # Get all translations
            translations_list: List[Dict[str, str]] = []
            for trans in sentence.translations:
                translations_list.append(
                    {
                        "language_code": trans.language_code,
                        "translation": trans.translation_text,
                    }
                )

            # Get languages with sentenceword data
            languages_with_words: Set[str] = set()
            for sw in sentence.words:
                languages_with_words.add(sw.language_code)

            # Only include languages that have sentenceword data
            decomposition_languages: List[Dict[str, Any]] = []

            for lang_code in sorted(languages_with_words & DECOMPOSITION_LANGUAGES):
                # Get sentencewords for this language
                lang_words = [sw for sw in sentence.words if sw.language_code == lang_code]

                # Sort by position
                lang_words.sort(key=lambda sw: sw.position)

                # Get translation text for this language
                translation_text = next(
                    (
                        t.translation_text
                        for t in sentence.translations
                        if t.language_code == lang_code
                    ),
                    "",
                )

                words_list: List[Dict[str, Any]] = []
                for sw in lang_words:
                    word_entry = {
                        "position": sw.position,
                        "role": sw.word_role,
                        "english_gloss": simplify_gloss(sw.english_text or ""),
                        "surface_form": sw.declined_form or sw.target_language_text or "",
                        "grammatical_form": sw.grammatical_form or f"{sw.word_role}/base",
                    }

                    # Add lemma info
                    if sw.lemma and sw.lemma.guid:
                        word_entry["lemma_guid"] = sw.lemma.guid
                        # Format lemma with disambiguation if present
                        lemma_text = sw.lemma.lemma_text
                        if sw.lemma.disambiguation:
                            lemma_text = f"{lemma_text} ({sw.lemma.disambiguation})"
                        word_entry["lemma"] = lemma_text
                    else:
                        word_entry["lemma_guid"] = "NONE"
                        word_entry["lemma"] = "No lemma"

                    words_list.append(word_entry)

                decomposition_languages.append(
                    {
                        "language_code": lang_code,
                        "translation": translation_text,
                        "word_count": len(words_list),
                        "words": words_list,
                    }
                )

            # Skip if not enough languages have decomposition
            if len(decomposition_languages) < min_languages:
                continue

            # Get candidate lemmas (unique lemmas used in this sentence)
            candidate_lemmas: List[Dict[str, Any]] = []
            seen_lemma_guids: Set[str] = set()

            for sw in sentence.words:
                if sw.lemma and sw.lemma.guid and sw.lemma.guid not in seen_lemma_guids:
                    seen_lemma_guids.add(sw.lemma.guid)

                    # Get translations for this lemma
                    lemma_translations: Dict[str, str] = {}

                    # From the lemma_translations table
                    for lt in sw.lemma.translations:
                        if lt.language_code not in lemma_translations:
                            lemma_translations[lt.language_code] = lt.translation

                    candidate_lemmas.append(
                        {
                            "guid": sw.lemma.guid,
                            "lemma": sw.lemma.lemma_text,
                            "disambiguation": sw.lemma.disambiguation or "",
                            "pos": sw.lemma.pos_type,
                            "definition": sw.lemma.definition_text,
                            "translations": lemma_translations,
                        }
                    )

            # Determine source language (assume English for now)
            source_language = "en"
            source_sentence = next(
                (
                    t.translation_text
                    for t in sentence.translations
                    if t.language_code == source_language
                ),
                translations_list[0]["translation"] if translations_list else "",
            )

            result.append(
                {
                    "source_language": source_language,
                    "source_sentence": source_sentence,
                    "translations": translations_list,
                    "decomposition": {
                        "languages": decomposition_languages,
                    },
                    "candidate_lemmas": candidate_lemmas,
                }
            )

        logger.info("Generated %d benchmark samples", len(result))
        return result

    finally:
        session.close()


def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Generate benchmark 0062 data from sentences in the database"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/wordfreq/linguistics.sqlite",
        help="Path to the linguistics database",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="src/benchmarks/0062_sentence_decomposition/samples.json",
        help="Output file path for generated samples",
    )
    parser.add_argument(
        "--min-languages",
        type=int,
        default=3,
        help="Minimum number of languages with sentenceword data (default: 3)",
    )
    parser.add_argument(
        "--max-sentences",
        type=int,
        default=50,
        help="Maximum number of sentences to generate (default: 50)",
    )
    parser.add_argument(
        "--max-per-lemma",
        type=int,
        default=2,
        help="Maximum sentences per lemma (default: 2)",
    )

    args = parser.parse_args()

    # Create config
    config = DataSourceConfig(
        sqlite_path=args.db_path,
        backend_type=BackendType.SQLITE,
    )

    # Generate samples
    samples = get_sentences_with_full_sentenceword_data(
        config=config,
        min_languages=args.min_languages,
        max_sentences=args.max_sentences,
        max_per_lemma=args.max_per_lemma,
    )

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(samples, f, indent=2, ensure_ascii=False)

    logger.info("Wrote %d samples to %s", len(samples), output_path)


if __name__ == "__main__":
    main()
