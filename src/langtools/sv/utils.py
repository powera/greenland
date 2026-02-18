"""Swedish-specific utility functions."""


def strip_subject_pronoun(text: str) -> str:
    """Strip a Swedish subject pronoun from the beginning of a verb phrase."""
    normalized = text.strip().lower()
    if not normalized:
        return ""

    pronouns = ["jag ", "du ", "han ", "hon ", "den ", "det ", "vi ", "ni ", "de "]
    for pronoun in pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()
    return normalized
