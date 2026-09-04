"""Tests for hyphenated-compound discovery."""

from wordfreq.corpora.hyphenated import (
    CATEGORY_ATTRIBUTIVE,
    CATEGORY_FRACTION,
    CATEGORY_GENERAL,
    CATEGORY_MEASURE,
    CATEGORY_ORDER,
    CATEGORY_PHRASE,
    CATEGORY_PREFIXED,
    CATEGORY_PROPER,
    CATEGORY_SOLID_VARIANT,
    HyphenatedCandidate,
    HyphenatedStats,
    classify,
    find_hyphenated,
    find_hyphenated_occurrences,
    group_by_category,
    is_fraction,
    is_measure_phrase,
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


class TestCaseEvidence:
    """Case is recorded the way the single-word tokenizer records it."""

    def test_mid_sentence_capital_is_evidence(self):
        found = find_hyphenated_occurrences("the captain Jean-Luc arrived")
        assert found.upper["jean-luc"] == 1
        assert found.lower["jean-luc"] == 0

    def test_sentence_initial_capital_is_uncertain(self):
        # The position forced the capital, so it decides nothing either way.
        found = find_hyphenated_occurrences("Jean-Luc arrived")
        assert found.uncertain["jean-luc"] == 1
        assert found.upper["jean-luc"] == 0

    def test_line_initial_capital_is_uncertain(self):
        found = find_hyphenated_occurrences("a heading\nWell-Known People")
        assert found.uncertain["well-known"] == 1

    def test_lowercase_mid_sentence_is_evidence(self):
        found = find_hyphenated_occurrences("a well-known fact")
        assert found.lower["well-known"] == 1

    def test_inner_capital_is_recorded(self):
        # No sentence position can force a capital on the second part, so this
        # is what separates "non-Jewish" from "non-fiction".
        found = find_hyphenated_occurrences("the non-Jewish population")
        assert found.inner_upper["non-jewish"] == 1

    def test_inner_capital_absent_for_an_ordinary_compound(self):
        found = find_hyphenated_occurrences("Non-fiction sells well")
        assert found.inner_upper["non-fiction"] == 0

    def test_capitalized_share_needs_decided_occurrences(self):
        stats = scan_source(lambda: iter([("a", "Well-known people")]), log_every=0)
        assert stats.capitalized_share("well-known") is None


class TestUnhyphenatedSpellings:
    """The solid and spaced spellings of what was found are counted too."""

    def test_counts_the_solid_spelling(self):
        found = find_hyphenated_occurrences("went north-east past the northeast wind")
        assert found.solid["north-east"] == 1

    def test_counts_the_spaced_spelling(self):
        found = find_hyphenated_occurrences("went north-east and also north east")
        assert found.spaced["north-east"] == 1

    def test_the_compound_is_not_its_own_spaced_spelling(self):
        # "north-east" contains "north" then "east"; without masking the
        # hyphenated matches it would count as evidence for "north east".
        found = find_hyphenated_occurrences("north-east north-east")
        assert found.spaced["north-east"] == 0

    def test_multi_part_compounds_have_no_unhyphenated_form(self):
        # "black and white" written out is a phrase, not a spelling of the
        # compound, so it is not counted as one.
        found = find_hyphenated_occurrences("black-and-white and black and white")
        assert found.spaced["black-and-white"] == 0

    def test_preferred_spelling_reports_the_winner(self):
        candidate = HyphenatedCandidate(
            text="north-east", count=3, documents=3, corpora=("g",), solid=9
        )
        assert candidate.preferred_spelling == "solid"


class TestClassify:
    """Which section of the report a compound lands in."""

    def _candidate(self, text, **kwargs):
        kwargs.setdefault("count", 10)
        kwargs.setdefault("documents", 5)
        kwargs.setdefault("corpora", ("gutenberg",))
        return HyphenatedCandidate(text=text, **kwargs)

    def test_fraction(self):
        assert classify(self._candidate("two-thirds")) == CATEGORY_FRACTION
        assert classify(self._candidate("one-half")) == CATEGORY_FRACTION

    def test_measure_phrase(self):
        # "a five-year plan" is "five" and "year"; nothing new is being learned.
        assert classify(self._candidate("five-year")) == CATEGORY_MEASURE
        assert classify(self._candidate("four-year")) == CATEGORY_MEASURE

    def test_multi_part_compound_is_a_phrase(self):
        assert classify(self._candidate("black-and-white")) == CATEGORY_PHRASE

    def test_participle_is_attributive(self):
        assert classify(self._candidate("long-tailed")) == CATEGORY_ATTRIBUTIVE

    def test_productive_prefix(self):
        assert classify(self._candidate("non-fiction")) == CATEGORY_PREFIXED

    def test_inner_capital_beats_the_prefix_rule(self):
        # "non-Jewish" is the base, negated -- and the capital says so even
        # though the compound looks exactly like "non-fiction".
        candidate = self._candidate("non-jewish", count=10, inner_upper=9, lower=10)
        assert classify(candidate) == CATEGORY_PROPER

    def test_capitalized_compound_is_a_name(self):
        assert classify(self._candidate("jean-luc", upper=9, lower=1)) == CATEGORY_PROPER

    def test_sentence_initial_capitals_do_not_condemn(self):
        # All the evidence is forced by position, so the compound is judged on
        # its shape instead of being called a name.
        candidate = self._candidate("horse-drawn", uncertain=10)
        assert classify(candidate) == CATEGORY_ATTRIBUTIVE

    def test_too_little_case_evidence_to_condemn(self):
        candidate = self._candidate("cross-examination", upper=2, lower=0, uncertain=8)
        assert classify(candidate) == CATEGORY_GENERAL

    def test_mostly_solid_is_a_spelling_variant(self):
        candidate = self._candidate("north-east", count=10, solid=40, lower=10)
        assert classify(candidate) == CATEGORY_SOLID_VARIANT

    def test_ordinary_compound_is_general(self):
        assert classify(self._candidate("ice-cream", lower=10)) == CATEGORY_GENERAL


class TestIsFraction:
    def test_detects_fractions(self):
        assert is_fraction("two-thirds")
        assert is_fraction("one-half")
        assert is_fraction("three-quarters")

    def test_a_measure_is_not_a_fraction(self):
        assert not is_fraction("five-year")

    def test_an_ordinary_compound_is_not_a_fraction(self):
        assert not is_fraction("well-known")


class TestIsMeasurePhrase:
    def test_detects_number_plus_unit(self):
        assert is_measure_phrase("five-year")
        assert is_measure_phrase("two-week")

    def test_a_fraction_is_not_a_measure(self):
        assert not is_measure_phrase("two-thirds")

    def test_lexicalized_number_compounds_are_not_measures(self):
        # These have the shape of a number modifying a unit and are nothing of
        # the kind: "a three-dimensional object" is one word where "a five-year
        # plan" is two.  "three-dimensional" was on the first curated list.
        assert not is_measure_phrase("three-dimensional")
        assert not is_measure_phrase("one-sided")


class TestGroupByCategory:
    """Sectioning the ranked list for the report."""

    def _candidate(self, text, category, documents=1):
        return HyphenatedCandidate(
            text=text, count=1, documents=documents, corpora=("g",), category=category
        )

    def test_fractions_lead_the_report(self):
        # They are wanted at a much earlier level than the rest, so they are
        # decided on their own rather than found partway down a long list.
        grouped = group_by_category(
            [
                self._candidate("well-known", CATEGORY_GENERAL),
                self._candidate("two-thirds", CATEGORY_FRACTION),
            ]
        )
        assert list(grouped) == [CATEGORY_FRACTION, CATEGORY_GENERAL]

    def test_empty_categories_are_omitted(self):
        grouped = group_by_category([self._candidate("well-known", CATEGORY_GENERAL)])
        assert list(grouped) == [CATEGORY_GENERAL]

    def test_ranking_is_preserved_within_a_category(self):
        grouped = group_by_category(
            [
                self._candidate("first", CATEGORY_GENERAL, documents=9),
                self._candidate("second", CATEGORY_GENERAL, documents=2),
            ]
        )
        assert [item.text for item in grouped[CATEGORY_GENERAL]] == ["first", "second"]

    def test_an_unlisted_category_still_reaches_the_report(self):
        grouped = group_by_category([self._candidate("odd", "invented")])
        assert list(grouped) == ["invented"]

    def test_every_ordered_category_is_a_real_one(self):
        assert len(set(CATEGORY_ORDER)) == len(CATEGORY_ORDER)


class TestRankCandidatesCategories:
    """rank_candidates assigns a category from the pooled evidence."""

    def test_case_evidence_reaches_the_candidate(self):
        stats = scan_source(
            lambda: iter([("a", "the captain Jean-Luc spoke to Jean-Luc again")]),
            log_every=0,
        )
        candidates = rank_candidates({"g": stats}, min_count=1, min_documents=1)
        assert candidates[0].upper == 2
        assert candidates[0].capitalized_share == 1.0

    def test_a_name_is_categorized_as_proper(self):
        text = "the captain Jean-Luc met Jean-Luc and Jean-Luc and Jean-Luc"
        stats = scan_source(lambda: iter([("a", text)]), log_every=0)
        candidates = rank_candidates({"g": stats}, min_count=1, min_documents=1)
        assert candidates[0].category == CATEGORY_PROPER
