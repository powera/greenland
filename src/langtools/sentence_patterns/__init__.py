"""Pattern sentences: short fixed frames filled with one database word.

These are the "first sentences" Trakaido builds at runtime ("I want a cat",
"She is tired", "The cars are red").  The app owns the quiz (prompts,
distractors, level gating); this package is the Greenland-side reference for
which sentences each language can make and from what data, so a missing
form shows up here as a Skip with its reason instead of as a quietly smaller
drill in the app.

Each language's patterns live in langtools.<lang>.sentence_patterns; this
package holds the shared types and helpers they import, so the language
modules are loaded lazily here rather than at import time.

Nothing here touches the database: callers build a WordPools (see
sentences.pattern_pools) and call render().
"""

import importlib
from typing import Dict, List, Optional, Set, Tuple

from langtools.sentence_patterns.types import (
    SUBJECTS,
    PatternResult,
    RenderedSentence,
    SentencePattern,
    Skip,
    SlotNoun,
    WordPools,
)

# language code -> (module under langtools, attribute holding its patterns)
_PATTERN_MODULES: Dict[str, Tuple[str, str]] = {
    "lt": ("lt", "PATTERNS"),
    "es": ("es", "PATTERNS"),
    "es-419": ("es", "LATIN_AMERICAN_PATTERNS"),
    "fr": ("fr", "PATTERNS"),
    "zh": ("zh", "PATTERNS"),
}


def supported_languages() -> List[str]:
    return list(_PATTERN_MODULES)


def pattern_module_for(language_code: str) -> str:
    """'es-419' -> 'langtools.es.sentence_patterns'."""
    return f"langtools.{_PATTERN_MODULES[language_code][0]}.sentence_patterns"


def patterns_for(language_code: str) -> List[SentencePattern]:
    module = importlib.import_module(pattern_module_for(language_code))
    patterns: List[SentencePattern] = getattr(module, _PATTERN_MODULES[language_code][1])
    return patterns


def render(
    language_code: str,
    pools: WordPools,
    pattern_ids: Optional[List[str]] = None,
) -> PatternResult:
    """Every sentence each pattern can make from ``pools``, for every subject,
    plus a Skip for each word a pattern could not use."""
    patterns = patterns_for(language_code)
    if pattern_ids is not None:
        patterns = [p for p in patterns if p.pattern_id in pattern_ids]
    result = PatternResult()
    # A word that lacks a form fails the same way for every subject and every
    # color it is paired with; report it once.
    seen_skips: Set[Skip] = set()
    for pattern in patterns:
        for words in pattern.candidates(pools):
            invalid = False
            for word in words:
                if not isinstance(word, SlotNoun):
                    continue
                reason = None
                if word.countability not in {"countable", "uncountable", "both"}:
                    reason = "missing countability"
                elif word.english_countability not in {"countable", "uncountable", "both"}:
                    reason = "missing en countability"
                elif "plurale_tantum" in (word.number_type, word.english_number_type):
                    reason = "unsupported plural-only noun"
                elif (word.countability == "uncountable") != (
                    word.english_countability == "uncountable"
                ):
                    reason = "unsupported countability mismatch with English"
                if reason:
                    invalid = True
                    skip = Skip(pattern.pattern_id, word.guid, reason)
                    if skip not in seen_skips:
                        seen_skips.add(skip)
                        result.skips.append(skip)
            if invalid:
                continue
            subjects = SUBJECTS if pattern.personal else (None,)
            for subject in subjects:
                for outcome in pattern.build(words, subject):
                    if isinstance(outcome, RenderedSentence):
                        result.sentences.append(outcome)
                    elif outcome not in seen_skips:
                        seen_skips.add(outcome)
                        result.skips.append(outcome)
    return result


__all__ = [
    "PatternResult",
    "RenderedSentence",
    "Skip",
    "WordPools",
    "patterns_for",
    "render",
    "supported_languages",
]
