"""Tests for corpus aggregation: name detection and cross-book weighting."""

import json
from pathlib import Path

import pytest

from wordfreq.corpora.frequency_build import (
    BookAnalysis,
    aggregate_frequencies,
    analyze_book,
    build_corpus_payload,
    detect_names,
    write_corpus_json,
)
from wordfreq.corpora.gutenberg_text import analyze_text


def make_book(slug: str, text: str) -> BookAnalysis:
    """Analyze raw text as a book (no Gutenberg markers needed)."""
    return analyze_book(slug, text)


def test_detect_names_finds_consistently_capitalized_words() -> None:
    text = (
        "The captain met Ahab today. Later the captain saw Ahab again. "
        "Everyone feared Ahab, and the captain knew it. Ahab said nothing to Ahab."
    )
    names = detect_names(analyze_text(text), min_mid_sentence=3)
    assert "ahab" in names
    assert "captain" not in names


def test_detect_names_ignores_the_first_person_pronoun() -> None:
    text = " ".join(["He told I and I told I about I again, and I agreed with I."] * 3)
    names = detect_names(analyze_text(text), min_mid_sentence=3)
    assert "i" not in names


def test_detect_names_needs_mid_sentence_evidence() -> None:
    # Verse: every line starts capitalized, so nothing can be judged a name.
    verse = "\n".join(["Praise him.", "Praise him.", "Praise him.", "Praise him."])
    assert detect_names(analyze_text(verse), min_mid_sentence=3) == {}


def test_names_are_excluded_from_content_counts_per_book() -> None:
    novel = "He met Rose. Everyone liked Rose because Rose was kind to Rose."
    garden = "She picked a rose. The rose smelled sweet and the rose was red."
    novel_analysis = make_book("1_Novel", novel)
    garden_analysis = make_book("2_Garden", garden)

    assert "rose" in novel_analysis.names
    assert novel_analysis.content_counts["rose"] == 0
    assert "rose" not in garden_analysis.names
    assert garden_analysis.content_counts["rose"] == 3


def test_per_book_mean_dilutes_a_word_confined_to_one_book() -> None:
    """A word that only one book uses heavily must not outrank common words."""
    obsessive = ("whale " * 2000) + ("ship sailed the sea " * 125)
    others = [("ship sailed the sea " * 125) for _ in range(4)]

    analyses = [make_book("1_Whales", obsessive)]
    analyses += [make_book(f"{index}_Other", text) for index, text in enumerate(others, start=2)]

    pooled, _ = aggregate_frequencies(analyses, weighting="pooled", min_books=1, max_words=None)
    averaged, _ = aggregate_frequencies(
        analyses, weighting="per-book-mean", min_books=1, max_words=None, full_weight_tokens=0
    )

    # Pooling lets the one obsessive book carry "whale" above every other word.
    assert max(pooled, key=lambda word: pooled[word]) == "whale"
    # Averaging rates across books does not.
    assert averaged["whale"] < averaged["ship"]


def test_min_books_filter_drops_words_confined_to_few_books() -> None:
    analyses = [
        make_book("1_A", "the ship sailed lembas"),
        make_book("2_B", "the ship sailed"),
        make_book("3_C", "the ship sailed"),
    ]
    kept, _ = aggregate_frequencies(analyses, min_books=2, max_words=None)
    assert "ship" in kept
    assert "lembas" not in kept


def test_short_books_get_proportionally_less_weight() -> None:
    long_book = make_book("1_Long", "alpha beta " * 5000)
    short_book = make_book("2_Short", "gamma " * 20 + "alpha beta " * 10)

    weighted, _ = aggregate_frequencies(
        [long_book, short_book], min_books=1, max_words=None, full_weight_tokens=10000
    )
    unweighted, _ = aggregate_frequencies(
        [long_book, short_book], min_books=1, max_words=None, full_weight_tokens=0
    )

    # "gamma" only exists in the short book; giving that book full weight
    # inflates it far more than length-scaled weighting does.
    assert weighted["gamma"] < unweighted["gamma"]


def test_aggregate_handles_no_books() -> None:
    frequencies, unique = aggregate_frequencies([], min_books=1)
    assert frequencies == {}
    assert unique == 0


def test_payload_has_the_corpus_file_shape(tmp_path: Path) -> None:
    analyses = [
        make_book("1_A", "The dog met Rufus. Rufus barked at the dog. " * 10),
        make_book("2_B", "The dog ran. A cat watched the dog run away. " * 10),
        make_book("3_C", "The cat and the dog sat by the door quietly. " * 10),
    ]
    payload = build_corpus_payload(
        analyses, corpus_name="test_corpus", min_books=2, max_words=5, min_name_count=5
    )

    assert set(payload) >= {
        "global_word_frequency",
        "name_frequency",
        "books_processed",
        "total_unique_words",
        "total_names_identified",
    }
    assert payload["books_processed"] == ["1_A", "2_B", "3_C"]
    assert 0 < len(payload["global_word_frequency"]) <= 5
    assert "rufus" in payload["name_frequency"]["1_A"]
    assert "rufus" not in payload["global_word_frequency"]
    assert payload["generation"]["corpus"] == "test_corpus"

    output = tmp_path / "test_corpus.json"
    write_corpus_json(payload, str(output))
    reloaded = json.loads(output.read_text(encoding="utf-8"))
    assert reloaded["global_word_frequency"] == payload["global_word_frequency"]


def test_generated_payload_loads_through_the_corpus_importer(tmp_path: Path) -> None:
    """The written file must parse in the importer that consumes corpus JSON."""
    from wordfreq.frequency.importer import _parse_frequency_file

    analyses = [
        make_book("1_A", "the quick brown fox jumps over the lazy dog. " * 20),
        make_book("2_B", "the lazy dog sleeps while the quick fox runs. " * 20),
        make_book("3_C", "a quick dog and a lazy fox met by the river. " * 20),
    ]
    payload = build_corpus_payload(analyses, corpus_name="test_corpus", min_books=2)
    output = tmp_path / "test_corpus.json"
    write_corpus_json(payload, str(output))

    parsed = _parse_frequency_file(str(output), "json", "auto")
    assert parsed["the"]["frequency"] is not None
    assert parsed["the"]["frequency"] > parsed["dog"]["frequency"]


@pytest.mark.parametrize("weighting", ["per-book-mean", "pooled"])
def test_frequencies_are_positive_integers(weighting: str) -> None:
    analyses = [make_book(f"{index}_B", "alpha beta gamma delta " * 30) for index in range(1, 4)]
    frequencies, _ = aggregate_frequencies(analyses, weighting=weighting, min_books=1)  # type: ignore[arg-type]
    assert frequencies
    assert all(isinstance(value, int) and value >= 1 for value in frequencies.values())


def test_extra_never_names_keeps_reverently_capitalized_words_as_vocabulary() -> None:
    text = (
        "The people praised God today. Everyone praised God again, "
        "and the elders praised God with the Lord watching over God."
    )
    stats = analyze_text(text)
    assert "god" in detect_names(stats, min_mid_sentence=3)
    kept = detect_names(stats, min_mid_sentence=3, extra_never_names=("God",))
    assert "god" not in kept


def test_analyze_book_honors_the_corpus_vocabulary_allowlist() -> None:
    text = "He praised God. The elders praised God, and all praised God with God. " * 4
    analysis = analyze_book("1_Scripture", text, extra_never_names=("god",))
    assert "god" not in analysis.names
    assert analysis.content_counts["god"] > 0
