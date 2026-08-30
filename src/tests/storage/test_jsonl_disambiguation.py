"""Tests that the JSONL backend round-trips the release disambiguation map.

A lemma's sense used to survive only inside the ``concept_label`` parenthetical
(``"fine (quality)"``), so a database rebuilt from the release had
``disambiguation`` NULL for every disambiguated lemma. The base record now
carries a ``{language: sense}`` map instead, English included, and
``concept_label`` is display text that nothing parses. These tests pin both
directions of the round trip.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from storage.backend.jsonl import models
from storage.backend.jsonl.storage import JSONLStorage

CATEGORY = ("lemmas", "adjectives", "quality")


def _write_jsonl(file_path: Path, records: List[Dict[str, Any]]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _build_release_tree(release_path: Path) -> Path:
    """Write a release tree with a disambiguated and an undisambiguated lemma."""
    category_path = release_path.joinpath(*CATEGORY)
    _write_jsonl(
        category_path / "base.jsonl",
        [
            {
                "guid": "A05_001",
                "pos_type": "adjective",
                "pos_subtype": "quality",
                "concept_label": "fine (quality)",
                "concept_definition": "of high quality",
                "translations": {"en": "fine", "lt": "puikus"},
                "disambiguation": {"en": "quality", "lt": "kokybė"},
                "difficulty_level": 5,
            },
            {
                "guid": "A05_002",
                "pos_type": "adjective",
                "pos_subtype": "quality",
                "concept_label": "good",
                "concept_definition": "having desirable qualities",
                "translations": {"en": "good", "lt": "geras"},
                "difficulty_level": 9,
            },
        ],
    )
    return category_path


def _load(release_path: Path) -> JSONLStorage:
    storage = JSONLStorage(str(release_path))
    storage.ensure_initialized()
    return storage


def test_the_english_sense_lands_on_the_lemma(tmp_path: Path) -> None:
    _build_release_tree(tmp_path)
    lemma = _load(tmp_path).lemmas["A05_001"]

    assert lemma.disambiguation == "quality"


def test_other_languages_land_beside_it(tmp_path: Path) -> None:
    _build_release_tree(tmp_path)
    lemma = _load(tmp_path).lemmas["A05_001"]

    assert lemma.translation_disambiguations == {"lt": "kokybė"}


def test_an_undisambiguated_label_yields_no_disambiguation(tmp_path: Path) -> None:
    _build_release_tree(tmp_path)
    lemma = _load(tmp_path).lemmas["A05_002"]

    assert lemma.disambiguation is None


def test_the_headword_never_keeps_the_parenthetical(tmp_path: Path) -> None:
    """lemma_text is translations.en; the sense lives in the map."""
    _build_release_tree(tmp_path)
    lemma = _load(tmp_path).lemmas["A05_001"]

    assert lemma.lemma_text == "fine"


def test_export_rebuilds_the_label_from_the_headword_and_sense(tmp_path: Path) -> None:
    """A lemma built in memory has no concept_label, but still exports its sense."""
    storage = JSONLStorage(str(tmp_path))
    lemma = models.Lemma()
    lemma.guid = "A05_003"
    lemma.pos_type = "adjective"
    lemma.pos_subtype = "quality"
    lemma.lemma_text = "sharp"
    lemma.disambiguation = "pointed"

    assert storage._extract_base_data(lemma)["concept_label"] == "sharp (pointed)"


def test_export_leaves_an_undisambiguated_label_bare(tmp_path: Path) -> None:
    storage = JSONLStorage(str(tmp_path))
    lemma = models.Lemma()
    lemma.guid = "A05_004"
    lemma.pos_type = "adjective"
    lemma.lemma_text = "good"

    assert storage._extract_base_data(lemma)["concept_label"] == "good"


def test_a_label_is_never_a_source_of_senses(tmp_path: Path) -> None:
    """A record with a parenthetical but no map loads no sense at all."""
    category_path = _build_release_tree(tmp_path)
    _write_jsonl(
        category_path / "base.jsonl",
        [
            {
                "guid": "A05_001",
                "pos_type": "adjective",
                "concept_label": "fine (quality)",
                "translations": {"en": "fine"},
            }
        ],
    )

    lemma = _load(tmp_path).lemmas["A05_001"]
    assert lemma.lemma_text == "fine"
    assert lemma.disambiguation is None


def test_the_map_survives_a_load_export_round_trip(tmp_path: Path) -> None:
    _build_release_tree(tmp_path)
    storage = _load(tmp_path)

    record = storage._extract_base_data(storage.lemmas["A05_001"])
    assert record["disambiguation"] == {"en": "quality", "lt": "kokybė"}
    assert record["concept_label"] == "fine (quality)"
