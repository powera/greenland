"""Regression coverage for shared spelling evidence and conservative casing."""

import importlib
from collections import Counter

import pytest

from wordfreq.corpora.casing import pooled_spelling_evidence, resolve_spellings
from wordfreq.corpora.frequency_build import (
    aggregate_case_frequencies,
    analyze_book,
    build_corpus_payload,
)
from wordfreq.corpora.gutenberg_text import analyze_text, build_phrase_index, iter_tokens


def frequencies(text: str, *, documents: int = 3) -> dict[str, int]:
    analyses = [analyze_book(str(index), text) for index in range(documents)]
    result, _ = aggregate_case_frequencies(analyses, weighting="pooled")
    return result


def test_observed_acronyms_and_mixed_case_are_not_titlecased() -> None:
    result = frequencies("They discuss NGO and ECU with LGBTQ groups using pH and iPhone. " * 10)
    for spelling in ("NGO", "ECU", "LGBTQ", "pH", "iPhone"):
        assert result[spelling] == 30
        assert spelling.lower() not in result
        assert spelling.capitalize() not in result


def test_sentence_initial_the_is_not_capitalized_vocabulary() -> None:
    result = frequencies("The dog saw the cat. The cat saw the dog. " * 10)
    assert result["the"] == 120
    assert "The" not in result


def test_sentence_initial_may_uses_only_lower_and_initial_capital_evidence() -> None:
    result = frequencies("May begins. They may travel in May. MAY begins. " * 10)
    # The sentence-initial May follows the equal may/May evidence; MAY is
    # independently informative and gets none of the ambiguous occurrences.
    assert result["may"] == 45
    assert result["May"] == 45
    assert result["MAY"] == 30


def test_lowercase_at_sentence_start_is_reliable() -> None:
    stats = analyze_text("rose. Rose. She met Rose.")
    assert stats.spelling_counts["rose"] == Counter({"rose": 1, "Rose": 1})
    assert stats.initial_counts["rose"] == 1


def test_initial_acronyms_and_mixed_case_are_reliable() -> None:
    stats = analyze_text("NGO workers arrived. pH matters. iPhone users agreed.")
    for word, spelling in (("ngo", "NGO"), ("ph", "pH"), ("iphone", "iPhone")):
        assert stats.spelling_counts[word][spelling] == 1
        assert stats.initial_counts[word] == 0


def test_forced_uppercase_does_not_supply_spelling_evidence() -> None:
    text = "THE DOG SAW THE CAT.\nTHE DOG\nThe dog saw the cat."
    stats = analyze_text(text)
    assert stats.forced_counts["the"] == 3
    assert "THE" not in stats.spelling_counts.get("the", {})
    result = frequencies(text * 10)
    assert "THE" not in result
    assert "The" not in result
    assert result["the"] == 150


def test_rare_shouted_the_folds_into_lowercase_without_losing_counts() -> None:
    result = frequencies("They saw the dog. " * 99 + "They saw THE dog. ")
    assert result["the"] == 300
    assert "THE" not in result
    assert "The" not in result


@pytest.mark.parametrize("upper,lower", [("US", "us"), ("IT", "it"), ("AIDS", "aids")])
def test_known_rare_acronym_survives_below_share_threshold(upper: str, lower: str) -> None:
    result = frequencies(f"They discuss {lower} today. " * 199 + f"They discuss {upper} today. ")
    assert result[upper] == 3
    assert result[lower] == 597
    assert upper.capitalize() not in result


def test_unknown_acronym_requires_reliable_spelling_coverage() -> None:
    analyses = [analyze_book("one", "They discuss QRT today. " * 20)]
    analyses.extend(analyze_book(str(index), "qrt. " * 10) for index in range(2))
    result, _ = aggregate_case_frequencies(analyses, weighting="pooled", min_books=3)
    assert "QRT" not in result
    assert result["qrt"] == 40


def test_unknown_acronym_with_evidence_across_documents_survives() -> None:
    result = frequencies("They discuss QRT today. " * 10)
    assert result["QRT"] == 30
    assert "Qrt" not in result


def test_known_spelling_never_creates_an_acronym_from_lowercase() -> None:
    result = frequencies("They help us because it aids recovery. " * 10)
    assert all(spelling not in result for spelling in ("US", "IT", "AIDS"))


def test_corpus_evidence_resolves_initial_only_documents() -> None:
    analyses = [analyze_book("prose", "They met Ishmael today. " * 10)]
    analyses.extend(analyze_book(str(index), "Ishmael arrived. " * 10) for index in range(2))
    result, _ = aggregate_case_frequencies(analyses, weighting="pooled", min_books=3)
    assert result["Ishmael"] == 30
    assert "ishmael" not in result
    assert analyses[0].names["ishmael"] == 10
    assert analyses[0].content_counts["ishmael"] == 10


