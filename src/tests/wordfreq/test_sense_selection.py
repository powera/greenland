"""Tests for sense selection in wordfreq.translation.definitions."""

from typing import Any, Dict, List

from storage.models.schema import (
    SENSE_PROMINENCE_COMMON,
    SENSE_PROMINENCE_RARE,
    SENSE_PROMINENCE_UNCOMMON,
    SENSE_PROMINENCE_VERY_COMMON,
)
from wordfreq.translation.definitions import SENSE_PROMINENCE_ORDER, select_senses_to_add


def _senses(*pairs: Any) -> List[Dict[str, Any]]:
    """Build a definitions list from (definition, prominence) pairs."""
    return [{"definition": text, "sense_prominence": prominence} for text, prominence in pairs]


def _texts(senses: List[Dict[str, Any]]) -> List[str]:
    return [sense["definition"] for sense in senses]


class TestSelectSensesToAdd:
    """The 2-4 sense rule: always a couple, more only while they stay common."""

    def test_keeps_prominent_senses_beyond_the_minimum(self) -> None:
        selected = select_senses_to_add(
            _senses(
                ("a", SENSE_PROMINENCE_VERY_COMMON),
                ("b", SENSE_PROMINENCE_COMMON),
                ("c", SENSE_PROMINENCE_COMMON),
                ("d", SENSE_PROMINENCE_COMMON),
            )
        )
        assert _texts(selected) == ["a", "b", "c", "d"]

    def test_stops_once_senses_become_marginal(self) -> None:
        """One everyday sense plus obscure ones yields the minimum, not all four."""
        selected = select_senses_to_add(
            _senses(
                ("main", SENSE_PROMINENCE_VERY_COMMON),
                ("obscure a", SENSE_PROMINENCE_RARE),
                ("obscure b", SENSE_PROMINENCE_RARE),
                ("obscure c", SENSE_PROMINENCE_RARE),
            )
        )
        assert _texts(selected) == ["main", "obscure a"]

    def test_caps_at_max_senses(self) -> None:
        selected = select_senses_to_add(
            _senses(*[(f"sense {i}", SENSE_PROMINENCE_COMMON) for i in range(6)])
        )
        assert len(selected) == 4

    def test_orders_by_prominence(self) -> None:
        """Input order does not matter; the prominent sense comes first."""
        selected = select_senses_to_add(
            _senses(
                ("rare one", SENSE_PROMINENCE_RARE),
                ("main", SENSE_PROMINENCE_VERY_COMMON),
                ("second", SENSE_PROMINENCE_COMMON),
            )
        )
        assert _texts(selected) == ["main", "second"]

    def test_uncommon_sense_survives_as_the_second(self) -> None:
        """min_senses wins over the threshold, so 'arrive' keeps both senses."""
        selected = select_senses_to_add(
            _senses(
                ("reach a destination", SENSE_PROMINENCE_VERY_COMMON),
                ("make a formal appearance", SENSE_PROMINENCE_UNCOMMON),
            )
        )
        assert _texts(selected) == ["reach a destination", "make a formal appearance"]

    def test_single_sense(self) -> None:
        selected = select_senses_to_add(_senses(("only", SENSE_PROMINENCE_VERY_COMMON)))
        assert _texts(selected) == ["only"]

    def test_empty_input(self) -> None:
        assert select_senses_to_add([]) == []

    def test_missing_prominence_is_treated_as_common(self) -> None:
        """An unrated sense should not be discarded as if it were rare."""
        selected = select_senses_to_add(
            [{"definition": "x"}, {"definition": "y"}, {"definition": "z"}]
        )
        assert _texts(selected) == ["x", "y", "z"]

    def test_respects_explicit_limits(self) -> None:
        senses = _senses(*[(f"sense {i}", SENSE_PROMINENCE_COMMON) for i in range(5)])
        assert len(select_senses_to_add(senses, max_senses=2)) == 2
        assert len(select_senses_to_add(senses, max_senses=5)) == 5

    def test_prominence_order_matches_the_schema_values(self) -> None:
        """The prompt's enum must stay in sync with Lemma.sense_prominence."""
        from storage.models.schema import SENSE_PROMINENCE_VALUES

        assert set(SENSE_PROMINENCE_ORDER) == SENSE_PROMINENCE_VALUES
