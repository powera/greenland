import json
from pathlib import Path
from typing import Any

from wireword.generate_manifest import generate_manifest


def _write_json_file(path: Path) -> None:
    path.write_text("[]", encoding="utf-8")


def _load_manifest(manifest_path: str) -> dict[str, Any]:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def test_generate_manifest_includes_lithuanian_conjugation_tense_metadata(tmp_path: Path) -> None:
    _write_json_file(tmp_path / "wireword_nouns.json")

    success, manifest_path = generate_manifest(str(tmp_path), "lt")

    assert success
    manifest = _load_manifest(manifest_path)
    tenses = manifest["config"]["grammar"]["conjugation"]["tenses"]

    assert [tense["id"] for tense in tenses] == [
        "past",
        "pres",
        "fut",
        "conditional",
        "imperative",
    ]
    assert manifest["config"]["grammar"]["conjugation"]["person_labels"] == {
        "1s": "aš",
        "2s": "tu",
        "3s": "jis/ji",
        "1p": "mes",
        "2p": "jūs",
        "3p": "jie/jos",
    }


def test_generate_manifest_includes_french_conjugation_tense_metadata(tmp_path: Path) -> None:
    _write_json_file(tmp_path / "wireword_nouns.json")

    success, manifest_path = generate_manifest(str(tmp_path), "fr")

    assert success
    manifest = _load_manifest(manifest_path)
    tenses = manifest["config"]["grammar"]["conjugation"]["tenses"]

    assert [tense["id"] for tense in tenses] == ["past", "pres", "fut", "impf"]
    assert tenses[0]["label"] == "Passé composé"
    assert manifest["config"]["grammar"]["conjugation"]["person_labels"] == {
        "1s": "je",
        "2s": "tu",
        "3s": "il/elle/on",
        "1p": "nous",
        "2p": "vous",
        "3p": "ils/elles",
    }


def test_generate_manifest_includes_spanish_conjugation_tense_metadata(tmp_path: Path) -> None:
    _write_json_file(tmp_path / "wireword_nouns.json")

    success, manifest_path = generate_manifest(str(tmp_path), "es")

    assert success
    manifest = _load_manifest(manifest_path)
    tenses = manifest["config"]["grammar"]["conjugation"]["tenses"]

    assert [tense["id"] for tense in tenses] == ["past", "pres", "fut"]
    assert manifest["config"]["grammar"]["conjugation"]["person_labels"] == {
        "1s": "yo",
        "2s": "tú",
        "3s": "él/ella/usted",
        "1p": "nosotros",
        "2p": "vosotros",
        "3p": "ellos/ellas/ustedes",
    }


def test_generate_manifest_omits_conjugation_tense_metadata_for_other_languages(
    tmp_path: Path,
) -> None:
    _write_json_file(tmp_path / "wireword_nouns.json")

    success, manifest_path = generate_manifest(str(tmp_path), "ko")

    assert success
    manifest = _load_manifest(manifest_path)
    assert "grammar" not in manifest["config"]
