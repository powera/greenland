"""Tests for Gutenberg plain-text extraction and tokenization."""

import pytest

from wordfreq.corpora.gutenberg_text import (
    MAX_ROMAN_NUMERAL,
    ROMAN_NUMERALS,
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


def test_every_apostrophe_variant_folds_to_one_word() -> None:
    """A contraction must be one word corpus-wide, however a book typesets it.

    Books are individually consistent but differ from each other, so an
    unfolded variant splits a common contraction across two entries and
    ``--min-books`` can then drop both.  U+02BC is a modifier *letter*, so
    without folding it splits "donʼt" into "don" + "t" rather than merely
    spelling it differently.
    """
    for text in ("don't", "don’t", "donʼt", "don′t", "don‛t"):
        tokens = [token for token, _, _ in iter_tokens(text)]
        assert tokens == ["don't"], f"{text!r} tokenized as {tokens}"


def test_dashes_separate_words_rather_than_joining_them() -> None:
    """An unspaced em dash is ordinary 19th-century typesetting, not a compound."""
    for text in ("cat—the dog", "cat–the dog", "cat--the dog", "cat―the dog"):
        tokens = [token for token, _, _ in iter_tokens(text)]
        assert tokens == ["cat", "the", "dog"], f"{text!r} tokenized as {tokens}"


def test_quote_marks_do_not_attach_to_words() -> None:
    """Folding ‘ to ' must not glue a quote mark onto the word it opens."""
    tokens = [token for token, _, _ in iter_tokens("‘Tis so,’ said the boys’ friend.")]
    assert tokens == ["tis", "so", "said", "the", "boys", "friend"]


def test_hyphen_still_splits_a_compound() -> None:
    """A plain hyphen is left alone; the token regex splits it as it always did."""
    tokens = [token for token, _, _ in iter_tokens("a well-known man")]
    assert tokens == ["a", "well", "known", "man"]


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


def test_case_split_apportions_sentence_starts_by_the_decided_ratio() -> None:
    """The three case counters partition counts, and uncertain follows evidence."""
    text = "Rose walked. He gave Rose a rose. The rose was for Rose."
    stats = analyze_text(text)

    # Every occurrence lands in exactly one bucket -- the invariant the whole
    # split rests on.
    for word in stats.counts:
        buckets = stats.lower_counts[word] + stats.upper_counts[word]
        assert buckets + stats.uncertain_counts[word] == stats.counts[word]

    # Mid-sentence: "Rose a" and "for Rose" capitalized, "a rose" and "rose was"
    # not.  One sentence-initial "Rose" carries no evidence of its own.
    assert stats.upper_counts["rose"] == 2
    assert stats.lower_counts["rose"] == 2
    assert stats.uncertain_counts["rose"] == 1

    upper, lower = stats.case_split("rose")
    # A 50/50 ratio splits the single uncertain occurrence down the middle.
    assert upper == pytest.approx(2.5)
    assert lower == pytest.approx(2.5)
    assert upper + lower == stats.counts["rose"]


def test_case_split_without_mid_sentence_evidence_stays_lowercase() -> None:
    """A word seen only at sentence starts is not evidence of a capital.

    This matches what the proper-noun filter does with the same absence:
    ``capitalization_ratio`` is None and the word stays ordinary vocabulary.
    """
    stats = analyze_text("Hymns.\nHymns.\nHymns.")
    upper, lower = stats.case_split("hymns")
    assert upper == 0.0
    assert lower == stats.counts["hymns"] == 3


def test_slug_matches_existing_corpus_key_format() -> None:
    assert (
        slugify_title(84, "Frankenstein; Or, The Modern Prometheus")
        == "84_Frankenstein__Or__The_Modern_Prometheus"
    )
    assert slugify_title(1342, "Pride and Prejudice") == "1342_Pride_and_Prejudice"


def test_roman_numerals_are_dropped() -> None:
    """A chapter or verse marker is a number, not a word.

    The digit form is already dropped for containing a digit; the letter form
    reached the corpora as ~60 entries in the religious one and a full
    "xi".."xxviii" series in both book ones.
    """
    tokens = [
        token for token, _, _ in iter_tokens("CHAPTER XXIII. Louis XIV read verse xi and cv.")
    ]
    assert tokens == ["chapter", "louis", "read", "verse", "and"]


def test_roman_numeral_filter_spares_the_pronoun_and_real_words() -> None:
    """The range starts at 2 so "I" survives, and no numeral in it is a word."""
    assert "i" not in ROMAN_NUMERALS
    # These look like numerals but are not valid ones, so the set must not
    # claim them.
    for word in ("mix", "mild", "mill", "civil", "did", "lid", "vivid", "dim", "ill", "mid"):
        assert word not in ROMAN_NUMERALS, f"{word!r} would be filtered as a numeral"
    tokens = [token for token, _, _ in iter_tokens("I did mix a mild civil drink.")]
    assert tokens == ["i", "did", "mix", "a", "mild", "civil", "drink"]


def test_roman_numeral_set_covers_two_through_the_maximum() -> None:
    """Derived from the bound rather than a literal, so it cannot go stale."""
    assert len(ROMAN_NUMERALS) == MAX_ROMAN_NUMERAL - 1
    assert "ii" in ROMAN_NUMERALS
    assert "cxx" in ROMAN_NUMERALS
    # One past the bound is left alone.
    assert "cxxi" not in ROMAN_NUMERALS
