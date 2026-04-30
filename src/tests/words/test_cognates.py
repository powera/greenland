from dataclasses import dataclass

from words.cognates import detect_cognate, detect_cognate_for_lemmas
from langtools.ja.romaji_helper import PYKAKASI_AVAILABLE
from langtools.zh.pinyin_helper import PYPINYIN_AVAILABLE


@dataclass
class _LemmaStub:
    lemma_text: str


def test_detect_cognate_lt_en_positive() -> None:
    result = detect_cognate("demokratija", "democracy", "lt", "en")
    assert result.is_cognate is True


def test_detect_cognate_es_fr_positive() -> None:
    result = detect_cognate("nación", "nation", "es", "fr")
    assert result.is_cognate is True


def test_detect_cognate_pt_en_positive() -> None:
    result = detect_cognate("filosofia", "philosophy", "pt", "en")
    assert result.is_cognate is True


def test_detect_cognate_it_en_positive() -> None:
    result = detect_cognate("democrazia", "democracy", "it", "en")
    assert result.is_cognate is True


def test_detect_cognate_de_en_positive() -> None:
    result = detect_cognate("telefon", "telephone", "de", "en")
    assert result.is_cognate is True


def test_detect_cognate_uk_en_positive() -> None:
    result = detect_cognate("демократія", "democracy", "uk", "en")
    assert result.is_cognate is True


def test_detect_cognate_zh_en_romanization() -> None:
    result = detect_cognate("中国", "zhongguo", "zh", "en")
    if PYPINYIN_AVAILABLE:
        assert result.is_cognate is True
    else:
        assert result.is_cognate is False


def test_detect_cognate_ja_en_romanization() -> None:
    result = detect_cognate("カタカナ", "katakana", "ja", "en")
    if PYKAKASI_AVAILABLE:
        assert result.is_cognate is True
    else:
        assert result.is_cognate is False


def test_detect_cognate_negative_pair() -> None:
    result = detect_cognate("vanduo", "table", "lt", "en")
    assert result.is_cognate is False


def test_detect_cognate_vanduo_water_not_cognate_in_module_definition() -> None:
    result = detect_cognate("vanduo", "water", "lt", "en")
    assert result.is_cognate is False


def test_detect_cognate_unknown_languages_fallback() -> None:
    result = detect_cognate("kitabu", "libro", "sw", "es")
    assert isinstance(result.score, float)


def test_detect_cognate_reason_codes_include_threshold_marker() -> None:
    result = detect_cognate("demokratija", "democracy", "lt", "en")
    assert "above_threshold" in result.reasons


def test_detect_cognate_for_lemmas_uses_lemma_text() -> None:
    left = _LemmaStub(lemma_text="demokratija")
    right = _LemmaStub(lemma_text="democracy")
    result = detect_cognate_for_lemmas(left, right, "lt", "en")
    assert result.is_cognate is True
