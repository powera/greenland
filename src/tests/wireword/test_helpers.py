from wireword.helpers import extract_conjugation_slot, extract_conjugation_tense


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
