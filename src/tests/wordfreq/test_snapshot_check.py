"""Tests for checking article-list titles against a dump snapshot.

The real snapshot is a 21GB dump on an external drive, so every test here uses
a fake loader: what is under test is the reporting, not the dump reader.
"""

from __future__ import annotations

from typing import Dict, Set, Tuple

from wordfreq.corpora.wikipedia.snapshot_check import (
    check_groups,
    check_titles,
    resolve_candidates,
    resolve_redirect,
    title_exists,
)


class _FakeLoader:
    """Stands in for WikiLoader with an in-memory page table."""

    def __init__(self, pages: Dict[str, str]) -> None:
        self._pages = pages

    def get_offset_for_page(self, page_name: str) -> Tuple[int, int]:
        if page_name not in self._pages:
            raise ValueError(f"Page not found in index: {page_name}")
        return (0, len(self._pages[page_name]))

    def get_text_from_page(self, page_name: str) -> str:
        return self._pages[page_name]


def _loader(**pages: str) -> _FakeLoader:
    return _FakeLoader(dict(pages))


def test_title_exists_reports_index_membership() -> None:
    loader = _loader(Vowel="a vowel is...")
    assert title_exists("Vowel", loader)  # type: ignore[arg-type]
    assert not title_exists("Nonexistent", loader)  # type: ignore[arg-type]


def test_check_titles_lists_only_the_missing_ones() -> None:
    loader = _loader(Vowel="...", Consonant="...")
    report = check_titles(["Vowel", "Consonant", "Sprachbund"], loader)  # type: ignore[arg-type]
    assert report.checked == 3
    assert report.found == 2
    assert report.missing == ["Sprachbund"]


def test_summary_says_so_when_everything_resolves() -> None:
    loader = _loader(Vowel="...")
    report = check_titles(["Vowel"], loader)  # type: ignore[arg-type]
    assert report.summary() == "all 1 titles resolve against the snapshot"


def test_summary_counts_the_misses() -> None:
    loader = _loader(Vowel="...")
    report = check_titles(["Vowel", "Gone"], loader)  # type: ignore[arg-type]
    assert "1/2" in report.summary()
    assert "1 missing" in report.summary()


def test_check_groups_keeps_only_groups_with_misses() -> None:
    """Five misses in one section usually means the section was renamed."""
    loader = _loader(Vowel="...", Grammar="...")
    groups = {
        "Phonetics": ["Vowel"],
        "Grammar": ["Grammar", "Declension", "Inflection"],
    }
    missing = check_groups(groups, loader)  # type: ignore[arg-type]
    assert missing == {"Grammar": ["Declension", "Inflection"]}


def test_resolve_redirect_reports_an_article() -> None:
    loader = _loader(**{"Comparison (grammar)": "x" * 500})
    resolution = resolve_redirect("Comparison (grammar)", loader)  # type: ignore[arg-type]
    assert resolution.exists
    assert resolution.is_article
    assert resolution.redirect_target is None
    assert resolution.size == 500


def test_resolve_redirect_reports_the_target() -> None:
    loader = _loader(
        **{"Degree of comparison": "#REDIRECT [[Comparison (grammar)]]"},
    )
    resolution = resolve_redirect("Degree of comparison", loader)  # type: ignore[arg-type]
    assert resolution.exists
    assert not resolution.is_article
    assert resolution.redirect_target == "Comparison (grammar)"


def test_redirect_syntax_variations_are_recognized() -> None:
    """Case, spacing and a section suffix all appear in real dumps."""
    for text in (
        "#redirect [[Target]]",
        "#REDIRECT[[Target]]",
        "#REDIRECT [[Target#Section]]",
        "#REDIRECT [[Target|label]]",
    ):
        loader = _loader(Source=text)
        assert resolve_redirect("Source", loader).redirect_target == "Target"  # type: ignore[arg-type]


def test_a_missing_title_resolves_to_absent_rather_than_raising() -> None:
    loader = _loader(Other="...")
    resolution = resolve_redirect("Absent", loader)  # type: ignore[arg-type]
    assert not resolution.exists
    assert not resolution.is_article
    assert resolution.size is None


def test_resolve_candidates_ranks_the_options_for_a_rename() -> None:
    """The curation step: which spelling did the snapshot use, and is it a stub?"""
    loader = _loader(
        **{
            "Burmese alphabet": "x" * 44000,
            "Mon script": "x" * 11000,
        }
    )
    resolutions = resolve_candidates(
        ["Burmese alphabet", "Mon script", "Mon-Burmese script"], loader  # type: ignore[arg-type]
    )
    by_title = {resolution.title: resolution for resolution in resolutions}
    assert by_title["Burmese alphabet"].size == 44000
    assert by_title["Mon script"].size == 11000
    assert not by_title["Mon-Burmese script"].exists
