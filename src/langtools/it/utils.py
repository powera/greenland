"""Italian-specific utility functions."""


def strip_subject_pronoun(text: str) -> str:
    """Strip an Italian subject pronoun from the beginning of a verb phrase."""
    normalized = text.strip().lower()
    if not normalized:
        return ""

    combined_pronouns = ["lui/lei ", "lei/lui ", "lui / lei ", "lei / lui "]
    for pronoun in combined_pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()

    pronouns = ["io ", "tu ", "lui ", "lei ", "noi ", "voi ", "loro "]
    for pronoun in pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()
    return normalized
