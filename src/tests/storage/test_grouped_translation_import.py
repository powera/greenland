"""Tests that the initial release import does not drop grouped translations.

``data/release/lemmas/*/*/`` holds three kinds of file beside ``base.jsonl``:

* per-language files (``lt.jsonl``, ``en.jsonl``) with inflections and facts;
* grouped translation files - ``secondary.jsonl`` for every Tier 3/4 language
  and one per named group (``ancient.jsonl``);
* ``audio.jsonl``, which is audio metadata rather than lemma content.

Only the first is a language file. The loader used to treat all three that way,
so "secondary" and "ancient" were read as if they were language codes and their
``translations`` maps - tens of thousands of translations across the real tree -
never reached the database. These tests pin the routing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from storage.admin.bootstrap import bootstrap_from_release
from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.backend.jsonl.storage import JSONLStorage
from storage.models.schema import Lemma, LemmaTranslation

CATEGORY = ("lemmas", "nouns", "food")


def _write_jsonl(file_path: Path, records: List[Dict[str, Any]]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _build_release_tree(release_path: Path) -> Path:
    """Write a one-lemma release tree with every kind of sibling file."""
    category_path = release_path.joinpath(*CATEGORY)
    _write_jsonl(
        category_path / "base.jsonl",
        [
            {
                "guid": "N06_001",
                "pos_type": "noun",
                "pos_subtype": "food",
                "concept_label": "bread",
                "concept_definition": "a baked staple",
                "translations": {"en": "bread", "lt": "duona"},
                "translation_metadata": {"lt": {"translation_status": "conventional"}},
                "difficulty_level": 1,
            }
        ],
    )
    _write_jsonl(
        category_path / "secondary.jsonl",
        [{"guid": "N06_001", "translations": {"ta": "ரொட்டி", "pl": "chleb"}}],
    )
    _write_jsonl(
        category_path / "ancient.jsonl",
        [
            {
                "guid": "N06_001",
                "translations": {"la": "panis", "grc": "ἄρτος"},
                "translation_metadata": {"la": {"translation_status": "conventional"}},
            }
        ],
    )
    _write_jsonl(
        category_path / "audio.jsonl",
        [
            {
                "guid": "N06_001",
                "english": "bread",
                "audio": [
                    {
                        "language_code": "lt",
                        "voice_name": "alloy",
                        "filename": "N06_001.mp3",
                        "status": "approved",
                    }
                ],
            }
        ],
    )
    return category_path


def _load(release_path: Path) -> JSONLStorage:
    storage = JSONLStorage(str(release_path))
    storage.ensure_initialized()
    return storage


def test_secondary_translations_are_loaded(tmp_path: Path) -> None:
    _build_release_tree(tmp_path)
    lemma = _load(tmp_path).lemmas["N06_001"]

    assert lemma.translations["ta"] == "ரொட்டி"
    assert lemma.translations["pl"] == "chleb"


def test_named_group_translations_are_loaded(tmp_path: Path) -> None:
    _build_release_tree(tmp_path)
    lemma = _load(tmp_path).lemmas["N06_001"]

    assert lemma.translations["la"] == "panis"
    assert lemma.translations["grc"] == "ἄρτος"


def test_group_file_stems_never_become_languages(tmp_path: Path) -> None:
    """ "secondary", "ancient" and "audio" are file names, not language codes."""
    _build_release_tree(tmp_path)
    lemma = _load(tmp_path).lemmas["N06_001"]

    for not_a_language in ("secondary", "ancient", "audio"):
        assert not_a_language not in lemma.translations
        assert not_a_language not in lemma.derivative_forms
        assert not_a_language not in lemma.base_forms


def test_base_translations_win_over_a_group_file(tmp_path: Path) -> None:
    """base.jsonl is the primary record; a group file must not redefine it."""
    category_path = _build_release_tree(tmp_path)
    _write_jsonl(
        category_path / "secondary.jsonl",
        [{"guid": "N06_001", "translations": {"lt": "WRONG", "ta": "ரொட்டி"}}],
    )

    lemma = _load(tmp_path).lemmas["N06_001"]
    assert lemma.translations["lt"] == "duona"
    assert lemma.translations["ta"] == "ரொட்டி"


def test_translation_metadata_is_carried_from_both_sources(tmp_path: Path) -> None:
    _build_release_tree(tmp_path)
    lemma = _load(tmp_path).lemmas["N06_001"]

    assert lemma.translation_metadata["lt"]["translation_status"] == "conventional"
    assert lemma.translation_metadata["la"]["translation_status"] == "conventional"


def test_a_group_file_for_an_unknown_guid_is_ignored(tmp_path: Path) -> None:
    category_path = _build_release_tree(tmp_path)
    _write_jsonl(
        category_path / "secondary.jsonl",
        [{"guid": "N06_999", "translations": {"ta": "orphan"}}],
    )

    storage = _load(tmp_path)
    assert set(storage.lemmas) == {"N06_001"}
    assert "ta" not in storage.lemmas["N06_001"].translations


def test_bootstrap_lands_grouped_translations_in_sqlite(tmp_path: Path) -> None:
    """The whole point: these translations must reach the real schema."""
    release_path = tmp_path / "release"
    _build_release_tree(release_path)

    database_path = tmp_path / "from-release.sqlite"
    config = DataSourceConfig(sqlite_path=str(database_path))
    bootstrap_from_release(config, release_path, include_frequency_data=False)

    session = create_session(config)
    try:
        lemma = session.query(Lemma).filter(Lemma.guid == "N06_001").one()
        translations = {
            row.language_code: row
            for row in session.query(LemmaTranslation).filter(LemmaTranslation.lemma_id == lemma.id)
        }
        assert translations["ta"].translation == "ரொட்டி"
        assert translations["pl"].translation == "chleb"
        assert translations["la"].translation == "panis"
        assert translations["grc"].translation == "ἄρτος"
        assert translations["lt"].translation_status == "conventional"
        assert "secondary" not in translations
        assert "ancient" not in translations
    finally:
        session.close()
