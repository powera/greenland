"""Tests for Gutenberg plain-text extraction and tokenization."""

from wordfreq.corpora.gutenberg_text import (
    analyze_text,
    extract_title,
    iter_tokens,
    slugify_title,
    strip_gutenberg_boilerplate,
)

MODERN_FILE = """The Project Gutenberg eBook of Example Book

Title: Example Book

Author: A. Writer

*** START OF THE PROJECT GUTENBERG EBOOK EXAMPLE BOOK ***

Produced by Some Volunteer and the Online Distributed Proofreading Team.

[Illustration: A picture caption that is not prose.]

The dog barked once. Then it slept.

*** END OF THE PROJECT GUTENBERG EBOOK EXAMPLE BOOK ***

This eBook is for the use of anyone anywhere at no cost. Redistribution
is subject to the trademark licence.
"""

LEGACY_FILE = """The Project Gutenberg Etext of Old Book

*END*THE SMALL PRINT! FOR PUBLIC DOMAIN ETEXTS*Ver.04.29.93*END*

Scanned by a volunteer.

The cat sat down.

End of Project Gutenberg's Old Book, by A. Writer

Trailing licence text nobody wants counted.
"""


def test_strip_removes_header_footer_and_apparatus() -> None:
    body = strip_gutenberg_boilerplate(MODERN_FILE)
    assert "The dog barked once. Then it slept." in body
    assert "START OF THE PROJECT GUTENBERG" not in body
    assert "trademark licence" not in body
    assert "Produced by" not in body
    assert "Illustration" not in body


def test_strip_handles_legacy_small_print_markers() -> None:
    body = strip_gutenberg_boilerplate(LEGACY_FILE)
    assert "The cat sat down." in body
    assert "SMALL PRINT" not in body
    assert "Trailing licence text" not in body
    assert "Scanned by a volunteer" not in body


def test_strip_leaves_unmarked_text_intact() -> None:
    text = "A book with no markers at all.\n\nJust prose."
    assert strip_gutenberg_boilerplate(text) == text


def test_extract_title_reads_the_header_field() -> None:
    assert extract_title(MODERN_FILE) == "Example Book"
    assert extract_title(LEGACY_FILE) is None


def test_tokens_drop_numerals_and_stray_single_letters() -> None:
    tokens = [token for token, _, _ in iter_tokens("In 1885 the 3rd b group of x men left.")]
    assert tokens == ["in", "the", "group", "of", "men", "left"]


def test_tokens_keep_apostrophes_and_real_single_letters() -> None:
    tokens = [token for token, _, _ in iter_tokens("I can't find a whale's tail, O reader.")]
    assert tokens == ["i", "can't", "find", "a", "whale's", "tail", "o", "reader"]


def test_curly_apostrophes_normalize_to_straight() -> None:
    tokens = [token for token, _, _ in iter_tokens("It’s Alice’s book.")]
    assert tokens == ["it's", "alice's", "book"]


def test_sentence_initial_flag_marks_line_and_sentence_starts() -> None:
    text = 'Alice ran. Alice ran again.\nAlice sang.\n"Alice!" he said, and Alice smiled.'
    tokens = list(iter_tokens(text))
    sentence_initial = [token for token, _, initial in tokens if initial]
    # Start of text, after a period, after a newline, after an opening quote --
    # and "he", because a dialogue attribution after `!"` is indistinguishable
    # from a new sentence.  That only discards capitalization evidence for a
    # word; it can never turn an uncapitalized word into a name.
    assert sentence_initial == ["alice", "alice", "alice", "alice", "he"]
    # "and Alice smiled" is mid-sentence despite the capital letter.
    assert tokens[-2] == ("alice", True, False)


def test_analyze_text_counts_capitalization_only_mid_sentence() -> None:
    text = "Rose walked. He gave Rose a rose. The rose was for Rose."
    stats = analyze_text(text)
    assert stats.counts["rose"] == 5
    # Four mid-sentence uses: "Rose a", "a rose", "rose was", "for Rose".
    assert stats.mid_sentence_total["rose"] == 4
    assert stats.mid_sentence_capitalized["rose"] == 2
    assert stats.capitalization_ratio("rose") == 0.5


def test_capitalization_ratio_is_none_without_evidence() -> None:
    stats = analyze_text("Hymns.\nHymns.\nHymns.")
    assert stats.capitalization_ratio("hymns") is None


def test_slug_matches_existing_corpus_key_format() -> None:
    assert (
        slugify_title(84, "Frankenstein; Or, The Modern Prometheus")
        == "84_Frankenstein__Or__The_Modern_Prometheus"
    )
    assert slugify_title(1342, "Pride and Prejudice") == "1342_Pride_and_Prejudice"
