"""Resolve observed corpus spellings without conflating case-sensitive words."""

from collections import Counter
from typing import Collection, Dict, Mapping

from wordfreq.corpora.gutenberg_text import TextStats

# Small, explicit exceptions for case-sensitive words whose ordinary-prose uses
# may be much rarer than the lowercase homograph. Callers can supply additional
# vocabulary without loading a database or guessing that every capital is a name.
KNOWN_DISTINCT_SPELLINGS = frozenset(
    {"I", "I'd", "I'll", "I'm", "I've", "US", "IT", "AIDS", "NGO", "ECU", "LGBTQ"}
)


def allocate_counts(count: int, weights: Mapping[str, int]) -> Dict[str, float]:
    """Apportion estimates without rounding each document's small counts.

    Rounding here would systematically give the same spelling every tie across
    many short documents. Only the final corpus publication rounds estimates.
    """
    total = sum(weights.values())
    if not count or not total:
        return {}
    return {surface: count * weight / total for surface, weight in weights.items() if weight}


def resolve_spellings(
    stats: TextStats,
    evidence: Mapping[str, Counter[str]],
    known_spellings: Collection[str] = KNOWN_DISTINCT_SPELLINGS,
) -> Dict[str, float]:
    """Resolve sentence capitals and forced casing using corpus-wide evidence.

    Initial capitals can represent a lowercase or initial-capital word, never
    an unrelated acronym. Uppercase passages can represent any attested form.
    With no usable evidence, retain the counts under the lowercase matching key.
    """
    result: Dict[str, float] = {}

    def add_counts(counts: Mapping[str, float]) -> None:
        for surface, count in counts.items():
            result[surface] = result.get(surface, 0.0) + count

    for word in stats.counts:
        observed = stats.spelling_counts.get(word, Counter())
        add_counts(observed)
        corpus_forms = evidence.get(word, Counter())
        initial_form = word[:1].upper() + word[1:]
        initial_weights = {
            surface: corpus_forms[surface]
            for surface in (word, initial_form)
            if corpus_forms[surface]
        }
        default_form = initial_form if initial_form in known_spellings and len(word) == 1 else word
        if not initial_weights:
            initial_weights = {default_form: 1}
        add_counts(allocate_counts(stats.initial_counts[word], initial_weights))
        forced_weights = corpus_forms or Counter({default_form: 1})
        add_counts(allocate_counts(stats.forced_counts[word], forced_weights))
    return result


def pooled_spelling_evidence(stats_list: Collection[TextStats]) -> Dict[str, Counter[str]]:
    """Pool reliable spellings; ambiguous occurrences never reinforce themselves."""
    evidence: Dict[str, Counter[str]] = {}
    for stats in stats_list:
        for word, forms in stats.spelling_counts.items():
            evidence.setdefault(word, Counter()).update(forms)
    return evidence
