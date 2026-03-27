from agents.bebras.integrity import IntegrityChecker


def test_phonetic_syllables_not_flagged_as_many_ascii_words() -> None:
    checker = IntegrityChecker()

    is_suspicious, reasons = checker._is_suspicious_pronunciation_text(
        pronunciation_text="SIH-luhnd-ruh-KAYL",
        source_text="cylindrical",
        field_name="phonetic",
    )

    assert not is_suspicious
    assert "contains_many_ascii_words" not in reasons


def test_prompt_leak_text_still_flagged_for_ipa() -> None:
    checker = IntegrityChecker()

    is_suspicious, reasons = checker._is_suspicious_pronunciation_text(
        pronunciation_text=(
            "I have corrected the IPA representation to match the requested schema, "
            "which requires simplified phonetic representation."
        ),
        source_text="show",
        field_name="ipa",
    )

    assert is_suspicious
    assert "contains_many_ascii_words" in reasons
