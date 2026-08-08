"""Tests for POS subtype helpers in storage.utils.enums.

The subtype vocabularies themselves live in models/enums.py and
models/guid_prefixes.py and change whenever a category is added. Nothing here
asserts that a particular subtype exists; the tests cover the dispatch logic and
the consistency contract between the two sources of subtype truth.
"""

from __future__ import annotations

import enum
from typing import Iterable, cast

import pytest

from storage.models.guid_prefixes import SUBTYPE_GUID_PREFIXES
from storage.utils.enums import (
    VALID_POS_TYPES,
    get_all_pos_subtypes,
    get_subtype_enum,
    get_subtype_values_for_pos,
)

# POS types that carry a dedicated Subtype enum class.
ENUM_BACKED_POS_TYPES = ["noun", "verb", "adjective", "adverb", "numeral"]


@pytest.mark.parametrize("pos_type", ENUM_BACKED_POS_TYPES)
def test_enum_backed_pos_types_resolve_to_an_enum(pos_type: str) -> None:
    assert get_subtype_enum(pos_type) is not None


def test_pos_type_lookup_is_case_insensitive() -> None:
    assert get_subtype_enum("NOUN") is get_subtype_enum("noun")


def test_unknown_pos_type_has_no_enum_and_no_subtypes() -> None:
    assert get_subtype_enum("not_a_pos_type") is None
    assert get_subtype_values_for_pos("not_a_pos_type") == []


@pytest.mark.parametrize("pos_type", ENUM_BACKED_POS_TYPES)
def test_enum_backed_subtypes_come_from_the_enum(pos_type: str) -> None:
    """For enum-backed POS types the enum is authoritative, not the GUID table."""
    enum_class = get_subtype_enum(pos_type)
    assert enum_class is not None
    expected = [member.value for member in cast(Iterable[enum.Enum], enum_class)]

    assert get_subtype_values_for_pos(pos_type) == expected


def test_non_enum_pos_types_fall_back_to_guid_prefixes() -> None:
    """POS types without an enum still report subtypes, sourced from the registry.

    Exercised over every such POS type in the registry so a newly added one is
    covered automatically.
    """
    fallback_pos_types = [
        pos_type for pos_type in SUBTYPE_GUID_PREFIXES if get_subtype_enum(pos_type) is None
    ]
    assert fallback_pos_types, "expected at least one POS type without a subtype enum"

    for pos_type in fallback_pos_types:
        assert get_subtype_values_for_pos(pos_type) == list(SUBTYPE_GUID_PREFIXES[pos_type])


def _subtypes_without_enum_members() -> set[str]:
    """GUID-prefixed subtypes that no enum or fallback exposes as a value."""
    all_subtypes = set(get_all_pos_subtypes())
    return {
        subtype
        for subtypes in SUBTYPE_GUID_PREFIXES.values()
        for subtype in subtypes
        if subtype not in all_subtypes
    }


def test_only_catch_all_subtypes_lack_an_enum_member() -> None:
    """A prefixed subtype with no enum member can never be assigned by name.

    This is the invariant the note at the top of guid_prefixes.py asks for. The
    "<pos>_other" buckets are the accepted exception: they are reachable by GUID
    but deliberately not offered as classification choices. Any *other* subtype
    here means the prefix table and the enum disagree on a name, so generate_guid
    rejects the value the enum tells callers to use.
    """
    unexpected = {
        subtype for subtype in _subtypes_without_enum_members() if not subtype.endswith("_other")
    }

    assert not unexpected, f"GUID-prefixed subtypes with no matching enum member: {unexpected}"


def test_every_enum_subtype_can_be_allocated_a_guid() -> None:
    """The enum's values are exactly what callers pass to generate_guid.

    Asserted over every enum-backed POS type, so a subtype added to an enum
    without a GUID prefix (or keyed differently in the prefix table, as
    adverb "duration" once was) fails here.
    """
    for pos_type in ENUM_BACKED_POS_TYPES:
        prefixes = SUBTYPE_GUID_PREFIXES[pos_type]
        for subtype in get_subtype_values_for_pos(pos_type):
            if subtype == "other":
                # The bare "other" enum member is keyed "<pos>_other" in the
                # prefix table; covered by the catch-all test above.
                continue
            assert subtype in prefixes, f"{pos_type} subtype {subtype!r} has no GUID prefix"


def test_catch_all_subtypes_are_prefixed_consistently() -> None:
    """Every POS type's catch-all follows the same "<pos>_other" naming."""
    for subtype in _subtypes_without_enum_members():
        if subtype.endswith("_other"):
            pos_type = subtype.removesuffix("_other")
            assert subtype in SUBTYPE_GUID_PREFIXES.get(pos_type, {})


def test_guid_prefixes_are_unique_within_a_pos_type() -> None:
    """Two subtypes sharing a prefix would share a GUID number sequence."""
    for pos_type, subtypes in SUBTYPE_GUID_PREFIXES.items():
        prefixes = list(subtypes.values())
        assert len(prefixes) == len(set(prefixes)), f"duplicate GUID prefix in {pos_type}"


def test_get_all_pos_subtypes_is_sorted_and_includes_bare_pos_types() -> None:
    all_subtypes = get_all_pos_subtypes()

    assert all_subtypes == sorted(set(all_subtypes))
    assert VALID_POS_TYPES <= set(all_subtypes)
