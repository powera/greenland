"""Tests for the verb/noun-subtype co-occurrence scoring."""

from __future__ import annotations

from typing import Dict, List

from wordfreq.corpora.cooccurrence import (
    HARDCODED_VERB_LEVELS,
    Affinity,
    CooccurrenceCounts,
    count_document,
    iter_windows,
    score_affinity,
    top_verbs_for_subtype,
    verb_clusters,
)

VERBS: Dict[str, str] = {"eat": "physical_action", "drink": "physical_action"}
NOUNS: Dict[str, str] = {
    "bread": "food",
    "apple": "food",
    "water": "beverage",
    "idea": "concept_idea",
}


def test_iter_windows_only_looks_forward() -> None:
    """A noun before the verb is not the verb's object."""
    tokens = ["bread", "eat", "water"]
    assert list(iter_windows(tokens, VERBS, NOUNS, window=2)) == [("eat", "beverage")]


def test_iter_windows_stops_at_end_of_tokens() -> None:
    """A verb near the end contributes fewer pairs rather than overrunning."""
    tokens = ["eat", "bread"]
    assert list(iter_windows(tokens, VERBS, NOUNS, window=6)) == [("eat", "food")]


def test_iter_windows_respects_window_size() -> None:
    """A noun beyond the window is out of reach."""
    tokens = ["eat", "x", "y", "z", "bread"]
    assert list(iter_windows(tokens, VERBS, NOUNS, window=2)) == []
    assert list(iter_windows(tokens, VERBS, NOUNS, window=4)) == [("eat", "food")]


def test_excluded_forms_are_skipped_on_both_sides() -> None:
    """An excluded token is neither a verb to score nor evidence for one."""
    tokens = ["eat", "have", "bread"]
    pairs = list(iter_windows(tokens, VERBS, NOUNS, window=6, excluded=frozenset({"have"})))
    assert pairs == [("eat", "food")]

    verbs_with_have = {**VERBS, "have": "possession"}
    pairs = list(
        iter_windows(tokens, verbs_with_have, NOUNS, window=6, excluded=frozenset({"have"}))
    )
    # "have" contributes nothing of its own, and "eat" still reaches bread.
    assert pairs == [("eat", "food")]


def test_merge_combines_counts() -> None:
    first = CooccurrenceCounts()
    count_document(["eat", "bread"], VERBS, NOUNS, first)
    second = CooccurrenceCounts()
    count_document(["eat", "apple"], VERBS, NOUNS, second)

    first.merge(second)
    assert first.verb_totals["eat"] == 2
    assert first.pair_counts["eat"]["food"] == 2
    assert first.subtype_totals["food"] == 2
    assert first.documents_scanned == 2


def test_lift_ranks_specific_pairing_above_frequent_generic_one() -> None:
    """The point of lift: a big ambient subtype must not win on raw count.

    "idea" (concept_idea) follows every verb here and outnumbers "water"
    overall, so a raw-share ranking would put concept_idea first for "drink".
    Scoring against each subtype's base rate is what puts beverage on top.
    """
    counts = CooccurrenceCounts()
    for _ in range(20):
        # "idea" is ambient: it follows both verbs, and twice per window for
        # "drink", so it beats beverage on raw count even for the verb whose
        # real object is water.
        count_document(["eat", "idea", "idea"], VERBS, NOUNS, counts)
        count_document(["drink", "water", "idea", "idea"], VERBS, NOUNS, counts)

    scored = score_affinity(counts, min_verb_count=5, min_pair_count=5)
    drink_top = scored["drink"][0]
    assert drink_top.subtype == "beverage"

    by_count = sorted(counts.pair_counts["drink"].items(), key=lambda pair: -pair[1])
    assert by_count[0][0] == "concept_idea", "raw counts should favour the ambient subtype"


def test_score_affinity_skips_thin_evidence() -> None:
    counts = CooccurrenceCounts()
    count_document(["eat", "bread"], VERBS, NOUNS, counts)
    assert score_affinity(counts, min_verb_count=30, min_pair_count=5) == {}


def test_top_verbs_for_subtype_reads_the_scores_by_group() -> None:
    counts = CooccurrenceCounts()
    for _ in range(20):
        count_document(["eat", "bread"], VERBS, NOUNS, counts)
        count_document(["drink", "water"], VERBS, NOUNS, counts)

    scored = score_affinity(counts, min_verb_count=5, min_pair_count=5)
    food_verbs = [affinity.verb for affinity in top_verbs_for_subtype(scored, "food")]
    assert food_verbs == ["eat"]


def test_verb_clusters_group_by_shared_profile() -> None:
    scored: Dict[str, List[Affinity]] = {
        "eat": [Affinity("eat", "food", 10, 0.9, 5.0)],
        "cook": [Affinity("cook", "food", 10, 0.9, 4.0)],
        "drive": [Affinity("drive", "vehicle", 10, 0.9, 6.0)],
    }
    clusters = verb_clusters(scored, top_n=1, min_lift=1.5)
    assert clusters[("food",)] == ["cook", "eat"]
    assert clusters[("vehicle",)] == ["drive"]


def test_hardcoded_verbs_are_named_and_not_derived() -> None:
    """These verbs are placed by hand; see the module docstring."""
    assert set(HARDCODED_VERB_LEVELS) == {"be", "have", "like"}
    assert all(level > 0 for level in HARDCODED_VERB_LEVELS.values())


def test_do_is_not_hardcoded() -> None:
    """'do' is deliberately absent, and the comment saying so must stay true.

    Unlike "be" and "have" it has no teachable content sense -- its uses are
    auxiliary, emphatic and pro-verb -- so it is not in the lemma table and
    must not be given a level here.
    """
    assert "do" not in HARDCODED_VERB_LEVELS
