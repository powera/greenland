import pytest

from exports.wireword.helpers import (
    extract_conjugation_slot,
    extract_conjugation_tense,
    normalize_translation_text,
)
from langtools.zh.converter import OPENCC_AVAILABLE


def test_extract_conjugation_slot() -> None:
    assert extract_conjugation_slot("1s_present") == "1s"
    assert extract_conjugation_slot("3p_future") == "3p"
    assert extract_conjugation_slot("3s-m_present") == "3s"
    assert extract_conjugation_slot("present") is None


def test_extract_conjugation_tense_normalized_aliases() -> None:
    assert extract_conjugation_tense("1s_present") == "pres"
    assert extract_conjugation_tense("2p_pc") == "past"
    assert extract_conjugation_tense("3s_future") == "fut"


def test_extract_conjugation_tense_flexible_language_specific() -> None:
    assert extract_conjugation_tense("3s_conditional") == "conditional"
    assert extract_conjugation_tense("1p_imparfait") == "imparfait"
    assert extract_conjugation_tense("2s_future_i") == "future_i"
    assert extract_conjugation_tense("present") is None


def test_normalize_translation_text_converts_zh_to_simplified() -> None:
    if not OPENCC_AVAILABLE:
        pytest.skip("opencc not installed")
    assert normalize_translation_text("zh", "雞") == "鸡"


def test_normalize_translation_text_converts_zh_tw_to_traditional() -> None:
    """zh-tw writes Traditional characters, so its rows normalize that way."""
    if not OPENCC_AVAILABLE:
        pytest.skip("opencc not installed")
    assert normalize_translation_text("zh-tw", "鸡") == "雞"


def test_normalize_translation_text_leaves_other_languages_alone() -> None:
    assert normalize_translation_text("lt", "šuo") == "šuo"
    assert normalize_translation_text("es-419", "computadora") == "computadora"
    assert normalize_translation_text("zh-tw", "") == ""
