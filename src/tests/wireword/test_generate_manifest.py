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
        "2s": "tú/usted",
        "3s": "él/ella",
        "1p": "nosotros/nosotras",
        "2p": "vosotros/vosotras/ustedes",
        "3p": "ellos/ellas",
    }


def test_generate_manifest_omits_conjugation_tense_metadata_for_other_languages(
    tmp_path: Path,
) -> None:
    _write_json_file(tmp_path / "wireword_nouns.json")

    success, manifest_path = generate_manifest(str(tmp_path), "ko")

    assert success
    manifest = _load_manifest(manifest_path)
    assert "grammar" not in manifest["config"]


def test_generate_manifest_includes_chinese_reading_config(tmp_path: Path) -> None:
    _write_json_file(tmp_path / "wireword_nouns.json")

    success, manifest_path = generate_manifest(str(tmp_path), "zh")

    assert success
    manifest = _load_manifest(manifest_path)

    assert manifest["config"]["reading"] == {
        "style": "ruby",
        "default_system": "pinyin",
        "systems": [
            {
                "id": "pinyin",
                "label": "Pinyin",
                "word_field": "target_pinyin",
                "grammatical_form_field": "target_pinyin",
                "alternatives_field": "target_alternatives_pinyin",
                "synonyms_field": "target_synonyms_pinyin",
                "sentence_translation_field": "pinyin",
            }
        ],
    }


def test_generate_manifest_includes_japanese_reading_config_and_voice_metadata(
    tmp_path: Path,
) -> None:
    _write_json_file(tmp_path / "wireword_nouns.json")

    success, manifest_path = generate_manifest(str(tmp_path), "ja")

    assert success
    manifest = _load_manifest(manifest_path)

    assert manifest["config"]["available_voices"] == ["sakura", "haruto"]
    assert manifest["config"]["default_voice"] == "sakura"
    assert manifest["config"]["reading"] == {
        "style": "ruby",
        "default_system": "hiragana",
        "systems": [
            {
                "id": "romaji",
                "label": "Romaji",
                "word_field": "target_romaji",
                "grammatical_form_field": "target_romaji",
                "alternatives_field": "target_alternatives_romaji",
                "synonyms_field": "target_synonyms_romaji",
                "sentence_translation_field": "romaji",
            },
            {
                "id": "hiragana",
                "label": "Hiragana",
                "word_field": "target_hiragana",
                "grammatical_form_field": "target_hiragana",
                "alternatives_field": "target_alternatives_hiragana",
                "synonyms_field": "target_synonyms_hiragana",
                "sentence_translation_field": "hiragana",
            },
        ],
    }
