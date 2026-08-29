"""Tests for the YAML article lists behind the ``wiki_*`` corpora.

These assert on the loader and on properties every list must hold, rather than
on the titles themselves: the lists are fetched data and their counts move when
the upstream page is re-fetched, so a hardcoded total would go stale.
"""

from typing import Dict, List

import pytest

from wordfreq.corpora.wikipedia.article_lists import (
    flatten,
    load_list,
    load_lists,
    load_redactions,
)

ALL_LISTS = [
    "arts",
    "math",
    "geography",
    "biology",
    "everyday_life",
    "technology",
    "society",
    "philosophy_religion",
    "physical_sciences",
    "molecular_biology",
    "history",
    "people",
]


@pytest.mark.parametrize("name", ALL_LISTS)
def test_every_list_loads_and_is_non_empty(name: str) -> None:
    """A list file parses, and every group in it has titles."""
    groups = load_list(name)
    assert groups, f"{name} loaded empty"
    for group, titles in groups.items():
        assert titles, f"{name}: group {group!r} is empty"
        assert all(isinstance(title, str) and title for title in titles)


@pytest.mark.parametrize("name", ALL_LISTS)
def test_titles_are_unique_within_a_list(name: str) -> None:
    """One article must not be counted twice by the same corpus."""
    titles = [title for group in load_list(name).values() for title in group]
    duplicates = {title for title in titles if titles.count(title) > 1}
    assert not duplicates, f"{name}: duplicate titles {sorted(duplicates)}"


@pytest.mark.parametrize("name", ALL_LISTS)
def test_titles_carry_no_wiki_markup(name: str) -> None:
    """A title is an exact page title, not a wikilink or a template.

    wiki_dump looks a page up by exact title, so markup left in by the
    extractor would be a silent miss rather than an error.
    """
    for group, titles in load_list(name).items():
        for title in titles:
            for markup in ("[[", "]]", "{{", "}}", "|", "#"):
                assert markup not in title, f"{name}/{group}: {title!r} holds {markup!r}"
            assert title == title.strip(), f"{title!r} has surrounding whitespace"
            assert not title.startswith(
                ("Wikipedia:", "Category:", "File:", "Image:", "Portal:", "Template:")
            ), f"{name}/{group}: {title!r} is not an article"


def test_redactions_are_applied() -> None:
    """A redacted title must not reach any list."""
    redactions = load_redactions()
    assert redactions, "no redactions declared"
    for name in ALL_LISTS:
        titles = set(flatten(load_list(name)))
        assert not titles & set(redactions), f"{name} contains a redacted title"


def test_redactions_carry_a_reason() -> None:
    """The reason is the point of the file: a bare list would lose it."""
    for title, reason in load_redactions().items():
        assert isinstance(reason, str) and len(reason.strip()) > 20, title


def test_load_lists_merges_in_order() -> None:
    """Merging is how a corpus spans two upstream pages."""
    merged = load_lists("physical_sciences", "molecular_biology")
    physical = flatten(load_list("physical_sciences"))
    molecular = flatten(load_list("molecular_biology"))
    assert set(flatten(merged)) == set(physical) | set(molecular)


def test_load_lists_can_prefix_group_names() -> None:
    """Prefixing keeps a gap visible when two lists share a section name."""
    merged = load_lists("society", "philosophy_religion", prefix_groups=True)
    assert all(group.startswith(("society: ", "philosophy_religion: ")) for group in merged)


def test_flatten_drops_duplicates_across_groups() -> None:
    """A title in two groups of a merged list is one article, counted once."""
    groups: Dict[str, List[str]] = {"a": ["One", "Two"], "b": ["Two", "Three"]}
    assert flatten(groups) == ["One", "Two", "Three"]


def test_unknown_list_raises() -> None:
    """A typo in a corpus definition must fail loudly."""
    with pytest.raises(FileNotFoundError):
        load_list("no_such_list")
