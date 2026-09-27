"""Unit tests for new-word level placement."""

from typing import Optional

from reports.level_candidates import (
    IndexRow,
    LevelIndex,
    PlacementQuery,
    core_evidence,
    detect_theme,
    level_candidates,
)

UNKNOWN = {"19th_books": 20000, "20th_books": 20000}


def _index(*rows: tuple[int, str, Optional[str], int, int]) -> LevelIndex:
    return LevelIndex(
        [
            IndexRow(lemma_id, pos, subtype, level, rank)
            for lemma_id, pos, subtype, level, rank in rows
        ],
        UNKNOWN,
    )


def _query(**overrides: object) -> PlacementQuery:
    fields: dict[str, object] = {
        "lemma_text": "word",
        "pos_type": "noun",
        "pos_subtype": "animal",
        "definition": "a thing",
        "rank": 8000,
    }
    fields.update(overrides)
    return PlacementQuery(**fields)  # type: ignore[arg-type]


def test_fixed_set_level_is_never_offered() -> None:
    index = _index((1, "noun", "region", 240, 9000), (2, "noun", "region", 150, 9000))

    levels = [
        candidate.level for candidate in level_candidates(_query(pos_subtype="region"), index)
    ]

    assert levels == [150]


def test_tag_places_even_a_common_word_in_its_theme() -> None:
    query = _query(rank=900, tags=("legal",))

    theme = detect_theme(query, _index())
    assert theme is not None and theme[0].name == "legal"


def test_theme_subtype_ignored_for_common_words() -> None:
    assert detect_theme(_query(pos_subtype="legal_concept", rank=1200), _index()) is None
    theme = detect_theme(_query(pos_subtype="legal_concept", rank=9000), _index())
    assert theme is not None and theme[0].name == "legal"


def test_corpus_enrichment_detects_theme() -> None:
    legal = _query(rank=9000, corpus_ranks={"legal_scotus": 800, "20th_books": 12000})
    general = _query(rank=9000, corpus_ranks={"legal_scotus": 800, "20th_books": 1500})

    theme = detect_theme(legal, _index())
    assert theme is not None and theme[0].name == "legal"
    assert detect_theme(general, _index()) is None


def test_core_needs_rank_and_learner_list() -> None:
    index = _index()
    common = _query(rank=1200, tiers=(("cefr", "A2"),))

    assert core_evidence(common, index) is None
    assert core_evidence(_query(rank=1200), index) is not None
    assert core_evidence(_query(rank=1200, tiers=(("cefr", "C1"),)), index) is not None
    assert core_evidence(_query(rank=7000, tiers=(("cefr", "A1"),)), index) is not None


def test_uncommon_word_goes_to_the_named_unit_holding_most_of_its_subtype() -> None:
    index = _index(
        (1, "noun", "animal", 12, 900),
        (2, "noun", "animal", 120, 6000),
        (3, "noun", "animal", 125, 7000),
        (4, "noun", "animal", 125, 8000),
    )

    levels = [candidate.level for candidate in level_candidates(_query(), index)]

    assert levels == [125, 120]


def test_core_word_goes_to_the_core_level_with_the_nearest_ranks() -> None:
    index = _index(
        (1, "noun", "animal", 8, 400),
        (2, "noun", "animal", 16, 3000),
        (3, "noun", "animal", 120, 6000),
    )
    query = _query(rank=2500, tiers=(("cambridge_yle", "movers"),))

    levels = [candidate.level for candidate in level_candidates(query, index)]

    assert levels == [16, 8, 120]


def test_scoring_a_placed_lemma_leaves_it_out_of_the_counts() -> None:
    index = _index((1, "noun", "animal", 120, 6000), (2, "noun", "animal", 125, 7000))

    levels = [candidate.level for candidate in level_candidates(_query(exclude_lemma_id=2), index)]

    assert levels == [120]


def test_unheld_subtype_falls_back_to_its_curriculum_theme() -> None:
    index = _index((1, "noun", "plant", 130, 6000))

    candidates = level_candidates(_query(pos_subtype="natural_feature"), index)

    assert [candidate.level for candidate in candidates] == [130]
    assert "same theme nature" in candidates[0].reason
