"""Nesting the UD head graph into a displayable tree.

The tree is built from data the database cannot guarantee is well-formed: rows
may predate Phase-4 validation, a language may be partially annotated, and a
head may name a position that no longer exists. The template renders the result
with a *recursive* macro, so a cycle that survives into the nested structure
does not merely look wrong — it never terminates and takes down the page. These
tests pin that every malformed shape still yields a finite tree containing every
annotated word exactly once.
"""

from typing import Any, Dict, List

from barsukas.routes.sentences import _build_dependency_tree
from langtools.ud_relations import ROOT_HEAD_POSITION


def _word(position: int, relation: Any, head: Any, surface: str = "w") -> Dict[str, Any]:
    return {
        "position": position,
        "target_text": surface,
        "part_of_speech": "noun",
        "ud_relation": relation,
        "ud_head_position": head,
    }


def _flatten(nodes: List[Dict[str, Any]], depth: int = 0) -> List[int]:
    """Walk the tree, asserting it is finite and no node is reachable twice."""
    assert depth < 50, "tree nested implausibly deep — probable cycle"
    positions: List[int] = []
    for node in nodes:
        positions.append(node["word"]["position"])
        positions.extend(_flatten(node["children"], depth + 1))
    return positions


# "The child found a green ball." — the real sentence 18 English parse.
_SENTENCE_18: List[Dict[str, Any]] = [
    _word(0, "det", 1, "The"),
    _word(1, "nsubj", 2, "child"),
    _word(2, "root", ROOT_HEAD_POSITION, "found"),
    _word(3, "det", 5, "a"),
    _word(4, "amod", 5, "green"),
    _word(5, "obj", 2, "ball"),
]


def test_well_formed_tree_nests_under_the_root() -> None:
    tree = _build_dependency_tree(_SENTENCE_18)

    assert len(tree) == 1
    root = tree[0]
    assert root["word"]["target_text"] == "found"

    # child <- The, ball <- a, green
    child, ball = root["children"]
    assert child["word"]["target_text"] == "child"
    assert [c["word"]["target_text"] for c in child["children"]] == ["The"]
    assert ball["word"]["target_text"] == "ball"
    assert [c["word"]["target_text"] for c in ball["children"]] == ["a", "green"]

    assert sorted(_flatten(tree)) == [0, 1, 2, 3, 4, 5]


def test_unannotated_language_yields_no_tree() -> None:
    """Sentences decomposed before Phase 4 existed must simply omit the view."""
    assert _build_dependency_tree([_word(0, None, None)]) == []


def test_partially_annotated_language_keeps_only_annotated_words() -> None:
    tree = _build_dependency_tree([_word(0, "root", ROOT_HEAD_POSITION), _word(1, None, None)])
    assert _flatten(tree) == [0]


def test_two_element_cycle_is_broken_and_flagged() -> None:
    """0 -> 1 -> 0 would otherwise nest forever in the recursive macro."""
    tree = _build_dependency_tree(
        [_word(0, "obj", 1), _word(1, "nmod", 0), _word(2, "root", ROOT_HEAD_POSITION)]
    )

    assert sorted(_flatten(tree)) == [0, 1, 2]
    assert any(node.get("orphaned") for node in tree)


def test_cycle_with_no_root_at_all_still_renders_every_word() -> None:
    tree = _build_dependency_tree([_word(0, "obj", 1), _word(1, "nmod", 2), _word(2, "obj", 0)])
    assert sorted(_flatten(tree)) == [0, 1, 2]


def test_self_loop_becomes_a_flagged_root() -> None:
    tree = _build_dependency_tree([_word(0, "obj", 0), _word(1, "root", ROOT_HEAD_POSITION)])
    assert sorted(_flatten(tree)) == [0, 1]
    assert any(node.get("orphaned") for node in tree)


def test_head_naming_a_missing_position_becomes_a_flagged_root() -> None:
    tree = _build_dependency_tree([_word(0, "obj", 99), _word(1, "root", ROOT_HEAD_POSITION)])
    assert sorted(_flatten(tree)) == [0, 1]
    assert any(node.get("orphaned") for node in tree)


def test_multiple_roots_are_all_returned_unflagged() -> None:
    """Two heads of -1 is an invalid parse, but each is a legitimate root here."""
    tree = _build_dependency_tree(
        [_word(0, "root", ROOT_HEAD_POSITION), _word(1, "root", ROOT_HEAD_POSITION)]
    )
    assert sorted(_flatten(tree)) == [0, 1]
    assert not any(node.get("orphaned") for node in tree)
