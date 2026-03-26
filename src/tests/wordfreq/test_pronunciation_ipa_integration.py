import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, List

# Pre-populate storage.translation_helpers in sys.modules to avoid the
# circular import that occurs when the full storage package initialises.
# Only needed when the real storage stack hasn't been loaded (CI / lightweight
# test environments).
if "storage.translation_helpers" not in sys.modules:
    _fake_th = ModuleType("storage.translation_helpers")
    _fake_th.LANGUAGE_NAMES = {"en": "English", "fr": "French", "es": "Spanish"}  # type: ignore[attr-defined]
    sys.modules.setdefault("storage.translation_helpers", _fake_th)

import wordfreq.tools.llm_validators as llm_validators


def test_generate_pronunciation_single_prompt(
    monkeypatch: Any,
) -> None:
    """generate_pronunciation uses a single validate_pronunciation call."""

    class FakeClient:
        default_model = "gpt-5.4-mini"

    def fake_validate_pronunciation(**kwargs: Any) -> Dict[str, Any]:
        # Should be called with no pre-generated IPA
        assert kwargs["ipa_pronunciation"] is None
        assert kwargs["word"] == "read"
        return {
            "suggested_ipa": "/rɛd/",
            "suggested_phonetic": "RED",
            "alternative_pronunciations": [],
            "confidence": 0.98,
            "notes": "Context indicates past tense.",
        }

    monkeypatch.setattr(llm_validators, "validate_pronunciation", fake_validate_pronunciation)
    monkeypatch.setattr(llm_validators, "UnifiedLLMClient", FakeClient)

    result = llm_validators.generate_pronunciation(
        word="read",
        pos_type="verb",
        example_sentence="I read the note yesterday.",
        definition="to look at and comprehend text",
        language_code="en",
    )

    assert result["ipa_pronunciation"] == "/rɛd/"
    assert result["phonetic_pronunciation"] == "RED"
    assert result["confidence"] == 0.98


def test_batch_generate_pronunciations_single_prompt(
    monkeypatch: Any,
) -> None:
    """batch_generate_pronunciations uses a single LLM call (no per-form IPA pre-generation)."""

    call_count = 0

    class FakeBatchClient:
        default_model = "gpt-5.4-mini"

        def generate_chat(self, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            return SimpleNamespace(
                structured_data={
                    "verb_fr_present_ipa": "/paʁl/",
                    "verb_fr_present_phonetic": "PARR-LUH",
                    "verb_fr_present_confidence": 0.91,
                    "verb_fr_past_ipa": "/paʁle/",
                    "verb_fr_past_phonetic": "par-LAY",
                    "verb_fr_past_confidence": 0.93,
                }
            )

    monkeypatch.setattr(llm_validators, "UnifiedLLMClient", FakeBatchClient)

    forms: List[Dict[str, str]] = [
        {"form": "verb/fr_present", "word": "parle"},
        {"form": "verb/fr_past", "word": "parlé"},
    ]

    result = llm_validators.batch_generate_pronunciations(
        lemma="parler",
        definition="to speak",
        pos_type="verb",
        forms=forms,
        language_code="fr",
    )

    # Should be exactly 1 LLM call (no per-form IPA pre-generation)
    assert call_count == 1

    assert result["verb/fr_present"]["ipa_pronunciation"] == "/paʁl/"
    assert result["verb/fr_present"]["phonetic_pronunciation"] == "PARR-LUH"
    assert result["verb/fr_past"]["ipa_pronunciation"] == "/paʁle/"
    assert result["verb/fr_past"]["phonetic_pronunciation"] == "par-LAY"
