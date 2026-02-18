"""Chinese-specific utility functions."""


def strip_subject_pronoun(text: str) -> str:
    """Strip a Mandarin subject pronoun from the beginning of a clause."""
    normalized = text.strip()
    if not normalized:
        return ""

    pronouns = ["我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "它们"]
    for pronoun in sorted(pronouns, key=len, reverse=True):
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()
    return normalized
