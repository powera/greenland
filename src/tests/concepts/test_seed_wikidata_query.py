"""Tests for Wikidata class-query construction and result extraction."""

from typing import Any, Dict, Optional

import pytest

from concepts.seed import wikidata_query
from concepts.seed.wikidata_query import PRESET_CLASS_QIDS, build_class_query, query_class_qids


def _query(pattern: str = "instance-tree", **overrides: Any) -> str:
    kwargs: Dict[str, Any] = {
        "class_qid": "Q4022",
        "pattern": pattern,
        "country_qid": None,
        "min_sitelinks": 250,
        "limit": 1000,
    }
    kwargs.update(overrides)
    return build_class_query(**kwargs)


def test_instance_tree_walks_the_subclass_chain() -> None:
    assert "?item wdt:P31/wdt:P279* wd:Q4022 ." in _query("instance-tree")


def test_direct_instance_does_not_walk_subclasses() -> None:
    sparql = _query("direct-instance")

    assert "?item wdt:P31 wd:Q4022 ." in sparql
    assert "wdt:P279*" not in sparql


def test_subclass_tree_matches_classes_rather_than_instances() -> None:
    assert "?item wdt:P279* wd:Q4022 ." in _query("subclass-tree")


def test_country_constraint_is_optional() -> None:
    assert "wdt:P17" not in _query()
    assert "?item wdt:P17 wd:Q183 ." in _query(country_qid="Q183")


def test_thresholds_and_limits_are_applied() -> None:
    sparql = _query(min_sitelinks=42, limit=7)

    assert "FILTER(?sitelinks >= 42)" in sparql
    assert sparql.endswith("LIMIT 7")


def test_lowercase_qids_are_normalized() -> None:
    assert "wd:Q4022" in _query(class_qid="q4022")


def test_invalid_class_qid_is_rejected() -> None:
    with pytest.raises(ValueError):
        _query(class_qid="not-a-qid")


def test_presets_all_name_real_qids() -> None:
    assert PRESET_CLASS_QIDS["geography_river"] == "Q4022"
    assert all(qid.startswith("Q") and qid[1:].isdigit() for qid in PRESET_CLASS_QIDS.values())


def test_query_class_qids_extracts_and_normalizes_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_sparql(_sparql: str) -> Optional[Dict[str, Any]]:
        return {
            "results": {
                "bindings": [
                    {"item": {"value": "http://www.wikidata.org/entity/Q1"}},
                    {"item": {"value": "http://www.wikidata.org/entity/Q2"}},
                    {"item": {"value": "http://www.wikidata.org/entity/not-a-qid"}},
                    {},
                ]
            }
        }

    monkeypatch.setattr(wikidata_query, "query_wikidata_sparql", fake_sparql)

    assert query_class_qids("SELECT ?item WHERE {}") == ["Q1", "Q2"]


def test_query_class_qids_raises_when_the_endpoint_never_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wikidata_query, "query_wikidata_sparql", lambda _sparql: None)

    with pytest.raises(RuntimeError):
        query_class_qids("SELECT ?item WHERE {}")
