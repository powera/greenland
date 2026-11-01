"""English pronunciation prompts retain sense and tense across workflows."""

import pytest

from words.llm_validators import build_batch_pronunciation_call, build_pronunciation_call
from ipa.normalization import invalid_english_ipa_characters


@pytest.mark.parametrize("existing_ipa", [None, "/riːd/"])
def test_english_prompt_keeps_definition_tense_and_example(existing_ipa: str | None) -> None:
    call = build_pronunciation_call(
        word="read",
        ipa_pronunciation=existing_ipa,
        phonetic_pronunciation=None,
        pos_type="verb",
        definition="to comprehend written text",
        grammatical_form="verb/en_1s_past",
        example_sentence="I read books every day.",
    )
    assert "to comprehend written text" in call.prompt
    assert "verb/en_1s_past" in call.prompt
    assert "I read books every day." in call.prompt
    assert "may use a different tense" in call.prompt
    assert call.context is not None
    assert "General American" in call.context


def test_batch_english_uses_general_american() -> None:
    call = build_batch_pronunciation_call(
        lemma="read",
        definition="to comprehend written text",
        pos_type="verb",
        forms=[{"word": "read", "form": "verb/en_1s_past"}],
    )
    assert call.context is not None
    assert "General American" in call.context
    assert "to comprehend written text" in call.prompt
    assert "verb/en_1s_past" in call.prompt


@pytest.mark.parametrize(
    "ipa", ["/rɛd/", "həv", "/stɹɛŋθs/", "/ˈbʌtn̩/", "/t͡ʃiːz/", "/wɪl riːd/", "/kæt/", "/dɒɡ/"]
)
def test_character_check_accepts_english_ipa_conventions(ipa: str) -> None:
    assert invalid_english_ipa_characters(ipa) == set()


def test_invalid_characters_rejected_in_validation_response() -> None:
    from words.llm_validators import interpret_pronunciation

    result = interpret_pronunciation(
        {"suggested_ipa": "IPA", "confidence": 0.99, "issues": []}, "en"
    )
    assert result["suggested_ipa"] == ""
    assert result["confidence"] == 0.0
    assert "Unsupported IPA characters" in result["issues"][0]


@pytest.mark.parametrize("ipa,success", [("/rɛd/", True), ("IPA", False), ("", False)])
def test_standalone_ipa_generation_checks_characters(ipa: str, success: bool) -> None:
    from unittest.mock import Mock
    from ipa.generation import generate_ipa_pronunciation

    client = Mock()
    client.generate_chat.return_value.structured_data = {"ipa": ipa}
    result = generate_ipa_pronunciation("en", "read", client=client, model="test")
    assert result["success"] is success
