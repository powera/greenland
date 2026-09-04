"""Tests for hyphenated-compound discovery."""

from wordfreq.corpora.hyphenated import (
    HyphenatedStats,
    find_hyphenated,
    is_spelled_number,
    rank_candidates,
    scan_source,
)


class TestFindHyphenated:
    """What counts as a hyphenated compound in one document."""

    def test_finds_a_plain_compound(self):
        assert find_hyphenated("a non-linear system")["non-linear"] == 1

    def test_counts_repeats(self):
        assert find_hyphenated("self-similar and self-similar again")["self-similar"] == 2

    def test_lowercases(self):
        assert find_hyphenated("Well-Known and well-known")["well-known"] == 2

    def test_finds_multi_part_compounds(self):
        assert "case-by-case" in find_hyphenated("decided case-by-case")

    def test_ignores_unhyphenated_words(self):
        assert find_hyphenated("an ordinary sentence of plain words") == {}

    def test_em_dash_is_not_a_compound(self):
        # _normalize turns dash variants into spaces before matching, so an
        # unspaced em dash between words must not read as a hyphen join.
        assert find_hyphenated("the cat—the dog") == {}

    def test_double_hyphen_is_not_a_compound(self):
        # "--" is the older typesetting of an em dash, handled by _normalize.
        assert find_hyphenated("the cat--the dog") == {}

    def test_line_broken_word_is_not_a_compound(self):
        # A hyphen at end of line is typesetting, not vocabulary. Counting it
        # would invent a compound out of every long word in the corpus.
        assert find_hyphenated("an inter-\nesting book") == {}

    def test_digits_do_not_produce_fragments(self):
        # "19th-century" must not yield "th-century" -- that is the same class
        # of fragment this module exists to eliminate.
        found = find_hyphenated("a 19th-century rule")
        assert "th-century" not in found
        assert found == {}

    def test_apostrophe_survives_inside_a_part(self):
        assert "ne'er-do-well" in find_hyphenated("a ne'er-do-well")


class TestIsSpelledNumber:
    """Spelled-out numbers are a pattern, not vocabulary."""

    def test_detects_compound_numerals(self):
        assert is_spelled_number("twenty-five")
        assert is_spelled_number("forty-second")

    def test_ordinary_compounds_are_not_numbers(self):
        assert not is_spelled_number("non-linear")
        assert not is_spelled_number("self-similar")

    def test_multi_part_compound_is_not_a_number(self):
        assert not is_spelled_number("one-to-one")


class TestScanSource:
    """Pooling counts across the documents of one corpus."""

    def _source(self, documents):
        return lambda: iter(documents)

    def test_counts_across_documents(self):
        stats = scan_source(
            self._source([("a", "non-linear"), ("b", "non-linear non-linear")]),
            log_every=0,
        )
        assert stats.counts["non-linear"] == 3
        assert stats.documents_scanned == 2

    def test_document_spread_counts_once_per_document(self):
        # Ten uses in one document is one document's worth of evidence.
        stats = scan_source(self._source([("a", "self-similar " * 10)]), log_every=0)
        assert stats.counts["self-similar"] == 10
        assert stats.documents["self-similar"] == 1

    def test_merge_adds_both_sides(self):
        first = scan_source(self._source([("a", "non-linear")]), log_every=0)
        second = scan_source(self._source([("b", "non-linear")]), log_every=0)
        first.merge(second)
        assert first.counts["non-linear"] == 2
        assert first.documents["non-linear"] == 2
        assert first.documents_scanned == 2


def _stats(counts, documents, scanned=10):
    stats = HyphenatedStats()
    stats.counts.update(counts)
    stats.documents.update(documents)
    stats.documents_scanned = scanned
    return stats


class TestRankCandidates:
    """Pooling corpora and filtering to what is worth importing."""

    def test_pools_counts_across_corpora(self):
        candidates = rank_candidates(
            {
                "gutenberg": _stats({"so-called": 5}, {"so-called": 3}),
                "scotus": _stats({"so-called": 7}, {"so-called": 4}),
            },
            min_count=1,
            min_documents=1,
        )
        assert len(candidates) == 1
        assert candidates[0].count == 12
        assert candidates[0].documents == 7
        assert candidates[0].corpora == ("gutenberg", "scotus")
        assert candidates[0].corpus_count == 2

    def test_min_documents_filters_one_author_habit(self):
        candidates = rank_candidates(
            {"gutenberg": _stats({"odd-word": 40}, {"odd-word": 1})},
            min_count=1,
            min_documents=3,
        )
        assert candidates == []

    def test_min_corpora_requires_agreement(self):
        stats = {"gutenberg": _stats({"one-corpus": 20}, {"one-corpus": 9})}
        assert rank_candidates(stats, min_corpora=1)
        assert rank_candidates(stats, min_corpora=2) == []

    def test_excludes_known_words_case_insensitively(self):
        candidates = rank_candidates(
            {"gutenberg": _stats({"well-known": 20}, {"well-known": 9})},
            exclude=["Well-Known"],
        )
        assert candidates == []

    def test_drops_spelled_numbers_by_default(self):
        stats = {"gutenberg": _stats({"twenty-five": 50}, {"twenty-five": 20})}
        assert rank_candidates(stats) == []
        assert rank_candidates(stats, drop_spelled_numbers=False)

    def test_sorted_by_spread_then_count(self):
        candidates = rank_candidates(
            {
                "gutenberg": _stats(
                    {"wide-spread": 10, "narrow-use": 99},
                    {"wide-spread": 9, "narrow-use": 4},
                )
            },
            min_count=1,
            min_documents=1,
        )
        # Spread wins over raw volume: the word used across nine documents is
        # the better import even though the other is used ten times as often.
        assert [item.text for item in candidates] == ["wide-spread", "narrow-use"]
