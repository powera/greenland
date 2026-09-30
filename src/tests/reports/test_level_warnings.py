"""Unit tests for the level warnings report."""

from typing import Optional

from reports.level_warnings import LemmaRow, find_duplicate_headwords, find_level_sizes
from wordfreq.data.cohorts import DAYS_AND_MONTHS


def test_level_size_separates_allowed_from_ideal() -> None:
    rows = (
        [_row(index, f"small{index}", 3) for index in range(15)]
        + [_row(100 + index, f"snug{index}", 4) for index in range(22)]
        + [_row(200 + index, f"fine{index}", 5) for index in range(30)]
    )

    findings = {finding.level: finding.detail for finding in find_level_sizes(rows, max_level=30)}

    assert findings == {
        3: "15 words, outside the allowed 20-50",
        4: "22 words, outside the ideal 25-40",
    }


def test_level_size_skips_a_fixed_set() -> None:
    rows = [_row(index, f"month{index}", DAYS_AND_MONTHS.level) for index in range(19)]

    assert find_level_sizes(rows, max_level=30) == []


def test_duplicate_headword_flags_two_core_senses() -> None:
    rows = [
        _row(1, "child", 5, disambiguation="young person", subtype="human"),
        _row(2, "child", 5, disambiguation="offspring", subtype="family_relation"),
        _row(3, "bank", 12, disambiguation="money"),
        _row(4, "bank", 250, disambiguation="river"),
    ]

    findings = find_duplicate_headwords(rows)

    assert [finding.word for finding in findings] == ["child"]


def test_duplicate_headword_keeps_form_pairs_and_allowed_words() -> None:
    rows = [
        _row(1, "fear", 9, pos_type="noun"),
        _row(2, "fear", 17, pos_type="verb"),
        _row(3, "fish", 2, disambiguation="animal"),
        _row(4, "fish", 7, disambiguation="food"),
    ]

    assert find_duplicate_headwords(rows) == []


def _row(
    lemma_id: int,
    text: str,
    level: int,
    *,
    disambiguation: Optional[str] = None,
    pos_type: str = "noun",
    subtype: str = "concept_idea",
) -> LemmaRow:
    return LemmaRow(
        lemma_id=lemma_id,
        guid=f"N01_{lemma_id:03d}",
        lemma_text=text,
        disambiguation=disambiguation,
        pos_type=pos_type,
        pos_subtype=subtype,
        level=level,
        frequency_rank=1000,
        overridden=False,
    )
