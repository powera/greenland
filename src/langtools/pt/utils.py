"""Portuguese-specific utility functions."""


def strip_subject_pronoun(text: str) -> str:
    """Strip a Portuguese subject pronoun from the beginning of a verb phrase."""
    normalized = text.strip().lower()
    if not normalized:
        return ""

    combined_pronouns = ["ele/ela ", "ela/ele ", "ele / ela ", "ela / ele "]
    for pronoun in combined_pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()

    pronouns = ["eu ", "tu ", "ele ", "ela ", "você ", "voce ", "nós ", "nos ", "vós ", "vos ", "vocês ", "voces ", "eles ", "elas "]
    for pronoun in pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()
    return normalized
