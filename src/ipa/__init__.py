"""IPA utilities package."""

from ipa.generation import (
    IPA_PRONUNCIATION_JSON_SCHEMA,
    build_ipa_pronunciation_prompt,
    generate_ipa_pronunciation,
    query_ipa_pronunciation,
)
from ipa.normalization import (
    are_ipa_equivalent,
    is_ipa_levenshtein_match,
    normalize_ipa,
    weighted_similarity_ratio,
)
from ipa.rhyme_keys import (
    IPA_VOWELS,
    RHYME_KEY_LANGUAGES,
    compute_rhyme_key,
    rhyme_key_final_sound,
    rhyme_key_penultimate_sound,
    rhyme_keys_available,
)

__all__ = [
    "IPA_PRONUNCIATION_JSON_SCHEMA",
    "build_ipa_pronunciation_prompt",
    "generate_ipa_pronunciation",
    "query_ipa_pronunciation",
    "normalize_ipa",
    "weighted_similarity_ratio",
    "are_ipa_equivalent",
    "is_ipa_levenshtein_match",
    "RHYME_KEY_LANGUAGES",
    "IPA_VOWELS",
    "rhyme_keys_available",
    "compute_rhyme_key",
    "rhyme_key_final_sound",
    "rhyme_key_penultimate_sound",
]
