from exports.wireword.readings import (
    build_target_reading_fields,
    build_target_reading_list_fields,
    build_translation_reading_fields,
    get_manifest_reading_config,
)


def test_manifest_reading_config_for_chinese() -> None:
    config = get_manifest_reading_config("zh")

    assert config == {
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


def test_manifest_reading_config_for_japanese() -> None:
    config = get_manifest_reading_config("ja")

    assert config == {
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


def test_build_target_reading_fields_for_japanese() -> None:
    reading_fields = build_target_reading_fields("ja", "東京")

    assert reading_fields["target_romaji"] == "toukyou"
    assert reading_fields["target_hiragana"] == "とうきょう"


def test_build_target_reading_list_fields_for_japanese() -> None:
    reading_fields = build_target_reading_list_fields(
        "ja",
        ["東京", "日本語"],
        "target_synonyms",
    )

    assert reading_fields["target_synonyms_romaji"] == ["toukyou", "nihongo"]
    assert reading_fields["target_synonyms_hiragana"] == ["とうきょう", "にほんご"]


def test_build_translation_reading_fields_for_chinese() -> None:
    reading_fields = build_translation_reading_fields("zh", "你好")

    assert reading_fields == {"pinyin": "nǐ hǎo"}


def test_manifest_reading_config_for_zh_tw_matches_chinese() -> None:
    """A dialect reads with its parent's script; zh-tw is annotated with pinyin.

    Keyed on the raw code, zh-tw fell through to no reading config at all and
    the export shipped Traditional characters with no pronunciation.
    """
    assert get_manifest_reading_config("zh-tw") == get_manifest_reading_config("zh")


def test_build_target_reading_fields_for_zh_tw() -> None:
    reading_fields = build_target_reading_fields("zh-tw", "電腦")

    assert reading_fields == {"target_pinyin": "diàn nǎo"}


def test_build_translation_reading_fields_for_zh_tw() -> None:
    reading_fields = build_translation_reading_fields("zh-tw", "你好")

    assert reading_fields == {"pinyin": "nǐ hǎo"}
