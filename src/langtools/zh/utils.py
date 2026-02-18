"""Chinese-specific utility functions."""


def strip_subject_pronoun(text: str) -> str:
    """Strip a Mandarin subject pronoun from the beginning of a clause."""
    normalized = text.strip()
    if not normalized:
        return ""

    combined_pronouns = ["他/她", "她/他", "他 / 她", "她 / 他"]
    for pronoun in combined_pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()

    pronouns = ["我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "它们"]
    for pronoun in sorted(pronouns, key=len, reverse=True):
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()
    return normalized
