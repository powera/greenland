"""English-specific utility functions."""

from typing import List


def clean_form(text: str) -> List[str]:
    """
    Clean an English grammatical form by handling alternatives.

    Args:
        text: Raw form text (may contain slashes for alternatives, etc.)

    Returns:
        List of cleaned forms (multiple if there are alternatives separated by /)
    """
    if not text or text.strip() in ("", "-", "\u2014", "\u2013", "—"):
        return []

    # Split by slash or comma to handle alternative forms
    forms: List[str] = []
    for part in text.split("/"):
        for subpart in part.split(","):
            cleaned = subpart.strip()
            if cleaned and cleaned not in ("-", "—", "\u2014", "\u2013"):
                forms.append(cleaned)

    return forms


def generate_regular_plural(word: str) -> str:
    """
    Generate regular English plural form.

    Args:
        word: Singular noun

    Returns:
        Plural form following regular rules
    """
    if not word:
        return word

    # Words ending in -s, -ss, -sh, -ch, -x, -z add -es
    if word.endswith(("s", "ss", "sh", "ch", "x", "z")):
        return word + "es"

    # Words ending in consonant + y change y to -ies
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return word[:-1] + "ies"

    # Words ending in -f or -fe often change to -ves (but not always)
    # This is a common pattern but has exceptions
    if word.endswith("fe"):
        return word[:-2] + "ves"
    if word.endswith("f") and not word.endswith("ff"):
        return word[:-1] + "ves"

    # Words ending in -o (some add -es, some just -s)
    # Common words that add -es: hero, potato, tomato, echo, veto
    # This is a heuristic
    if word.endswith("o") and word[-2:] not in ("oo", "io", "eo"):
        return word + "es"

    # Regular plural: add -s
    return word + "s"


def generate_3s_present(verb: str) -> str:
    """
    Generate 3rd person singular present form.

    Args:
        verb: Base/infinitive form

    Returns:
        3rd person singular present (e.g., walks, goes, watches)
    """
    if not verb:
        return verb

    # Verbs ending in -s, -ss, -sh, -ch, -x, -z add -es
    if verb.endswith(("s", "ss", "sh", "ch", "x", "z")):
        return verb + "es"

    # Verbs ending in consonant + y change y to -ies
    if verb.endswith("y") and len(verb) > 1 and verb[-2] not in "aeiou":
        return verb[:-1] + "ies"

    # Verbs ending in -o add -es
    if verb.endswith("o"):
        return verb + "es"

    # Regular: add -s
    return verb + "s"


def generate_past_tense(verb: str) -> str:
    """
    Generate regular past tense form.

    Args:
        verb: Base/infinitive form

    Returns:
        Past tense form (e.g., walked, tried)
    """
    if not verb:
        return verb

    # Already ends in -e: add -d
    if verb.endswith("e"):
        return verb + "d"

    # Ends in consonant + y: change y to -ied
    if verb.endswith("y") and len(verb) > 1 and verb[-2] not in "aeiou":
        return verb[:-1] + "ied"

    # Single consonant after single short vowel: double the consonant
    # This is a simplified heuristic
    if (
        len(verb) >= 2
        and verb[-1] in "bdgklmnprstz"
        and verb[-2] in "aeiou"
        and (len(verb) < 3 or verb[-3] not in "aeiou")
    ):
        return verb + verb[-1] + "ed"

    # Regular: add -ed
    return verb + "ed"


def generate_present_participle(verb: str) -> str:
    """
    Generate present participle (gerund) form.

    Args:
        verb: Base/infinitive form

    Returns:
        Present participle form (e.g., walking, running)
    """
    if not verb:
        return verb

    # Ends in -ie: change to -ying
    if verb.endswith("ie"):
        return verb[:-2] + "ying"

    # Ends in -e (not -ee, -ye, -oe): drop the e
    if verb.endswith("e") and len(verb) > 1 and verb[-2] not in "eyo":
        return verb[:-1] + "ing"

    # Single consonant after single short vowel: double the consonant
    if (
        len(verb) >= 2
        and verb[-1] in "bdgklmnprstz"
        and verb[-2] in "aeiou"
        and (len(verb) < 3 or verb[-3] not in "aeiou")
    ):
        return verb + verb[-1] + "ing"

    # Regular: add -ing
    return verb + "ing"


def generate_comparative(adjective: str) -> str:
    """
    Generate comparative form of an adjective.

    Args:
        adjective: Positive form

    Returns:
        Comparative form (e.g., bigger, happier)
    """
    if not adjective:
        return adjective

    # Short adjectives (1 syllable, or 2 syllables ending in -y, -le, -er, -ow)
    # use -er ending

    # Ends in -e: add -r
    if adjective.endswith("e"):
        return adjective + "r"

    # Ends in consonant + y: change y to -ier
    if adjective.endswith("y") and len(adjective) > 1 and adjective[-2] not in "aeiou":
        return adjective[:-1] + "ier"

    # Single consonant after single short vowel: double the consonant
    if (
        len(adjective) >= 2
        and adjective[-1] in "bdgpt"
        and adjective[-2] in "aeiou"
        and (len(adjective) < 3 or adjective[-3] not in "aeiou")
    ):
        return adjective + adjective[-1] + "er"

    # Regular short adjective: add -er
    return adjective + "er"


def generate_superlative(adjective: str) -> str:
    """
    Generate superlative form of an adjective.

    Args:
        adjective: Positive form

    Returns:
        Superlative form (e.g., biggest, happiest)
    """
    if not adjective:
        return adjective

    # Ends in -e: add -st
    if adjective.endswith("e"):
        return adjective + "st"

    # Ends in consonant + y: change y to -iest
    if adjective.endswith("y") and len(adjective) > 1 and adjective[-2] not in "aeiou":
        return adjective[:-1] + "iest"

    # Single consonant after single short vowel: double the consonant
    if (
        len(adjective) >= 2
        and adjective[-1] in "bdgpt"
        and adjective[-2] in "aeiou"
        and (len(adjective) < 3 or adjective[-3] not in "aeiou")
    ):
        return adjective + adjective[-1] + "est"

    # Regular short adjective: add -est
    return adjective + "est"
