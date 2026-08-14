"""Report dictionary coverage for a wikitext-format English word list."""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from langtools.en.grammatical_words import ENGLISH_GRAMMATICAL_WORDS_WITH_CONTRACTIONS
from storage.backend import create_session
from storage.queries.lemma import filter_existing_english_words


def parse_wikitext_file(file_path: str) -> List[str]:
    """Extract deduplicated, single-word link labels from a wikitext file."""
    content = Path(file_path).read_text(encoding="utf-8")
    link_pattern = re.compile(r"\[\[:?(?:[^|\]]*\|)?([^\]]+)\]\]")
    seen: Set[str] = set()
    words: List[str] = []

    for match in link_pattern.finditer(content):
        display_text = match.group(1).strip()
        if len(display_text) == 1 and display_text.isupper():
            continue
        if display_text.endswith("-"):
            continue
        word_lower = display_text.lower()
        if word_lower in seen or " " in word_lower:
            continue
        seen.add(word_lower)
        words.append(word_lower)
    return words


def get_grammatical_stopwords() -> Set[str]:
    """Return grammatical words excluded from content-word coverage."""
    return set(ENGLISH_GRAMMATICAL_WORDS_WITH_CONTRACTIONS)


def get_existing_english_words(session: Any, words: Iterable[str]) -> Set[str]:
    """Return the supplied words that exist in any English dictionary form."""
    return filter_existing_english_words(session, words)


def check_wordlist_coverage(file_path: str, session: Any) -> Dict[str, Any]:
    """Return coverage statistics and missing content words for a word list."""
    parsed_words = parse_wikitext_file(file_path)
    existing_words = get_existing_english_words(session, parsed_words)
    grammatical_stopwords = get_grammatical_stopwords()

    in_database: List[str] = []
    filtered_stopwords: List[str] = []
    missing_words: List[str] = []
    for word in parsed_words:
        if word in existing_words:
            in_database.append(word)
        elif word in grammatical_stopwords:
            filtered_stopwords.append(word)
        else:
            missing_words.append(word)
    missing_words.sort()

    return {
        "file_path": file_path,
        "total_words": len(parsed_words),
        "in_database": len(in_database),
        "grammatical_stopwords_filtered": len(filtered_stopwords),
        "missing_count": len(missing_words),
        "missing_words": missing_words,
    }


def print_report(results: Dict[str, Any]) -> None:
    """Print a human-readable coverage summary."""
    print(f"Source: {results['file_path']}")
    print(f"Total words: {results['total_words']}")
    print(f"In database: {results['in_database']}")
    print(f"Grammatical stopwords: {results['grammatical_stopwords_filtered']}")
    print(f"Missing content words: {results['missing_count']}")
    if results["missing_words"]:
        print("\n".join(results["missing_words"]))


def main() -> None:
    """Run the word-list coverage report from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument("wordlist", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    config = get_data_source_config(args)
    session = create_session(config)
    try:
        results = check_wordlist_coverage(str(args.wordlist), session)
    finally:
        session.close()

    print_report(results)
    if args.output is not None:
        args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
