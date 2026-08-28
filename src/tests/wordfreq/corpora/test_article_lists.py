"""Well-formedness checks on the Wikipedia article lists behind the ``wiki_*`` corpora.

The lists are transcribed from Wikipedia's Level 4 vital-article pages, so the
mistake worth catching is a transcription one: leftover wikitext in a title, a
namespace prefix that is not an article, or the same page listed twice.  How
many titles a list holds is not asserted -- the lists are edited deliberately,
and the builder already reports what it could not find in the snapshot.
"""

from typing import Dict, List

import pytest

from wordfreq.corpora.wikipedia.vital_articles import (
    ARTS_ARTICLES,
    BIOLOGY_ARTICLES,
    EVERYDAY_LIFE_ARTICLES,
    GEOGRAPHY_ARTICLES,
    MATH_ARTICLES,
    TECHNOLOGY_ARTICLES,
    VITAL_ARTICLES,
    flatten,
)

# Every list in the module, by the name it is exported under.
ARTICLE_LISTS: Dict[str, Dict[str, List[str]]] = {
    "VITAL_ARTICLES": VITAL_ARTICLES,
    "MATH_ARTICLES": MATH_ARTICLES,
    "GEOGRAPHY_ARTICLES": GEOGRAPHY_ARTICLES,
    "BIOLOGY_ARTICLES": BIOLOGY_ARTICLES,
    "EVERYDAY_LIFE_ARTICLES": EVERYDAY_LIFE_ARTICLES,
    "TECHNOLOGY_ARTICLES": TECHNOLOGY_ARTICLES,
    "ARTS_ARTICLES": ARTS_ARTICLES,
}


@pytest.mark.parametrize("list_name", sorted(ARTICLE_LISTS))
def test_titles_are_unique_within_a_list(list_name: str) -> None:
    """A duplicate would weight one article twice and inflate its vocabulary."""
    articles = ARTICLE_LISTS[list_name]
    titles = [title for group in articles.values() for title in group]
    duplicates = {title for title in titles if titles.count(title) > 1}
    assert not duplicates, f"{list_name} repeats {sorted(duplicates)}"
    # flatten() de-duplicates, so a duplicate would otherwise show up only as a
    # quiet disagreement between the two counts.
    assert len(flatten(articles)) == len(titles)


@pytest.mark.parametrize("list_name", sorted(ARTICLE_LISTS))
def test_titles_are_well_formed(list_name: str) -> None:
    """Titles are page titles, not wikitext: no markup, no namespace prefix."""
    for group, titles in ARTICLE_LISTS[list_name].items():
        assert titles, f"{list_name}[{group!r}] is empty"
        for title in titles:
            assert title, f"{list_name}[{group!r}] holds an empty title"
            assert title == title.strip(), f"{title!r} has surrounding whitespace"
            for markup in ("[[", "]]", "{{", "}}", "|", "#"):
                assert markup not in title, f"{title!r} still holds {markup!r}"
            assert not title.startswith(
                ("Wikipedia:", "Category:", "File:", "Image:", "Portal:")
            ), f"{title!r} is not an article"
