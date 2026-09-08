"""Unit tests for the temporary curriculum proposal builders."""

from collections import Counter

from reports.curriculum_relevel import _balanced_sizes
from reports.curriculum_sense_fixes import build_moves
from storage.models.schema import Lemma


def test_balanced_sizes_stay_near_target() -> None:
    sizes = _balanced_sizes(2242, 50)

    assert sum(sizes) == 2242
    assert min(sizes) == 44
    assert max(sizes) == 45


def test_balanced_sizes_split_oversized_cohort() -> None:
    assert _balanced_sizes(92, 2) == [46, 46]


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


def test_sense_fixes_preserve_counts_and_are_idempotent() -> None:
    lemmas = [
        _lemma(1, "N01_001", "example", 10, "very_common"),
        _lemma(2, "N01_002", "example", 10, "rare"),
        _lemma(3, "N01_003", "filler", 28, "common"),
    ]

    class FakeSession:
        def query(self, _model: type[Lemma]) -> "FakeSession":
            return self

        def filter(self, *_conditions: object) -> "FakeSession":
            return self

        def all(self) -> list[Lemma]:
            return lemmas

    moves = build_moves(FakeSession())  # type: ignore[arg-type]

    assert Counter(move.old_level for move in moves) == Counter(move.new_level for move in moves)
    assert {(move.guid, move.new_level) for move in moves} == {
        ("N01_002", 28),
        ("N01_003", 10),
    }
    new_levels = {move.lemma_id: move.new_level for move in moves}
    for lemma in lemmas:
        if lemma.id in new_levels:
            lemma.difficulty_level = new_levels[lemma.id]
    assert build_moves(FakeSession()) == []  # type: ignore[arg-type]
