"""Unit tests for the temporary curriculum proposal builders."""

from reports.curriculum_relevel import _balanced_sizes, _family_reserved_level, _is_us_state
from reports.curriculum_sense_fixes import plan_sense_levels
from storage.models.schema import Lemma


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

    assert _family_reserved_level(mother) == 1


def test_us_state_cohort_uses_definition_not_every_region() -> None:
    state = _lemma(1, "N45_038", "Illinois", 49, "common")
    state.pos_subtype = "region"
    state.definition_text = "a state of the United States, in the midwest"
    country = _lemma(2, "N45_005", "Germany", 49, "common")
    country.pos_subtype = "region"
    country.definition_text = "a country in central Europe"

    assert _is_us_state(state)
    assert not _is_us_state(country)


def _lemma(
    lemma_id: int,
    guid: str,
    text: str,
    level: int,
    prominence: str,
) -> Lemma:
    return Lemma(
        id=lemma_id,
        guid=guid,
        lemma_text=text,
        definition_text=f"definition of {text}",
        pos_type="noun",
        pos_subtype="concept_idea",
        difficulty_level=level,
        sense_prominence=prominence,
    )


def test_sense_fixes_space_prominence_ties_idempotently() -> None:
    lemmas = [
        _lemma(1, "N01_001", "example", 10, "very_common"),
        _lemma(2, "N01_002", "example", 10, "rare"),
        _lemma(3, "N01_003", "filler", 28, "common"),
    ]

    new_levels = plan_sense_levels(lemmas)

    assert new_levels == {1: 10, 2: 28, 3: 28}
    for lemma in lemmas:
        lemma.difficulty_level = new_levels[lemma.id]
    assert plan_sense_levels(lemmas) == new_levels
