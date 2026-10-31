"""Complete a word family: write the missing member for the given part of speech."""

import random
import re

from worksheets.activities.word_forms import BLANK
from worksheets.models import FamilyMember, Question, Worksheet


def build_families(families: list[tuple[FamilyMember, ...]], seed: int) -> Worksheet:
    """Hide one member of each family; its definition is the clue unless it gives it away."""
    rng = random.Random(seed)
    questions = []
    for family in families:
        hidden = rng.randrange(len(family))
        target = family[hidden]
        shown = [
            (
                f"{BLANK} ({member.pos_type})"
                if index == hidden
                else f"{member.text} ({member.pos_type})"
            )
            for index, member in enumerate(family)
        ]
        # The family's other words are on the page, so only the answer itself is a giveaway.
        clue = (
            ""
            if re.search(rf"\b{re.escape(target.text)}\b", target.definition, re.I)
            else target.definition
        )
        questions.append(Question(target.source_id, " · ".join(shown), clue, target.text))
    return Worksheet(
        "Word families",
        "Each line is one word family. Write the missing word for the part of speech shown.",
        tuple(questions),
    )
