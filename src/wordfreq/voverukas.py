"""Voverukas ranking: a PageRank-variant over the concept wiki-link graph.

This is a typed, in-memory port of the "Powerrank" algorithm from the slmt
project. It ranks topics by importance: starting from a seed set of nodes with
equal mass, it iteratively disperses each node's rank to the targets it links
to, so a topic referenced by many high-importance topics accumulates a high
score.

In greenland-mint the nodes are :class:`~storage.models.concept.Concept` slugs
and the edges are the ``[[wiki links]]`` inside concept bodies. Targets that are
linked-to but have no concept yet ("red links" / wanted slugs) still receive
rank, which lets callers prioritise *which* missing topics to create next.

The module is pure: it performs no I/O and depends only on a link graph
(``{source_slug -> [target_slug, ...]}``) supplied by the caller. Build that
graph from concept bodies with
:func:`~storage.models.concept.parse_wiki_links`.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

# Defaults mirror the original slmt Powerrank tuning: each node retains a fifth
# of its rank and disperses 85% across its out-links (the remainder is lost at
# dead-ends, which is acceptable for a relative ranking).
DEFAULT_ITERATIONS: int = 4
DEFAULT_DAMPING: float = 0.85
DEFAULT_RETENTION: float = 0.2
DEFAULT_SEED_MASS: float = 1.0
# Round dispersed rank like the original to keep float noise out of the scores.
_RANK_PRECISION: int = 6


class VoverukasRank:
    """An accumulator of per-slug rank scores.

    Replaces the file-backed ``PowerRankFile`` from slmt: scores live entirely
    in memory because greenland-mint recomputes the ranking on demand rather
    than persisting generations to disk.
    """

    def __init__(self) -> None:
        self.scores: Dict[str, float] = {}

    def add(self, slug: str, amount: float) -> None:
        """Add ``amount`` to ``slug``'s running score (creating it if new)."""
        self.scores[slug] = self.scores.get(slug, 0.0) + amount

    def get(self, slug: str) -> float:
        """Return the current score for ``slug`` (0.0 if absent)."""
        return self.scores.get(slug, 0.0)

    def slugs(self) -> Iterable[str]:
        """Return an iterable over all scored slugs."""
        return self.scores.keys()

    def top(self, n: int = 1000) -> List[Tuple[str, float]]:
        """Return the ``n`` highest-scoring ``(slug, score)`` pairs, descending.

        Ties are broken by slug for a stable, reproducible ordering.
        """
        ranked = sorted(self.scores.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:n]


def _disperse(
    current: VoverukasRank,
    link_graph: Mapping[str, Sequence[str]],
    *,
    damping: float,
    retention: float,
) -> VoverukasRank:
    """Run a single dispersion pass, returning the next generation's ranks."""
    nxt = VoverukasRank()
    for slug, rank in current.scores.items():
        if rank == 0.0:
            continue
        # A fraction of the rank always stays put.
        nxt.add(slug, retention * rank)

        links = list(link_graph.get(slug, ()))
        if not links:
            # Dead-end node: its dispersible share is simply lost.
            continue

        share = round(damping * rank / len(links), _RANK_PRECISION)
        for target in links:
            # A self-link folds back onto the node itself.
            nxt.add(target if target else slug, share)
    return nxt


def compute_ranks(
    link_graph: Mapping[str, Sequence[str]],
    seeds: Iterable[str],
    *,
    iterations: int = DEFAULT_ITERATIONS,
    damping: float = DEFAULT_DAMPING,
    retention: float = DEFAULT_RETENTION,
    seed_mass: float = DEFAULT_SEED_MASS,
) -> VoverukasRank:
    """Rank nodes by importance over a wiki-link graph.

    Args:
        link_graph: Mapping of source slug to the slugs it links to. Slugs that
            never appear as a key are treated as dead-ends (they accumulate
            rank but disperse none).
        seeds: The starting node set, each given equal ``seed_mass``. In
            greenland-mint this is the set of existing concept slugs.
        iterations: Number of dispersion passes to run.
        damping: Fraction of a node's rank dispersed across its out-links.
        retention: Fraction of a node's rank that stays on the node.
        seed_mass: Initial score assigned to every seed node.

    Returns:
        A :class:`VoverukasRank` with the final scores. Both seed nodes and any
        linked-to targets (including red links absent from ``seeds``) are
        present.
    """
    ranks = VoverukasRank()
    for seed in seeds:
        ranks.add(seed, seed_mass)

    for _ in range(max(0, iterations)):
        ranks = _disperse(ranks, link_graph, damping=damping, retention=retention)

    return ranks


def build_link_graph(
    bodies_by_slug: Mapping[str, str],
) -> Tuple[Dict[str, List[str]], Dict[str, int]]:
    """Build a link graph and inbound-link counts from concept bodies.

    Args:
        bodies_by_slug: Mapping of concept slug to its body text (Markdown with
            ``[[wiki links]]``). A ``None``/empty body contributes no edges.

    Returns:
        A tuple ``(link_graph, inbound_counts)`` where ``link_graph`` maps each
        source slug to its list of target slugs (in order of appearance, with
        duplicates preserved so multiple references weight more), and
        ``inbound_counts`` maps each target slug to the number of distinct
        concepts that link to it.
    """
    # Imported here to keep the algorithm core import-light and dependency-free
    # for callers that already hold a precomputed graph.
    from storage.models.concept import parse_wiki_links

    link_graph: Dict[str, List[str]] = {}
    inbound_counts: Dict[str, int] = {}
    for slug, body in bodies_by_slug.items():
        targets = [link.target_slug for link in parse_wiki_links(body or "") if link.target_slug]
        link_graph[slug] = targets
        for target in set(targets):
            inbound_counts[target] = inbound_counts.get(target, 0) + 1
    return link_graph, inbound_counts
