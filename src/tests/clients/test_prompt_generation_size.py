#!/usr/bin/python3
"""Guardrails for cross-provider prompt construction size."""

import os
import statistics
import sys
import unittest
from typing import Any, Dict, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from clients.anthropic.client import AnthropicClient
from clients.gemini_client import GeminiClient
from clients.lmstudio_client import LMStudioClient
from clients.openai.client import OpenAIClient


class PromptGenerationSizeTestCase(unittest.TestCase):
    """Ensure translation prompts are similarly sized across providers."""

    MAX_DEVIATION = 0.20

    TRANSLATION_QUERIES = [
        {
            "name": "single_word_translation",
            "context": "You are a translation assistant. Return only structured translation output.",
            "prompt": "Translate the English lemma 'flower' into Lithuanian, Spanish, and Japanese.",
        },
        {
            "name": "sentence_translation",
            "context": "You are a translation assistant. Preserve tone and register in all translations.",
            "prompt": "Translate this sentence from English to French and German: 'I had been waiting for hours before the train finally arrived.'",
        },
        {
            "name": "disambiguation_translation",
            "context": "You are a translation assistant. Pick the sense that fits the supplied definition.",
            "prompt": "Translate the word 'bank' meaning 'the side of a river' to Lithuanian, Polish, and Italian.",
        },
    ]

    RESPONSE_SCHEMA = {
        "name": "translation_result",
        "description": "Structured translation output",
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "language": {"type": "string"},
                        "translation": {"type": "string"},
                    },
                    "required": ["language", "translation"],
                },
            },
            "notes": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["translations", "confidence"],
    }

    def _capture_openai(self, prompt: str, context: str) -> Dict[str, Any]:
        captured: Dict[str, Any] = {}

        client = OpenAIClient.__new__(OpenAIClient)
        client.timeout = 50
        client.debug = False
        client.api_key = "test-key"
        client.headers = {"Authorization": "Bearer test-key", "Content-Type": "application/json"}
        client.encoder = None

        def _fake_response(**kwargs: Any) -> Tuple[Dict[str, Any], float]:
            captured.update(kwargs)
            return (
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "{}"}],
                        }
                    ],
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
                0.0,
            )

        client._create_response = _fake_response  # type: ignore[method-assign]
        client.generate_chat(
            prompt=prompt,
            model="gpt-5-mini",
            json_schema=self.RESPONSE_SCHEMA,
            context=context,
        )
        return captured

    def _capture_anthropic(self, prompt: str, context: str) -> Dict[str, Any]:
        captured: Dict[str, Any] = {}
        client = AnthropicClient(api_key="test-key", debug=False)

        def _fake_response(**kwargs: Any) -> Tuple[Dict[str, Any], float]:
            captured.update(kwargs)
            return (
                {
                    "content": [{"type": "tool_use", "input": {}}],
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
                0.0,
            )

        client._create_message = _fake_response  # type: ignore[method-assign]
        client.generate_chat(
            prompt=prompt,
            model="claude-3-5-haiku-20241022",
            json_schema=self.RESPONSE_SCHEMA,
            context=context,
        )
        return captured

    def _capture_gemini(self, prompt: str, context: str) -> Dict[str, Any]:
        captured: Dict[str, Any] = {}
        client = GeminiClient.__new__(GeminiClient)
        client.timeout = 50
        client.debug = False
        client.api_key = "test-key"
        client.headers = {"Content-Type": "application/json"}
        client.encoder = None

        def _fake_response(model: str, **kwargs: Any) -> Tuple[Dict[str, Any], float]:
            captured["model"] = model
            captured.update(kwargs)
            return (
                {
                    "candidates": [{"content": {"parts": [{"text": "[{}]"}]}}],
                    "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0},
                },
                0.0,
            )

        client._create_completion = _fake_response  # type: ignore[method-assign]
        client.generate_chat(
            prompt=prompt,
            model="gemini-2.5-flash",
            json_schema=self.RESPONSE_SCHEMA,
            context=context,
        )
        return captured

    def _capture_lmstudio(self, prompt: str, context: str) -> Dict[str, Any]:
        captured: Dict[str, Any] = {}
        client = LMStudioClient(debug=False)

        def _fake_response(endpoint: str, data: Dict[str, Any]) -> Any:
            captured["endpoint"] = endpoint
            captured.update(data)

            class _Elapsed:
                @staticmethod
                def total_seconds() -> float:
                    return 0.0

            class _Response:
                elapsed = _Elapsed()

                @staticmethod
                def json() -> Dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": "{}"}}],
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                    }

            return _Response()

        client._make_request = _fake_response  # type: ignore[method-assign]
        client.generate_chat(
            prompt=prompt,
            model="mistral",
            json_schema=self.RESPONSE_SCHEMA,
            context=context,
        )
        return captured

    @staticmethod
    def _extract_prompt_text_length(provider: str, payload: Dict[str, Any]) -> int:
        if provider == "openai":
            instructions = payload.get("instructions", "")
            prompt = payload.get("input", "")
            return len(instructions) + len(prompt)

        if provider == "anthropic":
            total = 0
            for block in payload.get("system", []):
                if isinstance(block, dict):
                    total += len(block.get("text", ""))
            for message in payload.get("messages", []):
                total += len(message.get("content", ""))
            return total

        if provider == "gemini":
            total = 0
            for part in payload.get("system_instruction", {}).get("parts", []):
                total += len(part.get("text", ""))
            for content in payload.get("contents", []):
                for part in content.get("parts", []):
                    total += len(part.get("text", ""))
            return total

        if provider == "lmstudio":
            return sum(len(message.get("content", "")) for message in payload.get("messages", []))

        raise ValueError(f"Unknown provider: {provider}")

    def test_translation_prompt_sizes_within_20_percent(self) -> None:
        for query in self.TRANSLATION_QUERIES:
            with self.subTest(query=query["name"]):
                openai_payload = self._capture_openai(query["prompt"], query["context"])
                anthropic_payload = self._capture_anthropic(query["prompt"], query["context"])
                gemini_payload = self._capture_gemini(query["prompt"], query["context"])
                lmstudio_payload = self._capture_lmstudio(query["prompt"], query["context"])

                prompt_sizes = {
                    "openai": self._extract_prompt_text_length("openai", openai_payload),
                    "anthropic": self._extract_prompt_text_length("anthropic", anthropic_payload),
                    "gemini": self._extract_prompt_text_length("gemini", gemini_payload),
                    "lmstudio": self._extract_prompt_text_length("lmstudio", lmstudio_payload),
                }

                baseline = statistics.median(prompt_sizes.values())
                self.assertGreater(baseline, 0)

                violations = []
                for provider, size in prompt_sizes.items():
                    deviation = abs(size - baseline) / baseline
                    if deviation > self.MAX_DEVIATION:
                        violations.append(
                            f"{provider} size={size} deviates {deviation:.1%} from median {baseline}"
                        )

                self.assertEqual(
                    violations,
                    [],
                    f"Prompt size mismatch for {query['name']}: {prompt_sizes}. "
                    f"Threshold is {self.MAX_DEVIATION:.0%}. Violations: {violations}",
                )


if __name__ == "__main__":
    unittest.main()
