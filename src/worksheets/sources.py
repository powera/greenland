"""Read existing English lemma data without modifying the linguistic database."""

import json
import random
import re

from sqlalchemy.orm import Session

from storage.models.schema import Lemma
from worksheets.models import Word


def select_words(
    session: Session, count: int, clue_type: str, seed: int, category: str = ""
) -> list[Word]:
    """Select unique words and clues; exclude clues that reveal the spelling."""
    query = session.query(Lemma).filter(Lemma.guid.isnot(None))
    if category:
        query = query.filter(Lemma.pos_subtype == category)
    # Stable order makes a seed reproducible while source data remains unchanged.
    lemmas = query.order_by(Lemma.guid).all()
    random.Random(seed).shuffle(lemmas)
    selected: list[Word] = []
    seen_words: set[str] = set()
    seen_clues: set[str] = set()
    for lemma in lemmas:
        text = lemma.lemma_text.strip().lower()
        if not re.fullmatch(r"[a-z]{2,16}", text) or len(set(text)) < 2:
            continue
        definition = lemma.definition_text.strip()
        try:
            emojis = json.loads(lemma.emoji or "[]")
        except (ValueError, TypeError):
            emojis = []
        emoji = (
            next((item for item in emojis if isinstance(item, str) and item.strip()), "")
            if isinstance(emojis, list)
            else ""
        )
        clue = emoji if clue_type == "emoji" else definition
        normalized_clue = clue.casefold()
        if not clue or text in seen_words or normalized_clue in seen_clues:
            continue
        if clue_type == "definition" and re.search(rf"\b{re.escape(text)}\b", clue, re.I):
            continue
        selected.append(Word(str(lemma.guid), text, definition, emoji))
        seen_words.add(text)
        seen_clues.add(normalized_clue)
        if len(selected) == count:
            break
    if len(selected) < count:
        raise ValueError(
            f"Only {len(selected)} eligible words found; request fewer questions or change filters."
        )
    return selected
