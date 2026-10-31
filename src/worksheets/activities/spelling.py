"""Missing-letter and scrambled-letter spelling exercises."""

import random

from worksheets.models import Question, Word, Worksheet


def build_spelling(words: list[Word], mode: str, clue_type: str, seed: int) -> Worksheet:
    """Build spelling questions with English definition or emoji clues."""
    if mode not in {"missing", "scramble"} or clue_type not in {"definition", "emoji"}:
        raise ValueError("Unknown spelling mode or clue type.")
    rng = random.Random(seed)
    questions = []
    for word in words:
        if mode == "missing":
            letters = list(word.text)
            positions = rng.sample(range(len(letters)), max(1, len(letters) // 3))
            for position in positions:
                letters[position] = "_"
            prompt = " ".join(letters)
        else:
            letters = list(word.text)
            rng.shuffle(letters)
            if "".join(letters) == word.text:
                # A rotation guarantees a change for every nonconstant word.
                offset = next(i for i, letter in enumerate(letters) if letter != letters[0])
                letters = letters[offset:] + letters[:offset]
            prompt = " ".join(letters)
        clue = word.emoji if clue_type == "emoji" else word.definition
        questions.append(Question(word.source_id, prompt, clue, word.text))
    instructions = (
        "Fill in the missing letters. Use each clue to find the intended word."
        if mode == "missing"
        else "Unscramble the letters. Use each clue to find the intended word."
    )
    return Worksheet(
        "English spelling", instructions, tuple(questions), emoji_clues=clue_type == "emoji"
    )
