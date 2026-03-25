from types import SimpleNamespace
from typing import Any, Dict, List

import wordfreq.tools.llm_validators as llm_validators


def test_generate_pronunciation_uses_shared_ipa_for_ambiguous_english_word(
    monkeypatch: Any,
) -> None:
    class FakeClient:
        default_model = "gpt-5.4-mini"

    def fake_generate_ipa_pronunciation(**kwargs: Any) -> Dict[str, Any]:
        assert kwargs["language_code"] == "en"
        assert kwargs["word"] == "read"
        assert "yesterday" in kwargs["sentence"]
        return {"success": True, "ipa": "/rɛd/"}

    def fake_validate_pronunciation(**kwargs: Any) -> Dict[str, Any]:
        assert kwargs["ipa_pronunciation"] == "/rɛd/"
        return {
            "suggested_ipa": kwargs["ipa_pronunciation"],
            "suggested_phonetic": "RED",
            "alternative_pronunciations": [],
            "confidence": 0.98,
            "notes": "Context indicates past tense.",
        }

    monkeypatch.setattr(
        llm_validators, "generate_ipa_pronunciation", fake_generate_ipa_pronunciation
    )
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


def test_shared_ipa_format_consistent_for_non_english_generate_and_batch(
    monkeypatch: Any,
) -> None:
    def fake_generate_ipa_pronunciation(**kwargs: Any) -> Dict[str, Any]:
        language_code = kwargs["language_code"]
        word = kwargs["word"]
        return {"success": True, "ipa": f"/{language_code}:{word}/"}

    class FakeBatchClient:
        default_model = "gpt-5.4-mini"

        def generate_chat(self, **kwargs: Any) -> Any:
            _ = kwargs
            return SimpleNamespace(
                structured_data={
                    "verb_fr_present_ipa": "INVALID_IPA_NO_SLASHES",
                    "verb_fr_present_phonetic": "PARR-LUH",
                    "verb_fr_present_confidence": 0.91,
                    "verb_es_present_ipa": "ALSO_INVALID",
                    "verb_es_present_phonetic": "AH-BLO",
                    "verb_es_present_confidence": 0.93,
                }
            )

    def fake_validate_pronunciation(**kwargs: Any) -> Dict[str, Any]:
        ipa = kwargs["ipa_pronunciation"] or ""
        return {
            "suggested_ipa": ipa,
            "suggested_phonetic": "PHONETIC",
            "alternative_pronunciations": [],
            "confidence": 0.9,
            "notes": "",
        }

    monkeypatch.setattr(
        llm_validators, "generate_ipa_pronunciation", fake_generate_ipa_pronunciation
    )
    monkeypatch.setattr(llm_validators, "validate_pronunciation", fake_validate_pronunciation)
    monkeypatch.setattr(llm_validators, "UnifiedLLMClient", FakeBatchClient)

    single_fr = llm_validators.generate_pronunciation(
        word="parle",
        pos_type="verb",
        definition="to speak",
        language_code="fr",
        grammatical_form="verb/fr_present",
    )
    single_es = llm_validators.generate_pronunciation(
        word="hablo",
        pos_type="verb",
        definition="to speak",
        language_code="es",
        grammatical_form="verb/es_present",
    )

    fr_forms: List[Dict[str, str]] = [{"form": "verb/fr_present", "word": "parle"}]
    es_forms: List[Dict[str, str]] = [{"form": "verb/es_present", "word": "hablo"}]

    fr_batch = llm_validators.batch_generate_pronunciations(
        lemma="speak",
        definition="to produce spoken language",
        pos_type="verb",
        forms=fr_forms,
        language_code="fr",
    )
    es_batch = llm_validators.batch_generate_pronunciations(
        lemma="speak",
        definition="to produce spoken language",
        pos_type="verb",
        forms=es_forms,
        language_code="es",
    )

    assert single_fr["ipa_pronunciation"] == "/fr:parle/"
    assert single_es["ipa_pronunciation"] == "/es:hablo/"
    assert fr_batch["verb/fr_present"]["ipa_pronunciation"] == "/fr:parle/"
    assert es_batch["verb/es_present"]["ipa_pronunciation"] == "/es:hablo/"
    assert fr_batch["verb/fr_present"]["phonetic_pronunciation"] == "PARR-LUH"
    assert es_batch["verb/es_present"]["phonetic_pronunciation"] == "AH-BLO"
