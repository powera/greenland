"""Word-level pinyin for exports: syllables, written form, overrides, review flags."""

import pytest

from exports.wireword.readings import build_target_reading_fields
from langtools.zh.pinyin_helper import PYPINYIN_AVAILABLE, word_reading

pytestmark = pytest.mark.skipif(not PYPINYIN_AVAILABLE, reason="pypinyin not installed")


def _reading(text: str, override: str | None = None):  # type: ignore[no-untyped-def]
    reading = word_reading(text, override)
    assert reading is not None
    return reading


def test_one_syllable_per_character_and_a_written_word() -> None:
    reading = _reading("银行")
    assert reading.syllables == ("yín", "háng")
    assert reading.pinyin == "yínháng"
    assert reading.spaced == "yín háng"
    assert reading.source == "pypinyin"
    assert not reading.is_ambiguous


def test_apostrophe_before_a_vowel_initial_syllable() -> None:
    assert _reading("西安").pinyin == "xī'ān"
    assert _reading("女儿").pinyin == "nǚ'ér"


def test_attributive_de_is_the_particle_and_stands_apart() -> None:
    reading = _reading("正确的")
    assert reading.syllables == ("zhèng", "què", "de")
    assert reading.pinyin == "zhèngquè de"
    assert not reading.is_ambiguous


def test_phrase_translations_are_written_word_by_word() -> None:
    assert _reading("发回重新审议").pinyin == "fāhuí chóngxīn shěnyì"


def test_non_han_runs_are_kept_and_spaced() -> None:
    reading = _reading("T恤")
    assert reading.syllables == ("T", "xù")
    assert reading.pinyin == "T xù"


def test_traditional_characters_are_read() -> None:
    assert _reading("長城").syllables == ("cháng", "chéng")


def test_bare_polyphone_is_flagged_for_review() -> None:
    # pypinyin reads a bare 长 as zhǎng; for "long" that is wrong.
    reading = _reading("长")
    assert reading.is_ambiguous
    assert reading.ambiguous_positions == (0,)


def test_a_phrase_settles_a_polyphone() -> None:
    assert not _reading("长城").is_ambiguous
    assert not _reading("银行").is_ambiguous


def test_override_wins_and_clears_the_flag() -> None:
    reading = _reading("长", "cháng")
    assert reading.syllables == ("cháng",)
    assert reading.source == "override"
    assert not reading.is_ambiguous


def test_misaligned_override_is_ignored() -> None:
    reading = _reading("长", "cháng dà")
    assert reading.source == "pypinyin"


def test_wireword_target_pinyin_takes_the_override_for_the_base_only() -> None:
    assert build_target_reading_fields("zh", "教") == {"target_pinyin": "jiào"}
    assert build_target_reading_fields("zh", "教", {"pinyin": "jiāo"}) == {"target_pinyin": "jiāo"}
    # Spaced syllables, unchanged from the earlier export format.
    assert build_target_reading_fields("zh", "银行", {}) == {"target_pinyin": "yín háng"}
