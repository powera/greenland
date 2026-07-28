"""Output-size estimates for the sentence pipeline's LLM calls.

Phase 3 (decomposition) and Phase 4 (dependencies) emit one JSON object per word
per language, so their response size is predictable from the input: count the
words, multiply. Every other property of the call is fixed.

That matters because the alternative is discovering the size after the fact. A
45-word sentence decomposed into several languages overruns a 4096-token default
and comes back truncated mid-array, which is not distinguishable from a short
answer without checking the provider's finish reason. Estimating up front and
asking for the room we need turns that into a non-event.

The estimate is deliberately generous. Guessing low truncates the response and
fails the whole call; guessing high costs nothing, because output tokens are
billed as generated, not as reserved. Callers pass the estimate through
``clients.lib.limit_from_estimate()``, which owns the safety-margin policy.
"""

import logging
from typing import Mapping, Sequence

logger = logging.getLogger(__name__)

# Output tokens for one decomposed word. Each emits the seven fields of
# build_decomposed_word_schema() -- position, part_of_speech, english_gloss,
# surface_form, grammatical_form, lemma_guid, lemma -- as JSON with quoted keys.
#
# Measured at ~42 tokens/word on a real 5-language run (37 words, 1580 output
# tokens; see scripts/trace_sentence_pipeline.py, which prints estimated vs.
# actual). 60 keeps roughly 1.4x over that before limit_from_estimate() adds its
# own margin. Isolated JSON objects encode at 55-60 tokens, but a real response
# is compact and most words are short function words -- do not re-tune from a
# hand-built sample.
TOKENS_PER_DECOMPOSED_WORD: int = 60

# Output tokens for one dependency entry: position, ud_relation,
# ud_head_position. Much smaller than a decomposed word -- three short fields,
# one of them a closed enum of relation labels. Measured at ~16 tokens/word.
TOKENS_PER_DEPENDENCY_WORD: int = 22

# Output tokens per word of a Phase-1 translated sentence. Phase 1 emits only
# the sentence text per language, no per-word breakdown, so this is ordinary
# prose. Measured at ~2 tokens/word/language for Latin and CJK targets; 5 keeps
# headroom for scripts that tokenize far less efficiently (Cyrillic,
# Devanagari, Kannada), which the measured run did not include.
TOKENS_PER_TRANSLATED_WORD: int = 5

# Fixed per-call cost that does not scale with word count: the response
# envelope, per-language wrapper objects, and any word_count field.
DECOMPOSITION_OVERHEAD_TOKENS: int = 400
DEPENDENCY_OVERHEAD_TOKENS: int = 200
TRANSLATION_OVERHEAD_TOKENS: int = 200

# Per-language overhead in a combined multi-language decomposition, which nests
# each language's word array under its own key.
DECOMPOSITION_PER_LANGUAGE_OVERHEAD_TOKENS: int = 60

# Languages that do not separate words with whitespace, so splitting on it
# undercounts badly. Kept in sync with the set of the same name in
# translate_and_decompose; duplicated rather than imported to avoid a circular
# import, since that module imports this one.
_NO_WHITESPACE_LANGUAGES = frozenset({"zh", "ja", "th", "lo", "km", "my"})

# Characters per word assumed for the languages above. CJK averages well under
# two characters per word, so this over-counts, which is the safe direction.
_CHARS_PER_WORD_NO_WHITESPACE: int = 2


def estimate_word_count(text: str, language_code: str) -> int:
    """Estimate how many words the LLM will emit for a translation.

    Whitespace splitting for languages that use it, character count for those
    that do not. This only has to be close enough to size a request; it is not
    the tokenization used for coverage checks.
    """
    if not text or not text.strip():
        return 0
    if language_code.lower() in _NO_WHITESPACE_LANGUAGES:
        stripped = "".join(text.split())
        return max(len(stripped) // _CHARS_PER_WORD_NO_WHITESPACE, 1)
    return len(text.split())


def estimate_decomposition_output_tokens(*, target_translations: Mapping[str, str]) -> int:
    """Estimate the response size of a Phase-3 decomposition call.

    Args:
        target_translations: language_code -> translation text, exactly the
            mapping the decomposition call will be asked to break down. A
            single-language call passes a one-entry mapping.

    Returns:
        Estimated output tokens. Pass to clients.lib.limit_from_estimate() to
        get a token limit; do not use as the limit directly.
    """
    if not target_translations:
        return DECOMPOSITION_OVERHEAD_TOKENS

    total = DECOMPOSITION_OVERHEAD_TOKENS
    for language_code, text in target_translations.items():
        word_count = estimate_word_count(text, language_code)
        total += word_count * TOKENS_PER_DECOMPOSED_WORD
        total += DECOMPOSITION_PER_LANGUAGE_OVERHEAD_TOKENS
    return total


def estimate_translation_output_tokens(
    *, source_text: str, source_language: str, target_languages: Sequence[str]
) -> int:
    """Estimate the response size of a Phase-1 translation call.

    The translations do not exist yet, so their length is estimated from the
    source sentence. Translations vary in length, but not by enough to matter
    against the headroom ``limit_from_estimate()`` adds.
    """
    word_count = estimate_word_count(source_text, source_language)
    return TRANSLATION_OVERHEAD_TOKENS + word_count * TOKENS_PER_TRANSLATED_WORD * max(
        len(target_languages), 1
    )


def estimate_dependency_output_tokens(*, word_count: int) -> int:
    """Estimate the response size of a Phase-4 dependency call.

    Phase 4 runs per language over an already-decomposed word list, so the word
    count is known exactly rather than estimated.
    """
    if word_count < 0:
        word_count = 0
    return DEPENDENCY_OVERHEAD_TOKENS + word_count * TOKENS_PER_DEPENDENCY_WORD
