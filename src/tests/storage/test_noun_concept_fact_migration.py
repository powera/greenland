"""The release migration uses reviewed senses and refuses incomplete coverage."""

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from storage.config.lemma_fact_registry import validate_lemma_fact

SCRIPT = Path(__file__).resolve().parents[3] / "migrations/20261012_migrate_noun_concept_facts.py"
_spec = importlib.util.spec_from_file_location("noun_concept_fact_migration", SCRIPT)
assert _spec is not None and _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


def _record(guid: str, label: str, facts: Dict[str, str]) -> Dict[str, Any]:
    return {"guid": guid, "concept_label": label, "pos_type": "noun", "facts": facts}


def test_reviewed_senses_migrate_both_booleans_and_preserve_other_data(tmp_path: Path) -> None:
    path = tmp_path / "base.jsonl"
    records = [
        _record("N1", "water", {"quantifiable": "true", "unrelated": "keep"}),
        _record("N2", "furniture", {"has_individual_instances": "false"}),
        _record("N3", "idea", {"quantifiable": "false"}),
    ]
    original = "".join(json.dumps(row) + "\n" for row in records)
    path.write_text(original)
    reviewed = {
        "N1": ("water", "non_individuated", "physical"),
        "N2": ("furniture", "collection", "physical"),
        "N3": ("idea", "individual", "abstract"),
    }
    # Values follow reviewed senses even when the legacy boolean disagrees.
    assert migration.migrate_release(tmp_path, reviewed_senses=reviewed) == 3
    assert path.read_text() == original
    assert migration.migrate_release(tmp_path, apply=True, reviewed_senses=reviewed) == 3
    migrated = [json.loads(line) for line in path.read_text().splitlines()]
    assert migrated[0]["facts"] == {
        "unrelated": "keep",
        "individuation": "non_individuated",
        "concreteness": "physical",
    }
    assert migrated[1]["facts"]["individuation"] == "collection"
    assert migrated[2]["facts"] == {"individuation": "individual", "concreteness": "abstract"}
    snapshot = path.read_bytes()
    assert migration.migrate_release(tmp_path, apply=True, reviewed_senses=reviewed) == 0
    assert path.read_bytes() == snapshot


def test_unknown_legacy_sense_fails_before_any_file_is_written(tmp_path: Path) -> None:
    first = tmp_path / "a.jsonl"
    second = tmp_path / "z.jsonl"
    first.write_text(json.dumps(_record("N1", "cat", {"quantifiable": "true"})) + "\n")
    second.write_text(json.dumps(_record("N2", "unknown", {"quantifiable": "false"})) + "\n")
    original = first.read_bytes()
    with pytest.raises(ValueError, match="Unreviewed"):
        migration.migrate_release(
            tmp_path, apply=True, reviewed_senses={"N1": ("cat", "individual", "physical")}
        )
    assert first.read_bytes() == original


def test_all_original_release_senses_have_both_dimensions() -> None:
    release_path = SCRIPT.parent.parent / "data/release"
    assert len(migration.REVIEWED_SENSES) == 30
    assert migration.migrate_release(release_path) == 0
    for path in release_path.rglob("*.jsonl"):
        for line in path.read_text().splitlines():
            if line.strip():
                facts = json.loads(line).get("facts", {})
                assert "quantifiable" not in facts
                assert "has_individual_instances" not in facts
                for dimension in ("individuation", "concreteness"):
                    if dimension in facts:
                        assert validate_lemma_fact(dimension, facts[dimension]) is None
