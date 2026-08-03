"""Tests for ruby-annotated HTML generation (Chinese pinyin, Japanese romaji).

The defect under test: a segment with no reading - a Latin name, digits,
punctuation - used to be emitted as a bare text node between <ruby> elements.
A <ruby> is pushed down to make room for its <rt>, but a bare text node is not,
so the unannotated run floated up into the annotation row. Every visible
segment must therefore come back wrapped in a ruby element.
"""

import re

import pytest

from langtools.ja.romaji_helper import PYKAKASI_AVAILABLE, generate_romaji_ruby_html
from langtools.ruby_html import wrap_unannotated_ruby
from langtools.zh.pinyin_helper import (
    JIEBA_AVAILABLE,
    PYPINYIN_AVAILABLE,
    generate_pinyin_ruby_html,
)

# Matches one <ruby>base<rt>annotation</rt></ruby>, capturing base and annotation.
RUBY_RE = re.compile(r"<ruby>(.*?)<rt>(.*?)</rt></ruby>")


def parse_ruby(html: str) -> list[tuple[str, str]]:
    """Return [(base, annotation), ...] for each ruby element in ``html``."""
    return [(m.group(1), m.group(2)) for m in RUBY_RE.finditer(html)]


def assert_fully_wrapped(html: str) -> None:
    """Assert nothing is left outside a ruby element (ignoring whitespace)."""
    leftover = RUBY_RE.sub("", html)
    assert not leftover.strip(), f"unwrapped text outside <ruby>: {leftover!r}"


# --- The shared helper -------------------------------------------------------


def test_wrap_unannotated_adds_empty_rt() -> None:
    """The empty <rt> is what reserves the annotation row."""
    assert wrap_unannotated_ruby("Ben") == "<ruby>Ben<rt></rt></ruby>"


def test_wrap_unannotated_passes_through_whitespace() -> None:
    """Whitespace has no glyph to misalign and must not gain a ruby margin."""
    assert wrap_unannotated_ruby(" ") == " "
    assert wrap_unannotated_ruby("") == ""


@pytest.mark.parametrize("segment", ["Ben", "。", "，", "42", "?"])
def test_wrap_unannotated_wraps_every_visible_segment(segment: str) -> None:
    """Punctuation and digits are wrapped too, for a consistent baseline."""
    base, annotation = parse_ruby(wrap_unannotated_ruby(segment))[0]
    assert base == segment
    assert annotation == ""


# --- Chinese -----------------------------------------------------------------


@pytest.mark.skipif(not PYPINYIN_AVAILABLE, reason="pypinyin not installed")
def test_latin_word_in_chinese_is_wrapped() -> None:
    """The reported bug: "Ben" floated above the line as a bare text node."""
    html = generate_pinyin_ruby_html("他们是Ben通常很害羞。")

    assert "<ruby>Ben<rt></rt></ruby>" in html
    assert_fully_wrapped(html)


@pytest.mark.skipif(not PYPINYIN_AVAILABLE, reason="pypinyin not installed")
def test_chinese_segments_keep_their_pinyin() -> None:
    """Wrapping unannotated runs must not disturb real annotations."""
    annotations = dict(parse_ruby(generate_pinyin_ruby_html("他们是Ben。")))

    assert annotations["他们"] == "tā men"
    assert annotations["Ben"] == ""


@pytest.mark.skipif(not PYPINYIN_AVAILABLE, reason="pypinyin not installed")
def test_chinese_trailing_punctuation_is_wrapped() -> None:
    """Punctuation is wrapped so it shares the baseline like everything else."""
    assert parse_ruby(generate_pinyin_ruby_html("你好。"))[-1] == ("。", "")


@pytest.mark.skipif(not PYPINYIN_AVAILABLE, reason="pypinyin not installed")
def test_chinese_bases_reconstruct_original_text() -> None:
    """No character is dropped or duplicated by the wrapping."""
    text = "他们是Ben通常很害羞。"
    bases = "".join(base for base, _ in parse_ruby(generate_pinyin_ruby_html(text)))

    assert bases == text


@pytest.mark.skipif(
    not PYPINYIN_AVAILABLE or JIEBA_AVAILABLE,
    reason="exercises the char-by-char fallback used when jieba is missing",
)
def test_chinese_char_fallback_wraps_latin() -> None:
    """The no-jieba fallback path wraps unannotated chars the same way."""
    assert_fully_wrapped(generate_pinyin_ruby_html("是B。"))


# --- Japanese ----------------------------------------------------------------


@pytest.mark.skipif(not PYKAKASI_AVAILABLE, reason="pykakasi not installed")
def test_latin_word_in_japanese_is_wrapped() -> None:
    """Same defect, same shape, in the romaji helper."""
    html = generate_romaji_ruby_html("彼はBenです。")

    assert "<ruby>Ben<rt></rt></ruby>" in html
    assert_fully_wrapped(html)


@pytest.mark.skipif(not PYKAKASI_AVAILABLE, reason="pykakasi not installed")
def test_japanese_segments_keep_their_romaji() -> None:
    """Real romaji annotations survive the change."""
    annotations = dict(parse_ruby(generate_romaji_ruby_html("彼はBenです。")))

    assert annotations["です"] == "desu"
    assert annotations["Ben"] == ""


@pytest.mark.skipif(not PYKAKASI_AVAILABLE, reason="pykakasi not installed")
def test_japanese_bases_reconstruct_original_text() -> None:
    """No character is dropped or duplicated by the wrapping."""
    text = "彼はBenです。"
    bases = "".join(base for base, _ in parse_ruby(generate_romaji_ruby_html(text)))

    assert bases == text
