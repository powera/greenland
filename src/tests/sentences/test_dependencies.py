"""Tests for the Phase-4 Universal Dependencies pass.

The schema and the prompt are load-bearing in a way the decomposition ones are
not: a head is an integer index, so it is meaningless unless the prompt shows
the model the exact numbering it must index into, and unless the schema pins
the range those numbers may take. ``validate_dependency_tree`` is the last
guard before storage, and a partially valid tree is worse than none, so each
structural failure mode is pinned individually.
"""

from typing import Any, Dict, List

from langtools.ud_relations import (
    ROOT_HEAD_POSITION,
    UD_RELATIONS,
    is_valid_ud_relation,
    sorted_ud_relations,
)
from sentences.dependencies import (
    build_dependency_prompt,
    build_dependency_schema,
    validate_dependency_tree,
)


def _word(position: int, surface_form: str, part_of_speech: str) -> Dict[str, Any]:
    return {
        "position": position,
        "surface_form": surface_form,
        "part_of_speech": part_of_speech,
    }


# "He saw the dog": saw=root, he=nsubj->saw, dog=obj->saw, the=det->dog
_HE_SAW_THE_DOG_WORDS: List[Dict[str, Any]] = [
    _word(0, "He", "pronoun"),
    _word(1, "saw", "verb"),
    _word(2, "the", "article"),
    _word(3, "dog", "noun"),
]

_HE_SAW_THE_DOG_TREE: List[Dict[str, Any]] = [
    {"position": 0, "ud_relation": "nsubj", "ud_head_position": 1},
    {"position": 1, "ud_relation": "root", "ud_head_position": ROOT_HEAD_POSITION},
    {"position": 2, "ud_relation": "det", "ud_head_position": 3},
    {"position": 3, "ud_relation": "obj", "ud_head_position": 1},
]


def _tree_without(position: int) -> List[Dict[str, Any]]:
    return [entry for entry in _HE_SAW_THE_DOG_TREE if entry["position"] != position]


def _tree_with(position: int, **overrides: Any) -> List[Dict[str, Any]]:
    updated: List[Dict[str, Any]] = []
    for entry in _HE_SAW_THE_DOG_TREE:
        if entry["position"] == position:
            merged = dict(entry)
            merged.update(overrides)
            updated.append(merged)
        else:
            updated.append(dict(entry))
    return updated


# --------------------------------------------------------------------------- #
# Relation vocabulary                                                          #
# --------------------------------------------------------------------------- #


def test_core_relation_set_has_37_labels() -> None:
    assert len(UD_RELATIONS) == 37
    assert is_valid_ud_relation("nsubj")
    assert is_valid_ud_relation("root")
    # Enhanced subtypes are explicitly out of scope.
    assert not is_valid_ud_relation("nsubj:pass")
    assert not is_valid_ud_relation("")


# --------------------------------------------------------------------------- #
# Schema                                                                       #
# --------------------------------------------------------------------------- #


def _word_item_schema(word_count: int) -> Dict[str, Any]:
    schema = build_dependency_schema(word_count=word_count)
    items: Dict[str, Any] = schema["properties"]["words"]["items"]
    return items


def test_schema_relation_is_a_closed_enum_of_core_relations() -> None:
    """A free-string relation would let enhanced subtypes and typos through."""
    relation_schema = _word_item_schema(4)["properties"]["ud_relation"]
    assert set(relation_schema["enum"]) == set(UD_RELATIONS)
    assert relation_schema["enum"] == sorted_ud_relations()


def test_schema_head_bounds_span_root_through_last_position() -> None:
    """Out-of-range heads should be rejected by the provider, not by us."""
    word_count = 4
    head_schema = _word_item_schema(word_count)["properties"]["ud_head_position"]
    assert head_schema["minimum"] == ROOT_HEAD_POSITION
    assert head_schema["maximum"] == word_count - 1

    position_schema = _word_item_schema(word_count)["properties"]["position"]
    assert position_schema["minimum"] == 0
    assert position_schema["maximum"] == word_count - 1


def test_schema_caps_entries_at_the_token_count() -> None:
    """The upper bound is structural; the lower bound is left to validation.

    Pinning ``minItems`` to the word count too made a short answer a provider
    schema violation, which surfaces as an opaque API error instead of the
    "Missing positions: ..." message validate_dependency_tree can produce.
    """
    word_count = 7
    words_schema = build_dependency_schema(word_count=word_count)["properties"]["words"]
    assert words_schema["minItems"] == 1
    assert words_schema["maxItems"] == word_count
    assert set(words_schema["items"]["required"]) == {
        "position",
        "ud_relation",
        "ud_head_position",
    }


