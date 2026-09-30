"""Unit tests for the curriculum band helpers and the level word listing."""

from typing import Optional

from reports.curriculum_bands import (
    UNRANKED_SENTINEL,
    RankEvidence,
    commonness_key,
    effective_rank,
    family_reserved_level,
    stable_commonness_key,
)
from reports.level_words import LevelWord, format_level_words
from storage.models.schema import Lemma, LemmaTier


def test_family_levels_come_from_reserved_section_values() -> None:
    mother = _lemma(1, "N35_032", "mother", 63, "very_common")
    mother.pos_subtype = "family_relation"

    assert family_reserved_level(mother) == 5


def test_tier_evidence_never_outranks_corpus_evidence() -> None:
    ranked = _lemma(1, "N01_001", "ranked", 10, "common", rank=5000)
    yle_only = _lemma(2, "N01_002", "yle_only", 10, "common", rank=None)
    evidence = RankEvidence(
        tiers_by_lemma={2: [LemmaTier(lemma_id=2, source="cambridge_yle", tier_name="starters")]}
    )

    ordered = sorted([yle_only, ranked], key=lambda lemma: commonness_key(lemma, evidence))

    assert ordered == [ranked, yle_only]


def test_tier_derived_rank_without_corpus_evidence_reads_as_unranked() -> None:
    ranked = _lemma(1, "N01_001", "ranked", 10, "common", rank=5000)
    vodka = _lemma(2, "N01_002", "vodka", 10, "common", rank=3758)
    evidence = RankEvidence(no_corpus_ids=frozenset({2}))

    ordered = sorted([vodka, ranked], key=lambda lemma: commonness_key(lemma, evidence))

    assert ordered == [ranked, vodka]
    assert effective_rank(vodka, evidence) == UNRANKED_SENTINEL
    assert effective_rank(vodka, RankEvidence()) == 3758


def test_missing_rank_sorts_with_the_unranked_sentinel() -> None:
    missing = _lemma(1, "N01_001", "missing", 10, "common", rank=None)
    sentinel = _lemma(2, "N01_002", "sentinel", 10, "common", rank=UNRANKED_SENTINEL)

    assert commonness_key(missing, RankEvidence())[0] == commonness_key(sentinel, RankEvidence())[0]


def test_current_level_wins_when_ranks_are_close() -> None:
    earlier = _lemma(1, "N01_001", "earlier", 8, "common", rank=3000)
    slightly_commoner = _lemma(2, "N01_002", "commoner", 12, "common", rank=2500)
    much_commoner = _lemma(3, "N01_003", "much", 12, "common", rank=900)

    ordered = sorted(
        [slightly_commoner, earlier, much_commoner],
        key=lambda lemma: stable_commonness_key(lemma, RankEvidence()),
    )

    assert ordered == [much_commoner, earlier, slightly_commoner]


def test_level_words_group_by_level_and_subtype() -> None:
    words = [
        LevelWord(8, "noun", "food", "rice", None, "N01_002"),
        LevelWord(8, "noun", "food", "bread", None, "N01_001"),
        LevelWord(8, "verb", "physical_action", "cut", None, "V01_001"),
        LevelWord(2, "noun", "animal", "fish", "the animal", "N02_001"),
        LevelWord(8, "noun", "food", "fish", "as food", "N02_002"),
        LevelWord(1050, "noun", "legal", "voir dire", None, "N03_001"),
    ]

    text = format_level_words(words, bands=("core",))

    assert "## Level 2 (1 words)\n  noun/animal (1): fish [the animal]" in text
    assert "  noun/food (3): bread, fish [as food], rice" in text
    assert text.index("noun/food") < text.index("verb/physical_action")
    assert "voir dire" not in text


def _lemma(
    lemma_id: int,
    guid: str,
    text: str,
    level: int,
    prominence: str,
    *,
    rank: Optional[int] = 1000,
    pos_type: str = "noun",
    subtype: str = "concept_idea",
) -> Lemma:
    return Lemma(
        id=lemma_id,
        guid=guid,
        lemma_text=text,
        definition_text=f"definition of {text}",
        pos_type=pos_type,
        pos_subtype=subtype,
        difficulty_level=level,
        sense_prominence=prominence,
        frequency_rank=rank,
    )
