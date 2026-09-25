"""Unit tests for the curriculum rebalance builders."""

from typing import Optional

from reports.curriculum_bands import (
    UNRANKED_SENTINEL,
    RankEvidence,
    commonness_key,
    effective_rank,
    family_reserved_level,
    is_us_state,
    stable_commonness_key,
)
from reports.curriculum_relevel import (
    CORE_SUBTYPE_CAP,
    _balanced_sizes,
    _group_into_units,
    pack_core_levels,
    reserved_level,
    spill_from_core,
)
from reports.curriculum_sense_fixes import plan_core_polysemy
from reports.level_words import LevelWord, format_level_words
from storage.models.schema import Lemma, LemmaTier


def test_balanced_sizes_stay_near_target() -> None:
    sizes = _balanced_sizes(2242, 50)

    assert sum(sizes) == 2242
    assert min(sizes) == 44
    assert max(sizes) == 45


def test_balanced_sizes_split_oversized_cohort() -> None:
    assert _balanced_sizes(92, 2) == [46, 46]


def test_family_levels_come_from_reserved_section_values() -> None:
    mother = _lemma(1, "N35_032", "mother", 63, "very_common")
    mother.pos_subtype = "family_relation"

    assert family_reserved_level(mother) == 5


def test_us_state_cohort_uses_definition_not_every_region() -> None:
    state = _lemma(1, "N45_038", "Illinois", 49, "common")
    state.pos_subtype = "region"
    state.definition_text = "a state of the United States, in the midwest"
    country = _lemma(2, "N45_005", "Germany", 49, "common")
    country.pos_subtype = "region"
    country.definition_text = "a country in central Europe"

    assert is_us_state(state)
    assert not is_us_state(country)


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


def test_core_polysemy_keeps_word_form_pairs() -> None:
    noun = _lemma(1, "N01_001", "square", 8, "common")
    adjective = _lemma(2, "A01_001", "square", 15, "common", pos_type="adjective")
    feeling = _lemma(3, "N01_003", "fear", 13, "common")
    verb = _lemma(4, "V01_004", "fear", 14, "very_common", pos_type="verb")

    leaving, warnings = plan_core_polysemy([noun, adjective, feeling, verb])

    assert leaving == []
    assert warnings == []


def test_core_polysemy_keeps_allowed_headwords() -> None:
    animal = _lemma(1, "N01_001", "fish", 2, "very_common")
    food = _lemma(2, "N01_002", "fish", 8, "common")

    assert plan_core_polysemy([animal, food]) == ([], [])


def test_core_polysemy_moves_a_clearly_lesser_sense() -> None:
    main = _lemma(1, "A01_001", "open", 16, "very_common", pos_type="adjective")
    lesser = _lemma(2, "A01_002", "open", 19, "common", pos_type="adjective")

    leaving, warnings = plan_core_polysemy([main, lesser])

    assert leaving == [lesser]
    assert warnings == []


def test_core_polysemy_leaves_unclear_cases_with_a_warning() -> None:
    tied_a = _lemma(1, "A01_001", "light", 16, "very_common", pos_type="adjective")
    tied_b = _lemma(2, "A01_002", "light", 19, "very_common", pos_type="adjective")
    preposition = _lemma(3, "R01_003", "after", 7, "very_common", pos_type="preposition")
    conjunction = _lemma(4, "C01_004", "after", 6, "common", pos_type="conjunction")
    fixed_main = _lemma(5, "N01_005", "cap", 7, "very_common")
    fixed_lesser = _lemma(6, "N01_006", "cap", 4, "rare")

    leaving, warnings = plan_core_polysemy(
        [tied_a, tied_b, preposition, conjunction, fixed_main, fixed_lesser]
    )

    assert leaving == []
    assert sorted(warning.headword for warning in warnings) == ["after", "cap", "light"]


def test_hardcoded_verbs_are_pinned_only_from_the_core() -> None:
    like = _lemma(1, "V01_001", "like", 13, "common", pos_type="verb", subtype="emotional_state")
    be = _lemma(2, "V01_002", "be", 150, "very_common", pos_type="verb", subtype="existence")

    assert reserved_level(like) == 4
    assert reserved_level(be) is None


def test_oversized_core_subtype_spills_its_least_common_words() -> None:
    qualities = [
        _lemma(index, f"A01_{index:03d}", f"quality{index}", 19, "common", rank=100 + index * 100)
        for index in range(CORE_SUBTYPE_CAP + 5)
    ]

    spilled = spill_from_core(qualities, RankEvidence())

    assert set(spilled) == {lemma.id for lemma in qualities[CORE_SUBTYPE_CAP:]}


def test_core_caps_count_fixed_words_and_exclude_alcohol() -> None:
    drinks = [
        _lemma(index, f"N42_{index:03d}", f"drink{index}", 10, "common", rank=100 + index * 100)
        for index in range(12)
    ]
    for drink in drinks:
        drink.pos_subtype = "beverage"
    drinks[0].definition_text = "An alcoholic drink made from malt"

    spilled = spill_from_core(drinks, RankEvidence(), {"beverage": 3})

    assert spilled[drinks[0].id] == "core excludes alcohol"
    # Ten drinks in the core, three of them already fixed: the eleven
    # non-alcoholic candidates keep their seven commonest.
    assert sorted(spilled) == [drinks[0].id, *(drink.id for drink in drinks[8:])]


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


def test_named_units_keep_a_coherent_subtype_whole() -> None:
    states = [
        _lemma(index, f"N45_{index:03d}", f"state{index}", 240, "common", subtype="region")
        for index in range(50)
    ]

    units, small = _group_into_units(states, RankEvidence())

    assert [len(unit) for unit in units] == [50]
    assert small == []


def test_named_units_split_a_large_subtype_by_commonness() -> None:
    animals = [
        _lemma(index, f"N02_{index:03d}", f"animal{index}", 125, "common", rank=100 * (index + 1))
        for index in range(80)
    ]

    units, _small = _group_into_units(animals, RankEvidence())

    assert [len(unit) for unit in units] == [27, 27, 26]
    assert units[0][0].lemma_text == "animal0"


def test_core_levels_have_verbs_and_spread_function_words() -> None:
    pool: list[Lemma] = []
    next_id = 0
    for subtype in ("food", "animal", "vehicle", "clothing_accessory", "furniture", "tool"):
        for _index in range(25):
            pool.append(
                _lemma(
                    next_id, f"N{next_id:05d}", f"{subtype}{next_id}", 8, "common", subtype=subtype
                )
            )
            next_id += 1
    for _index in range(12):
        pool.append(
            _lemma(
                next_id,
                f"V{next_id:05d}",
                f"verb{next_id}",
                8,
                "common",
                pos_type="verb",
                subtype="physical_action",
            )
        )
        next_id += 1
    for _index in range(20):
        pool.append(
            _lemma(
                next_id,
                f"P{next_id:05d}",
                f"prep{next_id}",
                6,
                "common",
                pos_type="preposition",
                subtype="preposition_other",
            )
        )
        next_id += 1

    proposed = pack_core_levels(pool, RankEvidence(), {})

    levels = sorted(set(proposed.values()))
    assert min(levels) == 6
    by_id = {lemma.id: lemma for lemma in pool}
    for level in levels:
        members = [by_id[lemma_id] for lemma_id, assigned in proposed.items() if assigned == level]
        verbs = [lemma for lemma in members if lemma.pos_type == "verb"]
        function_words = [lemma for lemma in members if lemma.pos_type == "preposition"]
        assert 1 <= len(verbs) <= 5
        assert function_words
        assert 30 <= len(members) <= 40


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
