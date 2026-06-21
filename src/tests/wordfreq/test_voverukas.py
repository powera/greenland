"""Tests for wordfreq.voverukas — the concept link-graph ranking algorithm
(a typed port of slmt's "Powerrank")."""

from __future__ import annotations

from typing import Dict, List

from wordfreq.voverukas import VoverukasRank, build_link_graph, compute_ranks


def _rank_order(link_graph: Dict[str, List[str]], seeds: List[str]) -> List[str]:
    """Return ranked slugs (descending) for a tiny graph, for readable asserts."""
    ranks = compute_ranks(link_graph, seeds)
    return [slug for slug, _score in ranks.top(n=len(ranks.scores))]


def test_more_referenced_target_outranks_less_referenced() -> None:
    """A red link cited by many seeds outranks one cited by few."""
    # Three seed concepts all link to "Popular"; only one links to "Obscure".
    link_graph = {
        "A": ["Popular"],
        "B": ["Popular"],
        "C": ["Popular", "Obscure"],
    }
    ranks = compute_ranks(link_graph, ["A", "B", "C"])
    assert ranks.get("Popular") > ranks.get("Obscure")


def test_dead_end_node_does_not_crash() -> None:
    """A node with no out-links disperses nothing and is handled gracefully."""
    link_graph = {"A": ["B"]}  # "B" is a dead-end (never a key).
    ranks = compute_ranks(link_graph, ["A"])
    # B accumulated rank from A; running more iterations must not error.
    assert ranks.get("B") > 0.0
    more = compute_ranks(link_graph, ["A"], iterations=10)
    assert more.get("B") > 0.0


def test_self_link_folds_back_onto_node() -> None:
    """An empty-string link target folds rank back onto the source node."""
    # parse_wiki_links normalizes "#section" anchors to empty targets upstream;
    # here we exercise the algorithm's self-link handling directly.
    link_graph = {"A": [""]}
    ranks = compute_ranks(link_graph, ["A"], iterations=2)
    # All rank stays on A (retention + the self-directed share), nothing leaks.
    assert set(ranks.slugs()) == {"A"}
    assert ranks.get("A") > 0.0


def test_top_is_descending_and_tie_broken_by_slug() -> None:
    """top() sorts by score descending, ties broken alphabetically by slug."""
    ranks = VoverukasRank()
    ranks.add("zebra", 1.0)
    ranks.add("apple", 1.0)
    ranks.add("middle", 2.0)
    assert ranks.top() == [("middle", 2.0), ("apple", 1.0), ("zebra", 1.0)]


def test_build_link_graph_counts_distinct_inbound() -> None:
    """build_link_graph parses bodies and counts distinct referencing concepts."""
    bodies = {
        "Alpha": "See [[Gamma]] and [[Gamma]] again.",  # duplicate -> still 1 inbound
        "Beta": "Also [[Gamma]] and [[Delta]].",
        "Empty": "",
    }
    link_graph, inbound = build_link_graph(bodies)
    # Duplicates preserved in the edge list (weight), counted once for inbound.
    assert link_graph["Alpha"] == ["Gamma", "Gamma"]
    assert link_graph["Empty"] == []
    assert inbound["Gamma"] == 2  # Alpha + Beta
    assert inbound["Delta"] == 1  # Beta only


def test_red_links_are_present_but_excluded_from_seeds() -> None:
    """Targets absent from the seed set still receive rank (they are red links)."""
    bodies = {
        "Alpha": "Links to [[Wanted]].",
        "Beta": "Also links to [[Wanted]].",
    }
    link_graph, _inbound = build_link_graph(bodies)
    seeds = list(bodies.keys())
    ranks = compute_ranks(link_graph, seeds)
    # "Wanted" is not a seed/concept, but it is ranked.
    assert "Wanted" in set(ranks.slugs())
    assert "Wanted" not in seeds
    assert ranks.get("Wanted") > 0.0