def test_short_dependency_response_is_caught_by_validation() -> None:
    """What the relaxed minItems delegates to validate_dependency_tree.

    The expected count has to be supplied: a truncated response is internally
    consistent, so inferring the count from the response itself makes a tree
    covering the first 3 of 4 words look like a complete 3-word tree.
    """
    complete: List[Dict[str, Any]] = [
        {"position": position, "ud_relation": "dep", "ud_head_position": 0} for position in range(4)
    ]
    complete[0]["ud_relation"] = "root"
    complete[0]["ud_head_position"] = ROOT_HEAD_POSITION
    assert validate_dependency_tree(complete, expected_word_count=4) == []

    truncated = complete[:-1]
    assert validate_dependency_tree(truncated) == []
    problems = validate_dependency_tree(truncated, expected_word_count=4)
    assert any("Missing positions: 3" in problem for problem in problems)


# --------------------------------------------------------------------------- #
# Prompt                                                                       #
# --------------------------------------------------------------------------- #


def test_prompt_renders_the_numbered_token_list() -> None:
    """Heads index into this list; without it the model has nothing to point at."""
    prompt = build_dependency_prompt(
        language_code="lt",
        sentence_text="Man reikia druskos sriubai.",
        words=[
            _word(0, "Man", "pronoun"),
            _word(1, "reikia", "verb"),
            _word(2, "druskos", "noun"),
            _word(3, "sriubai", "noun"),
        ],
    )

    for position, surface_form in enumerate(["Man", "reikia", "druskos", "sriubai"]):
        assert f"{position}  {surface_form}" in prompt

    assert "Man reikia druskos sriubai." in prompt
    assert "(verb)" in prompt
    assert "lt" in prompt


def test_prompt_numbers_tokens_by_their_stored_position() -> None:
    """List order is a fallback; a word's own position wins when present."""
    prompt = build_dependency_prompt(
        language_code="en",
        sentence_text="He saw the dog",
        words=[_word(5, "dog", "noun")],
    )
    assert "5  dog" in prompt
    assert "0  dog" not in prompt


# --------------------------------------------------------------------------- #
# Validation                                                                   #
# --------------------------------------------------------------------------- #


def test_valid_tree_has_no_problems() -> None:
    assert validate_dependency_tree(_HE_SAW_THE_DOG_TREE) == []


def test_no_root_is_rejected() -> None:
    tree = _tree_with(1, ud_relation="advcl", ud_head_position=3)
    problems = validate_dependency_tree(tree)
    assert any("No root" in problem for problem in problems)


def test_two_roots_are_rejected() -> None:
    tree = _tree_with(3, ud_relation="root", ud_head_position=ROOT_HEAD_POSITION)
    problems = validate_dependency_tree(tree)
    assert any("Multiple roots" in problem for problem in problems)


def test_out_of_range_head_is_rejected() -> None:
    tree = _tree_with(0, ud_head_position=9)
    problems = validate_dependency_tree(tree)
    assert any("out of range" in problem for problem in problems)


def test_self_loop_is_rejected() -> None:
    tree = _tree_with(0, ud_head_position=0)
    problems = validate_dependency_tree(tree)
    assert any("own head" in problem for problem in problems)


def test_cycle_is_rejected() -> None:
    """0 -> 2 -> 3 -> 0 never reaches the root, so nothing attaches to the sentence."""
    tree = _tree_with(0, ud_head_position=2)
    tree = [dict(entry, ud_head_position=0) if entry["position"] == 3 else entry for entry in tree]
    problems = validate_dependency_tree(tree)
    assert any("Cycle" in problem for problem in problems)


def test_duplicated_position_is_rejected() -> None:
    tree = _HE_SAW_THE_DOG_TREE + [
        {"position": 0, "ud_relation": "obl", "ud_head_position": 1},
    ]
    problems = validate_dependency_tree(tree)
    assert any("Duplicate position 0" in problem for problem in problems)


def test_missing_position_is_rejected() -> None:
    """Coverage is checked against the token count, not the returned count."""
    tree = _tree_without(2) + [
        {"position": 3, "ud_relation": "obj", "ud_head_position": 1},
    ]
    problems = validate_dependency_tree(tree)
    assert any("Duplicate position 3" in problem for problem in problems)
    assert any("Missing positions: 2" in problem for problem in problems)


def test_root_relation_and_root_head_must_agree() -> None:
    """A "root" label on a headed word, or head -1 without the label, is a parse error."""
    labelled_but_headed = _tree_with(0, ud_relation="root")
    assert any(
        "expected -1" in problem for problem in validate_dependency_tree(labelled_but_headed)
    )

    headed_but_unlabelled = _tree_with(1, ud_relation="obj")
    assert any(
        "expected 'root'" in problem for problem in validate_dependency_tree(headed_but_unlabelled)
    )


def test_non_integer_head_is_rejected() -> None:
    problems = validate_dependency_tree(_tree_with(0, ud_head_position="1"))
    assert any("Non-integer head" in problem for problem in problems)


def test_empty_word_list_is_rejected() -> None:
    assert validate_dependency_tree([]) == ["No words returned"]
