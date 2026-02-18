"""Dutch-specific utility functions."""


def strip_subject_pronoun(text: str) -> str:
    """Strip a Dutch subject pronoun from the beginning of a verb phrase."""
    normalized = text.strip().lower()
    if not normalized:
        return ""

    pronouns = ["ik ", "jij ", "je ", "u ", "hij ", "zij ", "ze ", "het ", "wij ", "we ", "jullie ", "zij ", "ze "]
    for pronoun in pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()
    return normalized