def test_initial_only_unknown_word_stays_lowercase() -> None:
    assert frequencies("Hymns.\nHymns.\nHymns.")["hymns"] == 9


def test_forced_uppercase_uses_all_attested_forms() -> None:
    stats = analyze_text("They discuss US with us.\nUS US US")
    result = resolve_spellings(stats, pooled_spelling_evidence([stats]))
    assert result["US"] + result["us"] == 5
    assert result["US"] == 2.5
    assert result["us"] == 2.5


def test_internal_capitals_and_possessives_survive() -> None:
    result = frequencies("They met O'Connor and saw NGO's work on iPhone. " * 10)
    assert result["O'Connor"] == 30
    assert result["NGO's"] == 30
    assert "O'connor" not in result


@pytest.mark.parametrize("weighting", ["pooled", "per-book-mean"])
def test_resolving_spelling_conserves_counts_and_weighted_scores(weighting: str) -> None:
    texts = [
        "Rose arrived. They met Rose and saw a rose. THE ROSE IS RED. ",
        "They discuss US and ask us. NGO workers arrived. pH matters. ",
        "AIDS aids research. They use iPhone. HYMNS AND SONGS. ",
    ]
    analyses = [analyze_book(str(index), text * (index + 1)) for index, text in enumerate(texts)]
    evidence = pooled_spelling_evidence([analysis.stats for analysis in analyses])
    for analysis in analyses:
        resolved = resolve_spellings(analysis.stats, evidence)
        grouped: dict[str, float] = {}
        for surface, count in resolved.items():
            grouped[surface.lower()] = grouped.get(surface.lower(), 0.0) + count
        assert grouped == pytest.approx(dict(analysis.content_counts))
        assert sum(resolved.values()) == pytest.approx(analysis.stats.token_total)
    result, _ = aggregate_case_frequencies(analyses, weighting=weighting, min_books=1)  # type: ignore[arg-type]
    # Integer publication can round each spelling by at most half a count.
    assert abs(sum(result.values()) - sum(analysis.content_tokens for analysis in analyses)) <= len(
        result
    )


def test_phrase_and_cooccurrence_matching_remains_lowercase() -> None:
    phrases = build_phrase_index(["new york", "ice cream"])
    tokens = list(iter_tokens("They visit New York for ice cream.", phrases))
    assert ("new york", True, False) in tokens
    assert ("ice cream", False, False) in tokens
    stats = analyze_text("They visit New York.", phrases)
    assert stats.spelling_counts["new york"]["New York"] == 1


@pytest.mark.parametrize(
    "builder", ["gutenberg", "scotus", "europarl", "wikipedia", "openstax", "wpalh"]
)
def test_all_builders_use_the_same_frequency_and_casing_path(builder: str) -> None:
    module = importlib.import_module(f"wordfreq.corpora.build_{builder}")
    assert module.analyze_book is analyze_book
    assert module.build_corpus_payload is build_corpus_payload
    analyses = [
        module.analyze_book(str(index), "They met Ishmael at an NGO. " * 10) for index in range(3)
    ]
    payload = module.build_corpus_payload(analyses, corpus_name=f"test_{builder}")
    assert payload["global_word_frequency"]["NGO"] > 0
    assert payload["global_word_frequency"]["Ishmael"] > 0
    assert payload["generation"]["name_detection"] == "diagnostic"


def test_sentence_start_estimates_do_not_round_each_document() -> None:
    analyses = [analyze_book("evidence", "They met Rose and saw a rose.")]
    analyses.extend(analyze_book(str(index), "Rose arrived.") for index in range(20))
    result, _ = aggregate_case_frequencies(
        analyses, weighting="pooled", min_books=1, min_uppercase_count=1
    )
    assert result["Rose"] == 11
    assert result["rose"] == 11


def test_additional_known_vocabulary_can_preserve_a_rare_distinct_form() -> None:
    analysis = analyze_book("sample", "They discuss ram today. " * 200 + "They discuss RAM today.")
    payload = build_corpus_payload([analysis], corpus_name="test", known_spellings={"RAM"})
    assert payload["global_word_frequency"]["RAM"] > 0
    assert "RAM" in payload["generation"]["known_case_spellings"]


def test_initial_article_a_does_not_create_a_capitalized_twin() -> None:
    result = frequencies("A dog arrived. They saw a dog. " * 10)
    assert result["a"] == 60
    assert "A" not in result


def test_first_person_pronoun_keeps_its_required_case_in_shouted_text() -> None:
    result = frequencies("I AM HERE. " * 10)
    assert result["I"] == 30
    assert "i" not in result
