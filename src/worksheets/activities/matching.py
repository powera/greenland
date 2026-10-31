"""Match English words to clues: definitions, emojis, synonyms, or rhyming words."""

import random

from worksheets.models import Question, Word, Worksheet

# Synonym and rhyme pairs carry the partner word in ``Word.definition``.
MATCHING_TEXT: dict[str, tuple[str, str]] = {
    "definition": (
        "English matching",
        "Write the letter of the matching clue beside each word. Use each letter once.",
    ),
    "emoji": (
        "English matching",
        "Write the letter of the matching picture beside each word. Use each letter once.",
    ),
    "synonym": (
        "Synonym matching",
        "Write the letter of the word that means almost the same. Use each letter once.",
    ),
    "rhyme": (
        "Rhyme matching",
        "Write the letter of the word that rhymes. Use each letter once.",
    ),
}


def build_matching(words: list[Word], clue_type: str, seed: int) -> Worksheet:
    """Shuffle clues independently and retain the correct answer letters."""
    if clue_type not in MATCHING_TEXT:
        raise ValueError("Unknown clue type.")
    clues = [word.emoji if clue_type == "emoji" else word.definition for word in words]
    if len(set(clues)) != len(clues):
        raise ValueError("Matching clues must be unique.")
    random.Random(seed).shuffle(clues)
    questions = tuple(
        Question(
            word.source_id,
            word.text,
            "",
            chr(65 + clues.index(word.emoji if clue_type == "emoji" else word.definition)),
        )
        for word in words
    )
    title, instructions = MATCHING_TEXT[clue_type]
    return Worksheet(title, instructions, questions, tuple(clues), clue_type == "emoji")
