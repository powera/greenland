"""Tests for the wikitext cache in :mod:`wordfreq.corpora.wikipedia.wiki_dump`.

The dump itself is a 21GB snapshot on an external drive, so these never read
it: :meth:`WikiLoader._read_page_from_dump` is stubbed and the tests assert on
how often it is consulted.  What is covered is the cache around it -- the part
that decides whether a build re-reads the dump at all.
"""

import os
from typing import Dict, List

import pytest

from wordfreq.corpora.wikipedia.wiki_dump import WikiLoader


class _FakeDump:
    """Stands in for the dump, counting the pages actually read from it."""

    def __init__(self, pages: Dict[str, str]) -> None:
        self.pages = pages
        self.reads: List[str] = []

    def __call__(self, page_name: str) -> str:
        self.reads.append(page_name)
        if page_name not in self.pages:
            raise ValueError(f"Page {page_name} not found")
        return self.pages[page_name]


@pytest.fixture
def loader(tmp_path, monkeypatch):
    """A loader whose cache is a temp directory and whose dump is a fake."""
    # set_corpus_base touches only paths, but constructing a WikiLoader reads
    # module-level constants; the cache directory is the only one these tests
    # care about.
    instance = WikiLoader(cache_dir=str(tmp_path / "wiki_cache"))
    dump = _FakeDump(
        {
            "Photosynthesis": "Plants convert light.",
            "AC/DC": "An Australian rock band.",
            "Nul (band)": "A disambiguated title.",
            "Ünicode": "Non-ASCII title.",
        }
    )
    monkeypatch.setattr(instance, "_read_page_from_dump", dump)
    return instance, dump


def test_second_read_comes_from_the_cache(loader) -> None:
    """The dump is consulted once per article, however often it is asked for."""
    instance, dump = loader
    first = instance.get_text_from_page("Photosynthesis")
    second = instance.get_text_from_page("Photosynthesis")
    assert first == second == "Plants convert light."
    assert dump.reads == ["Photosynthesis"]


def test_cache_survives_a_new_loader(loader, tmp_path, monkeypatch) -> None:
    """A later build reads the cache written by an earlier one."""
    instance, dump = loader
    instance.get_text_from_page("Photosynthesis")

    fresh = WikiLoader(cache_dir=str(tmp_path / "wiki_cache"))
    fresh_dump = _FakeDump({})  # Would raise if it were consulted.
    monkeypatch.setattr(fresh, "_read_page_from_dump", fresh_dump)
    assert fresh.get_text_from_page("Photosynthesis") == "Plants convert light."
    assert fresh_dump.reads == []


@pytest.mark.parametrize("title", ["AC/DC", "Nul (band)", "Ünicode"])
def test_titles_that_are_not_filenames_round_trip(loader, title: str) -> None:
    """A title with a separator or non-ASCII character caches like any other.

    "AC/DC" is the case that matters: named directly, the slash would write
    into a subdirectory that does not exist.
    """
    instance, dump = loader
    expected = instance.get_text_from_page(title)
    assert instance.get_text_from_page(title) == expected
    assert dump.reads == [title]


def test_cache_is_sharded_rather_than_flat(loader, tmp_path) -> None:
    """Articles land in subdirectories, not one directory of thousands."""
    instance, _ = loader
    for title in ("Photosynthesis", "AC/DC", "Nul (band)", "Ünicode"):
        instance.get_text_from_page(title)

    cache_dir = tmp_path / "wiki_cache"
    entries = list(cache_dir.iterdir())
    assert entries, "nothing was cached"
    assert all(entry.is_dir() for entry in entries)
    assert all(len(entry.name) == 2 for entry in entries)


def test_disabled_cache_always_reads_the_dump(tmp_path, monkeypatch) -> None:
    """cache_dir="" opts out, for a run that must not leave files behind."""
    instance = WikiLoader(cache_dir="")
    dump = _FakeDump({"Photosynthesis": "Plants convert light."})
    monkeypatch.setattr(instance, "_read_page_from_dump", dump)

    instance.get_text_from_page("Photosynthesis")
    instance.get_text_from_page("Photosynthesis")
    assert dump.reads == ["Photosynthesis", "Photosynthesis"]


def test_a_missing_page_is_not_cached(loader) -> None:
    """A miss must stay a miss rather than being remembered as empty text."""
    instance, dump = loader
    for _ in range(2):
        with pytest.raises(ValueError):
            instance.get_text_from_page("Nonexistent")
    assert dump.reads == ["Nonexistent", "Nonexistent"]


def test_a_corrupt_cache_file_falls_back_to_the_dump(loader) -> None:
    """An unreadable or truncated file is treated as absent, not as text."""
    instance, dump = loader
    instance.get_text_from_page("Photosynthesis")
    path = instance._cache_path("Photosynthesis")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("")  # Truncated: no title line.

    assert instance.get_text_from_page("Photosynthesis") == "Plants convert light."
    assert dump.reads == ["Photosynthesis", "Photosynthesis"]
