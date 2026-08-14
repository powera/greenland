"""Report high-frequency English words that are absent from the dictionary."""

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend import create_session
from storage.models.schema import ExternalLexemeAnnotation, Lemma, WordToken
from storage.queries.lemma import filter_existing_english_words
from util.stopwords import (
    COMMON_ADVERBS,
    COMMON_NOUNS,
    COMMON_VERBS,
    CONTRACTIONS,
    MISC_WORDS,
    all_stopwords,
)

logger = logging.getLogger(__name__)


def is_valid_frequency_candidate(word: str) -> bool:
    """Return whether a corpus token is worth reporting as a missing word."""
    word_lower = word.lower()
    if word_lower in all_stopwords:
        return False
    if word_lower in COMMON_VERBS:
        return False
    if word_lower in COMMON_NOUNS:
        return False
    if word_lower in COMMON_ADVERBS:
        return False
    if word_lower in MISC_WORDS:
        return False
    if word in CONTRACTIONS:
        return False
    if not any(character.isalpha() for character in word):
        return False
    if len(word) < 2:
        return False
    if any(character.isdigit() for character in word):
        return False
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'-")
    return all(character in allowed_chars for character in word)


def check_high_frequency_missing_words(
    session: Any,
    *,
    top_n: int = 5000,
    min_rank: int = 1,
) -> Dict[str, Any]:
    """Return ranked English corpus tokens missing from the dictionary."""
    logger.info("Checking top %d frequency words for missing lemmas...", top_n)
    try:
        high_frequency_tokens = (
            session.query(WordToken)
            .filter(
                WordToken.language_code == "en",
                WordToken.frequency_rank.isnot(None),
                WordToken.frequency_rank >= min_rank,
            )
            .order_by(WordToken.frequency_rank)
            .limit(top_n)
            .all()
        )
        existing_words = filter_existing_english_words(
            session,
            [token.token for token in high_frequency_tokens],
            include_exclusions=True,
        )

        missing_words = []
        for token in high_frequency_tokens:
            if token.token.lower() in existing_words:
                continue
            if not is_valid_frequency_candidate(token.token):
                continue

            annotations = (
                session.query(ExternalLexemeAnnotation)
                .filter(
                    ExternalLexemeAnnotation.word_token_id == token.id,
                    ExternalLexemeAnnotation.source.like("wordfreq_%"),
                )
                .all()
            )
            corpus_frequencies = [
                {
                    "corpus": annotation.source.removeprefix("wordfreq_"),
                    "rank": annotation.ordinal_rank,
                    "frequency": annotation.frequency,
                }
                for annotation in annotations
            ]
            missing_words.append(
                {
                    "word": token.token,
                    "overall_rank": token.frequency_rank,
                    "corpus_frequencies": corpus_frequencies,
                }
            )

        return {
            "total_checked": len(high_frequency_tokens),
            "missing_count": len(missing_words),
            "missing_words": missing_words,
            "existing_word_count": session.query(Lemma).count(),
        }
    except Exception as error:
        logger.error("Error checking high-frequency missing words: %s", error)
        return {
            "error": str(error),
            "total_checked": 0,
            "missing_count": 0,
            "missing_words": [],
        }


def print_report(results: Dict[str, Any], *, max_words: int = 200) -> None:
    """Print a compact human-readable missing-word report."""
    if "error" in results:
        print(f"Error: {results['error']}")
        return
    print(f"Frequency tokens checked: {results['total_checked']}")
    print(f"Missing words found: {results['missing_count']}")
    print(f"Existing words in database: {results.get('existing_word_count', 'N/A')}")
    for index, word_info in enumerate(results["missing_words"][:max_words], 1):
        print(f"{index}. {word_info['word']} (rank: {word_info['overall_rank']})")


def main() -> None:
    """Run the missing-word report from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument("--top-n", type=int, default=5000)
    parser.add_argument("--min-rank", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    config = get_data_source_config(args)
    session = create_session(config)
    try:
        results = check_high_frequency_missing_words(
            session,
            top_n=args.top_n,
            min_rank=args.min_rank,
        )
    finally:
        session.close()

    print_report(results)
    if args.output is not None:
        args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
