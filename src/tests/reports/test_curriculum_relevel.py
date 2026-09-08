"""Unit tests for the temporary curriculum proposal builder."""

from reports.curriculum_relevel import _balanced_sizes


def test_balanced_sizes_stay_near_target() -> None:
    sizes = _balanced_sizes(2242, 50)

    assert sum(sizes) == 2242
    assert min(sizes) == 44
    assert max(sizes) == 45


def test_balanced_sizes_split_oversized_cohort() -> None:
    assert _balanced_sizes(92, 2) == [46, 46]
