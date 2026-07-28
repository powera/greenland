#!/usr/bin/python3
"""Tests for output-token limits and truncation detection.

The bug these cover: a response cut off at the token limit used to be reported
as a *successful* call. The OpenAI client returned ``{"error": ...}`` as its
structured data, and callers merge structured data into their result dict, so
the truncated fragment arrived downstream looking like an answer. A 45-word
sentence would be stored with half its words missing.
"""

import os
import sys
import unittest
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from clients import lib
from clients.openai.client import OpenAIClient


class LimitFromEstimateTestCase(unittest.TestCase):
    """The estimate -> limit policy, tuned in one place for every caller."""

    def test_applies_headroom_above_the_floor(self) -> None:
        # 1.35x + 100, so a 1000-token estimate asks for 1450.
        self.assertEqual(lib.limit_from_estimate(1000), 1450)

    def test_small_estimates_get_the_floor(self) -> None:
        """A tiny estimate should not produce an absurdly tight limit."""
        self.assertEqual(lib.limit_from_estimate(0), lib.MIN_ESTIMATED_LIMIT_TOKENS)
        self.assertEqual(lib.limit_from_estimate(10), lib.MIN_ESTIMATED_LIMIT_TOKENS)

    def test_is_monotonic(self) -> None:
        limits = [lib.limit_from_estimate(estimate) for estimate in (500, 1000, 2000, 4000)]
        self.assertEqual(limits, sorted(limits))

    def test_long_sentence_estimate_exceeds_the_old_hardcoded_cap(self) -> None:
        """The regression that motivated all of this.

        A 45-word sentence decomposed into several languages needs more than the
        4096 tokens that used to be hardcoded; if this stops holding, long
        sentences are silently back to being truncated.
        """
        self.assertGreater(lib.limit_from_estimate(3600), 4096)


class ResolveOutputTokensTestCase(unittest.TestCase):
    """Backwards compatibility is the point: no caller should shift silently."""

    def test_none_reproduces_the_backend_default(self) -> None:
        self.assertEqual(
            lib.resolve_output_tokens(
                "gpt-5.4-mini", brief=False, requested=None, backend_default=4096
            ),
            4096,
        )

    def test_none_with_brief_reproduces_the_brief_default(self) -> None:
        self.assertEqual(
            lib.resolve_output_tokens(
                "gpt-5.4-mini", brief=True, requested=None, backend_default=4096
            ),
            512,
        )
        # Gemini's brief default differs and must be preserved.
        self.assertEqual(
            lib.resolve_output_tokens(
                "gemini-2.5-flash",
                brief=True,
                requested=None,
                backend_default=1536,
                brief_default=256,
            ),
            256,
        )

    def test_explicit_request_wins_over_brief(self) -> None:
        """max_tokens is the more specific knob, so it overrides the coarse one."""
        self.assertEqual(
            lib.resolve_output_tokens(
                "gpt-5.4-mini", brief=True, requested=8000, backend_default=4096
            ),
            8000,
        )

    def test_request_is_clamped_to_the_model_ceiling(self) -> None:
        resolved = lib.resolve_output_tokens(
            "gemini-2.5-flash", brief=False, requested=999_999, backend_default=1536
        )
        self.assertEqual(resolved, lib.ceiling_for_model("gemini-2.5-flash"))

    def test_unknown_model_falls_back_to_the_default_ceiling(self) -> None:
        self.assertEqual(lib.ceiling_for_model("some-new-model"), lib.DEFAULT_OUTPUT_CEILING)

    def test_default_pipeline_model_has_a_real_ceiling(self) -> None:
        """Catches a model rename quietly dropping the pipeline to the fallback."""
        from sentences.translate_and_decompose import DEFAULT_MODEL

        self.assertGreater(lib.ceiling_for_model(DEFAULT_MODEL), lib.DEFAULT_OUTPUT_CEILING)


def _openai_envelope(
    *,
    text: str,
    status: str = "completed",
    output_tokens: int = 10,
    incomplete_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """A minimal OpenAI Responses envelope in the shape the client parses."""
    envelope: Dict[str, Any] = {
        "status": status,
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {"input_tokens": 5, "output_tokens": output_tokens},
    }
    if incomplete_reason is not None:
        envelope["incomplete_details"] = {"reason": incomplete_reason}
    return envelope


class OpenAITruncationTestCase(unittest.TestCase):
    """Truncation must surface as a raised error, never as response data."""

    def setUp(self) -> None:
        self.client = OpenAIClient()
        self.client.api_key = "test-key-not-used"
        self.schema = {"type": "object", "properties": {"words": {"type": "array"}}}

    def _patch_response(self, envelope: Dict[str, Any]) -> None:
        self.client._create_response = lambda **kwargs: (envelope, 1.0)  # type: ignore[method-assign]

    def test_spending_the_whole_budget_is_truncation(self) -> None:
        """The signal that needs no cooperation from the provider.

        A response that ended on its own terms stops short of the cap, so
        landing on it means the cap did the stopping -- true even when the
        status flags say nothing.
        """
        self._patch_response(
            _openai_envelope(text='{"words": [{"a": 1}', status="completed", output_tokens=512)
        )
        with self.assertRaises(lib.TruncatedResponseError) as caught:
            self.client.generate_chat(
                prompt="decompose this",
                model="gpt-5.4-mini",
                json_schema=self.schema,
                max_tokens=512,
            )
        self.assertIn("512", str(caught.exception))

    def test_incomplete_status_is_truncation(self) -> None:
        self._patch_response(
            _openai_envelope(
                text='{"words": [',
                status="incomplete",
                output_tokens=100,
                incomplete_reason="max_output_tokens",
            )
        )
        with self.assertRaises(lib.TruncatedResponseError):
            self.client.generate_chat(
                prompt="decompose this",
                model="gpt-5.4-mini",
                json_schema=self.schema,
                max_tokens=4096,
            )

    def test_incomplete_with_no_message_content_is_truncation(self) -> None:
        """Reasoning models can return an incomplete envelope with no message."""
        envelope: Dict[str, Any] = {
            "status": "incomplete",
            "output": [{"type": "reasoning", "summary": []}],
            "usage": {"input_tokens": 5, "output_tokens": 100},
        }
        self._patch_response(envelope)
        with self.assertRaises(lib.TruncatedResponseError):
            self.client.generate_chat(
                prompt="decompose this",
                model="gpt-5.4-mini",
                json_schema=self.schema,
                max_tokens=4096,
            )

    def test_unparseable_json_raises_instead_of_returning_an_error_dict(self) -> None:
        """The specific regression: an error payload used to read as success.

        structured_data is merged into the caller's result, so returning
        {"error": ...} produced a "successful" call with no words in it.
        """
        self._patch_response(
            _openai_envelope(text="this is not json", status="completed", output_tokens=10)
        )
        with self.assertRaises(ValueError) as caught:
            self.client.generate_chat(
                prompt="decompose this",
                model="gpt-5.4-mini",
                json_schema=self.schema,
                max_tokens=4096,
            )
        self.assertNotIsInstance(caught.exception, lib.TruncatedResponseError)

    def test_complete_response_is_returned_normally(self) -> None:
        """The common path stays untouched."""
        self._patch_response(
            _openai_envelope(text='{"words": ["ok"]}', status="completed", output_tokens=42)
        )
        response = self.client.generate_chat(
            prompt="decompose this", model="gpt-5.4-mini", json_schema=self.schema, max_tokens=4096
        )
        self.assertEqual(response.structured_data, {"words": ["ok"]})


if __name__ == "__main__":
    unittest.main()
