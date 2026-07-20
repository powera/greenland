"""Tests for Chinese pinyin sort keys used in dictionary ordering."""

import pytest

from langtools.zh.pinyin_helper import PYPINYIN_AVAILABLE, generate_pinyin_sort_key
from storage.translation_helpers import compute_sort_key

pytestmark = pytest.mark.skipif(not PYPINYIN_AVAILABLE, reason="pypinyin not installed")


def test_sort_key_uses_tone_digits() -> None:
    """Tones are trailing digits, not diacritics, so letters stay adjacent."""
    assert generate_pinyin_sort_key("点") == "dian3"
    assert generate_pinyin_sort_key("你好") == "ni3 hao3"


def test_sort_keys_are_ascii() -> None:
    """Tone-marked vowels would break binary collation; keys must be ASCII."""
    for word in ["点", "掉", "对", "大", "动", "女", "绿", "散步"]:
        key = generate_pinyin_sort_key(word)
        assert key is not None
        assert key.isascii(), f"non-ASCII sort key for {word!r}: {key!r}"


def test_alphabetical_before_tonal() -> None:
    """Spelling drives ordering; tone is only a tiebreaker among homophones."""
    words = ["点", "掉", "对", "大", "的", "动", "但", "当", "都"]
    ordered = sorted(words, key=lambda w: generate_pinyin_sort_key(w) or "")
    assert ordered == ["大", "但", "当", "的", "点", "掉", "动", "都", "对"]


def test_tone_order_within_homophones() -> None:
    """Same syllable sorts by tone 1-4, with neutral tone (5) last."""
    # 三 sān, 伞 sǎn, 散 sàn
    words = ["散", "伞", "三"]
    ordered = sorted(words, key=lambda w: generate_pinyin_sort_key(w) or "")
    assert ordered == ["三", "伞", "散"]


def test_neutral_tone_written_as_five() -> None:
    """Every syllable ends in a digit so neutral tone can't sort before tone 1."""
    assert generate_pinyin_sort_key("的") == "de5"


def test_umlaut_u_becomes_v() -> None:
    """ü is written 'v', sorting just after 'u' as dictionaries expect."""
    assert generate_pinyin_sort_key("女") == "nv3"
    assert generate_pinyin_sort_key("绿") == "lv4"


def test_shorter_word_sorts_before_compound() -> None:
    """A syllable sorts before compounds starting with it (space < digits)."""
    words = ["大学", "大"]
    ordered = sorted(words, key=lambda w: generate_pinyin_sort_key(w) or "")
    assert ordered == ["大", "大学"]


def test_non_chinese_returns_none() -> None:
    assert generate_pinyin_sort_key("hello") is None
    assert generate_pinyin_sort_key("") is None


def test_compute_sort_key_uses_tone_digits() -> None:
    """The storage-layer entrypoint must produce the same tone-digit keys."""
    assert compute_sort_key("zh", "点") == "dian3"


def test_compute_sort_key_returns_none_not_literal_none() -> None:
    """A failed transliteration must be None, never the string 'None'."""
    assert compute_sort_key("zh", "hello") is None
