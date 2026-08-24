"""Integrity checks on the Gutenberg book lists behind the generated corpora."""

from typing import Set

import pytest

from wordfreq.corpora.book_lists import BOOK_LISTS, find_book, get_book_list, get_corpus_names
from wordfreq.frequency.corpus import get_corpus_config


@pytest.mark.parametrize("corpus_name", sorted(BOOK_LISTS))
def test_book_ids_are_unique_within_a_list(corpus_name: str) -> None:
    ids = get_book_list(corpus_name).gutenberg_ids
    assert len(ids) == len(set(ids))


def test_no_book_appears_in_two_corpora() -> None:
    seen: Set[int] = set()
    for book_list in BOOK_LISTS.values():
        ids = set(book_list.gutenberg_ids)
        assert not (ids & seen), f"{ids & seen} appears in more than one corpus"
        seen |= ids


@pytest.mark.parametrize("corpus_name", sorted(BOOK_LISTS))
def test_slugs_are_unique_and_well_formed(corpus_name: str) -> None:
    slugs = [book.slug for book in get_book_list(corpus_name).books]
    assert len(slugs) == len(set(slugs))
    for book, slug in zip(get_book_list(corpus_name).books, slugs):
        assert slug.startswith(f"{book.gutenberg_id}_")
        assert not slug.endswith("_")


@pytest.mark.parametrize("corpus_name", sorted(BOOK_LISTS))
def test_every_book_has_metadata(corpus_name: str) -> None:
    for book in get_book_list(corpus_name).books:
        assert book.gutenberg_id > 0
        assert book.title.strip()
        assert book.year is not None


def test_century_lists_hold_books_from_their_century() -> None:
    for book in get_book_list("19th_books").books:
        assert book.year is not None and 1800 <= book.year <= 1899, book.title
    for book in get_book_list("20th_books").books:
        assert book.year is not None and 1900 <= book.year <= 1999, book.title


def test_lists_are_large_enough_that_no_single_book_dominates() -> None:
    # The corpora are meant to average over many authors; a handful of books
    # would put us back to "whale is a top-200 English word".
    assert len(get_book_list("19th_books").books) >= 40
    assert len(get_book_list("20th_books").books) >= 40
    assert len(get_book_list("religious_translated").books) >= 15


@pytest.mark.parametrize("corpus_name", sorted(BOOK_LISTS))
def test_book_list_matches_the_corpus_configuration(corpus_name: str) -> None:
    config = get_corpus_config(corpus_name)
    assert config is not None, f"{corpus_name} has a book list but no CorpusConfig"
    assert config.file_path == f"{corpus_name}.json"
    # The book list caps how many words are written to the JSON file; the
    # corpus config caps how many of those the database import reads, so the
    # config may ask for fewer but never for more than the file holds.
    assert config.max_words <= get_book_list(corpus_name).max_words


def test_find_book_locates_across_lists() -> None:
    found = find_book(1342)
    assert found is not None and found.title == "Pride and Prejudice"
    assert find_book(-1) is None


def test_corpus_names_are_sorted() -> None:
    assert get_corpus_names() == sorted(get_corpus_names())


def test_religious_corpus_keeps_its_core_vocabulary_out_of_the_name_list() -> None:
    vocabulary = get_book_list("religious_translated").always_vocabulary
    assert {"god", "lord", "spirit", "heaven"} <= set(vocabulary)
    # Actual proper nouns must not be smuggled in as "vocabulary".
    assert not ({"jesus", "christ", "israel", "krishna", "allah"} & set(vocabulary))
    assert all(word == word.lower() for word in vocabulary)


def test_century_corpora_need_no_vocabulary_allowlist() -> None:
    assert get_book_list("19th_books").always_vocabulary == ()
    assert get_book_list("20th_books").always_vocabulary == ()
