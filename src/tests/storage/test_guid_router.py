#!/usr/bin/python3

"""Tests for GUID well-formedness checking in :mod:`storage.guid_router`."""

from storage.guid_router import guid_kind, is_wellformed_guid


def test_wellformed_accepts_every_allocated_family() -> None:
    """Each prefix family in guid_prefixes.py is GUID-shaped."""
    assert is_wellformed_guid("N02_001")  # lemma (noun)
    assert is_wellformed_guid("V01_003")  # lemma (verb)
    assert is_wellformed_guid("A02_008")  # lemma (adjective)
    assert is_wellformed_guid("F01_003")  # phrase
    assert is_wellformed_guid("M01_001")  # idiom
    assert is_wellformed_guid("E04_012")  # name
    assert is_wellformed_guid("S_00077")  # sentence


def test_wellformed_rejects_non_guid_strings() -> None:
    """A word a user might type into the box is not a GUID.

    This is the case that motivated the function: ``guid_kind`` falls back to
    "lemma" for anything unrecognized, so without a separate check "banana"
    reported as a lemma GUID that was never issued.
    """
    assert not is_wellformed_guid("banana")
    assert not is_wellformed_guid("")
    assert not is_wellformed_guid("apple pie")
    # A separator but no number after it.
    assert not is_wellformed_guid("N02_")
    assert not is_wellformed_guid("N02_abc")
    # A number but no separator.
    assert not is_wellformed_guid("N02001")
    # A prefix that does not start with a letter.
    assert not is_wellformed_guid("02N_001")
    assert not is_wellformed_guid("_001")


def test_wellformed_accepts_unallocated_but_valid_shapes() -> None:
    """An unissued number is a missing record, not a malformed string.

    The check is deliberately about shape, not about whether the prefix is
    allocated: "N98_001" should get the "never issued" answer, which is
    accurate, rather than being called a typo.
    """
    assert is_wellformed_guid("N98_001")
    assert is_wellformed_guid("N04_999")
    assert is_wellformed_guid("Z99_123")


def test_wellformed_is_independent_of_guid_kind() -> None:
    """Strings guid_kind() calls "lemma" as a fallback are still malformed.

    ``guid_kind`` must stay total for routing, so these keep returning "lemma";
    the two functions answer different questions and both behaviors are correct.
    """
    for candidate in ("MISC_001", "M_001", "M01001"):
        assert guid_kind(candidate) == "lemma"

    # "M_001" is a single-letter prefix plus digits, which is the sentence
    # shape, so it is well-formed even though it routes as a lemma.
    assert is_wellformed_guid("M_001")
    # These two are genuinely malformed.
    assert not is_wellformed_guid("MISC_001")
    assert not is_wellformed_guid("M01001")
