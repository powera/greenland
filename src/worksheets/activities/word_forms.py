"""Write the plural, past tense, past participle, or comparison of a base word."""

from worksheets.models import FormEntry, Question, Worksheet

BLANK = "________"

# kind -> (title, instructions, prompt template using {base} and {blank}).
FORM_TEXT: dict[str, tuple[str, str, str]] = {
    "plural": (
        "Plurals",
        "Write the word for more than one.",
        "one {base}, two {blank}",
    ),
    "past": (
        "Past tense",
        "Write the past tense of each verb.",
        "{base}: {blank}",
    ),
    "past_participle": (
        "Past participles",
        "Write the past participle of each verb.",
        "{base}: have {blank}",
    ),
    "principal_parts": (
        "Verb forms: past and past participle",
        "Write the past tense, then the past participle.",
        "{base}: {blank}, have {blank}",
    ),
    "comparison": (
        "Comparing words",
        "Write the form for comparing two things, then the form for the most of all "
        "(for example big: bigger, biggest; careful: more careful, most careful).",
        "{base}: {blank}, {blank}",
    ),
}


def build_word_forms(entries: list[FormEntry], kind: str) -> Worksheet:
    """One question per base word; the answer lists each blank's form in order."""
    if kind not in FORM_TEXT:
        raise ValueError("Unknown word-form activity.")
    title, instructions, template = FORM_TEXT[kind]
    questions = tuple(
        Question(
            entry.source_id,
            template.format(base=entry.base, blank=BLANK),
            entry.clue,
            ", ".join(entry.forms),
        )
        for entry in entries
    )
    return Worksheet(title, instructions, questions)
