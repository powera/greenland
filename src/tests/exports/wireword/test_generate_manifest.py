import json
from pathlib import Path
from typing import Any

from exports.wireword.generate_manifest import (
    _slugify_language_name,
    calculate_file_md5,
    generate_manifest,
)


def _write_json_file(path: Path, data: str = "[]") -> None:
    path.write_text(data, encoding="utf-8")


def _write_level_file(tmp_path: Path, start: int = 1, end: int = 5) -> Path:
    """Create a minimal wireword_levels_X_Y.json so the manifest discovers it."""
    p = tmp_path / f"wireword_levels_{start}_{end}.json"
    _write_json_file(p)
    return p


def _load_manifest(manifest_path: str) -> dict[str, Any]:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def test_generate_manifest_includes_lithuanian_conjugation_tense_metadata(tmp_path: Path) -> None:
    _write_level_file(tmp_path)

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
    _write_level_file(tmp_path)

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
    _write_level_file(tmp_path)

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
    _write_level_file(tmp_path)

    success, manifest_path = generate_manifest(str(tmp_path), "ko")

    assert success
    manifest = _load_manifest(manifest_path)
    assert "grammar" not in manifest["config"]


def test_generate_manifest_includes_chinese_reading_config(tmp_path: Path) -> None:
    _write_level_file(tmp_path)

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
    _write_level_file(tmp_path)

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


def test_generate_manifest_discovers_level_range_files(tmp_path: Path) -> None:
    """Level-range word files are discovered and listed in the manifest."""
    _write_level_file(tmp_path, 1, 5)
    _write_level_file(tmp_path, 6, 10)

    success, manifest_path = generate_manifest(str(tmp_path), "lt")

    assert success
    manifest = _load_manifest(manifest_path)
    word_files = manifest["word_files"]
    assert len(word_files) == 2
    assert word_files[0]["id"] == "levels_1_5"
    assert word_files[0]["filename"] == "wireword_levels_1_5.json"
    assert word_files[0]["display_name"] == "Levels 1-5"
    assert word_files[0]["levels"] == [1, 2, 3, 4, 5]
    assert word_files[0]["type"] == "words"
    assert word_files[0]["required"] is True
    assert word_files[1]["id"] == "levels_6_10"
    assert word_files[1]["levels"] == [6, 7, 8, 9, 10]


def test_generate_manifest_cdn_base_uses_md5_filenames(tmp_path: Path) -> None:
    """When cdn_base is set, filenames use the file's MD5 hash."""
    level_path = _write_level_file(tmp_path, 1, 5)
    expected_md5 = calculate_file_md5(str(level_path))

    success, manifest_path = generate_manifest(
        str(tmp_path), "lt", cdn_base="https://wireword.trakaido.com"
    )

    assert success
    manifest = _load_manifest(manifest_path)
    assert manifest["config"]["cdn_base"] == "https://wireword.trakaido.com"
    word_file = manifest["word_files"][0]
    assert word_file["filename"] == f"{expected_md5}.json"
    assert word_file["md5"] == expected_md5


def test_generate_manifest_no_cdn_base_uses_readable_filenames(tmp_path: Path) -> None:
    """Without cdn_base, filenames stay human-readable."""
    _write_level_file(tmp_path, 1, 5)

    success, manifest_path = generate_manifest(str(tmp_path), "lt")

    assert success
    manifest = _load_manifest(manifest_path)
    assert "cdn_base" not in manifest["config"]
    assert manifest["word_files"][0]["filename"] == "wireword_levels_1_5.json"


def test_generate_manifest_level_file_word_count_and_groups(tmp_path: Path) -> None:
    """Word count and groups are extracted from level-range file contents."""
    data = json.dumps(
        [
            {"level": 1, "group": "Animals", "guid": "N01_001"},
            {"level": 2, "group": "Food", "guid": "N01_002"},
        ]
    )
    _write_json_file(tmp_path / "wireword_levels_1_5.json", data)

    success, manifest_path = generate_manifest(str(tmp_path), "lt")

    assert success
    manifest = _load_manifest(manifest_path)
    wf = manifest["word_files"][0]
    assert wf["word_count"] == 2
    assert wf["groups"] == ["Animals", "Food"]


