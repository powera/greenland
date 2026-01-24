"""Vocabulary budget builder for guided sentence generation.

Reads wordlists from data/release and builds a summary of available
words by category, filtered by difficulty level.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set

import constants


def load_vocabulary_from_release(
    max_level: int = 8,
    release_dir: Optional[Path] = None,
) -> Dict[str, Dict[str, List[str]]]:
    """Load vocabulary from data/release, filtered by difficulty level.

    Args:
        max_level: Maximum difficulty level to include (default 8)
        release_dir: Path to release directory (default: data/release)

    Returns:
        Nested dict: {pos_type: {pos_subtype: [word1, word2, ...]}}
    """
    if release_dir is None:
        release_dir = Path(constants.SRC_DIR).parent / "data" / "release"

    lemmas_dir = release_dir / "lemmas"
    if not lemmas_dir.exists():
        return {}

    vocabulary: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))

    # Read all base.jsonl files
    for base_file in lemmas_dir.rglob("base.jsonl"):
        try:
            with open(base_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    data = json.loads(line)

                    # Check difficulty level
                    level = data.get("difficulty_level")
                    if level is None or level < 0 or level > max_level:
                        continue

                    pos_type = data.get("pos_type", "unknown")
                    pos_subtype = data.get("pos_subtype", "misc")

                    # Get English word from translations or concept_label
                    translations = data.get("translations", {})
                    word = translations.get("en") or data.get("concept_label", "")

                    if word:
                        # Strip disambiguation if present
                        if "(" in word:
                            word = word.split("(")[0].strip()
                        vocabulary[pos_type][pos_subtype].append(word)

        except Exception as e:
            print(f"Error loading {base_file}: {e}")

    return dict(vocabulary)


def format_vocabulary_summary(
    vocabulary: Dict[str, Dict[str, List[str]]],
    max_examples_per_category: int = 8,
    exclude_subtypes: Optional[Set[str]] = None,
    flatten_pos_types: Optional[Set[str]] = None,
) -> str:
    """Format vocabulary as a readable summary for LLM prompts.

    Args:
        vocabulary: Output from load_vocabulary_from_release()
        max_examples_per_category: Max words to show per category
        exclude_subtypes: Subtypes to exclude (e.g., {"pronoun", "determiner"})
        flatten_pos_types: POS types to show as flat list without categories
                          (e.g., {"verb"} shows "VERBS: eat, drink, sleep, ...")

    Returns:
        Formatted string like:
        "NOUNS: 8 animals (dog, cat, bird...), 10 foods (bread, rice...)
         VERBS: eat, drink, sleep, walk, run, see, hear, say, ...
         ADJECTIVES: 8 colors (red, blue, green...), 6 sizes (big, small...)"
    """
    if exclude_subtypes is None:
        exclude_subtypes = set()
    if flatten_pos_types is None:
        flatten_pos_types = set()

    lines = []

    # Order: nouns, verbs, adjectives, adverbs, then others
    pos_order = ["noun", "verb", "adjective", "adverb"]
    ordered_pos = pos_order + [p for p in vocabulary.keys() if p not in pos_order]

    for pos_type in ordered_pos:
        if pos_type not in vocabulary:
            continue

        subtypes = vocabulary[pos_type]

        # For flattened POS types, show all words in a simple list
        if pos_type in flatten_pos_types:
            all_words = []
            for subtype, words in subtypes.items():
                if subtype not in exclude_subtypes:
                    all_words.extend(words)
            if all_words:
                words_str = ", ".join(all_words)
                lines.append(f"{pos_type.upper()}S: {words_str}")
            continue

        # For other POS types, show by category
        category_parts = []

        for subtype, words in sorted(subtypes.items()):
            if subtype in exclude_subtypes:
                continue

            count = len(words)
            if count == 0:
                continue

            # Show examples
            examples = words[:max_examples_per_category]
            examples_str = ", ".join(examples)
            if count > max_examples_per_category:
                examples_str += "..."

            # Format: "8 animals (dog, cat, bird...)"
            category_parts.append(f"{count} {subtype} ({examples_str})")

        if category_parts:
            lines.append(f"{pos_type.upper()}S: {'; '.join(category_parts)}")

    return "\n".join(lines)


def get_words_for_category(
    vocabulary: Dict[str, Dict[str, List[str]]],
    pos_type: str,
    pos_subtype: Optional[str] = None,
) -> List[str]:
    """Get all words for a specific category.

    Args:
        vocabulary: Output from load_vocabulary_from_release()
        pos_type: Part of speech (noun, verb, etc.)
        pos_subtype: Optional subtype filter

    Returns:
        List of words
    """
    if pos_type not in vocabulary:
        return []

    if pos_subtype:
        return vocabulary[pos_type].get(pos_subtype, [])

    # Return all words for this POS type
    all_words = []
    for words in vocabulary[pos_type].values():
        all_words.extend(words)
    return all_words


def build_prompt_vocabulary_section(
    target_word: str,
    target_pos_type: str,
    target_pos_subtype: str,
    max_level: int = 7,
) -> str:
    """Build a vocabulary section for sentence generation prompts.

    Args:
        target_word: The word sentences are being generated for
        target_pos_type: POS type of target word
        target_pos_subtype: POS subtype of target word
        max_level: Maximum difficulty level

    Returns:
        Formatted vocabulary description for prompt
    """
    vocabulary = load_vocabulary_from_release(max_level=max_level)

    # Exclude function word categories that don't need to be listed
    exclude = {"pronoun", "determiner", "article", "conjunction", "preposition"}

    summary = format_vocabulary_summary(
        vocabulary,
        max_examples_per_category=2,
        exclude_subtypes=exclude,
        flatten_pos_types={"verb"},  # Show verbs as flat list, not by category
    )

    return f"""Available vocabulary (levels 1-{max_level}):
{summary}

You may also use common pronouns (I, you, he, she, we, they) and articles (a, the).
Try to use words from the vocabulary above when possible, but natural sentences are more important than strict vocabulary adherence."""
