"""Match English words to sense-specific definitions or emojis."""

import random

from worksheets.models import Question, Word, Worksheet


def build_matching(words: list[Word], clue_type: str, seed: int) -> Worksheet:
    """Shuffle clues independently and retain the correct answer letters."""
    if clue_type not in {"definition", "emoji"}:
        raise ValueError("Unknown clue type.")
    clues = [word.emoji if clue_type == "emoji" else word.definition for word in words]
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
    return Worksheet(
        "English matching",
        "Write the letter of the matching clue beside each word. Use each letter once.",
        questions,
        tuple(clues),
        clue_type == "emoji",
    )