def test_generate_manifest_sorts_level_files_numerically(tmp_path: Path) -> None:
    """Level-range files are sorted by start level, not lexicographically."""
    _write_level_file(tmp_path, 11, 15)
    _write_level_file(tmp_path, 1, 5)
    _write_level_file(tmp_path, 6, 10)

    success, manifest_path = generate_manifest(str(tmp_path), "lt")

    assert success
    manifest = _load_manifest(manifest_path)
    ids = [wf["id"] for wf in manifest["word_files"]]
    assert ids == ["levels_1_5", "levels_6_10", "levels_11_15"]


def test_generate_manifest_uses_zh_tw_as_its_own_language(tmp_path: Path) -> None:
    """zh-tw keeps its own language_code, but the base language's name.

    It used to be written as language "zh" plus simplified_chinese=False and
    labeled zh_Hant, then as its own language named "chinese_taiwan".  Now that
    a dialect is served as a regional *variant* of its base language, the name
    collapses back to "chinese": the client keys its language-level state
    (stats namespace, grammar lessons, UI strings) off that name, and a variant
    shares all of it.  The variety travels in language_code and "variant".
    """
    _write_level_file(tmp_path)

    success, manifest_path = generate_manifest(str(tmp_path), "zh-tw")

    assert success
    manifest = _load_manifest(manifest_path)
    assert manifest["language_code"] == "zh-tw"
    assert manifest["language"] == "chinese"
    assert manifest["variant"] == "zh-tw"


def test_generate_manifest_variant_matches_base_language_name(tmp_path: Path) -> None:
    """A variant's manifest is told apart from its base by variant, not name."""
    _write_level_file(tmp_path)

    success, base_path = generate_manifest(str(tmp_path), "es")
    assert success
    base = _load_manifest(base_path)

    success, variant_path = generate_manifest(str(tmp_path), "es-419")
    assert success
    variant = _load_manifest(variant_path)

    assert variant["language"] == base["language"]
    assert variant["language_code"] == "es-419"
    assert variant["variant"] == "es-419"
    # The base language is not a variant of anything, so it carries no field.
    assert "variant" not in base


def test_generate_manifest_zh_tw_keeps_pinyin_reading_config(tmp_path: Path) -> None:
    """A dialect reads with its parent's script, so zh-tw still gets pinyin."""
    _write_level_file(tmp_path)

    success, zh_manifest_path = generate_manifest(str(tmp_path), "zh")
    assert success
    zh_reading = _load_manifest(zh_manifest_path)["config"]["reading"]

    success, zh_tw_manifest_path = generate_manifest(str(tmp_path), "zh-tw")
    assert success
    assert _load_manifest(zh_tw_manifest_path)["config"]["reading"] == zh_reading


def test_generate_manifest_zh_tw_advertises_no_voices_yet(tmp_path: Path) -> None:
    """zh-tw audio is recorded from zh-tw text; it does not borrow zh's voices."""
    _write_level_file(tmp_path)

    success, manifest_path = generate_manifest(str(tmp_path), "zh-tw")

    assert success
    manifest = _load_manifest(manifest_path)
    assert manifest["config"]["available_voices"] == []
    assert manifest["config"]["default_voice"] is None


def test_slugify_language_name_joins_parenthesized_names() -> None:
    """Display names with punctuation become underscore-joined identifiers.

    A dialect no longer reaches this via its own name -- it takes the base
    language's -- but source-language names still run through it.
    """
    assert _slugify_language_name("Lithuanian") == "lithuanian"
    assert _slugify_language_name("Spanish (Latin America)") == "spanish_latin_america"


def test_generate_manifest_variant_keeps_the_dialect_code(tmp_path: Path) -> None:
    """The variety travels in language_code even though the name does not."""
    _write_level_file(tmp_path)

    success, manifest_path = generate_manifest(str(tmp_path), "es-419")

    assert success
    manifest = _load_manifest(manifest_path)
    assert manifest["language_code"] == "es-419"
    assert manifest["language"] == "spanish"
