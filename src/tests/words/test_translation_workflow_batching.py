"""Tests that TranslationWorkflow.generate_translations_for_lemma batches its requests.

The single-lemma path (``voras --populate --guid``) used to send every missing
language in one request, which the prompt builder cut to the first ten -- and
when those ten mixed ancient and modern languages, the schema went over
OpenAI's limit and the request failed every time.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from storage.backend.config import DataSourceConfig
from storage.models.schema import Lemma
from storage.translation_helpers import LANG_CODE_TO_LLM_FIELD
from words.translation_workflow import TranslationWorkflow

LEMMA = Lemma(lemma_text="be", definition_text="x", pos_type="verb", pos_subtype="existence")


class _FakeClient:
    """Answers each language with its own code; fails any batch listed in ``fail``."""

    def __init__(self, fail: Optional[List[str]] = None) -> None:
        self.calls: List[List[str]] = []
        self.fail = fail or []

    def query_translations(self, **kwargs: Any) -> Tuple[Dict[str, Any], bool]:
        languages: List[str] = kwargs["languages"]
        self.calls.append(languages)
        if set(languages) & set(self.fail):
            return {}, False
        return {LANG_CODE_TO_LLM_FIELD[code]: code for code in languages}, True


def _workflow(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> TranslationWorkflow:
    workflow = TranslationWorkflow(config=DataSourceConfig())
    monkeypatch.setattr(workflow, "get_cache_client", lambda: None)
    monkeypatch.setattr(workflow, "get_linguistic_client", lambda: client)
    monkeypatch.setattr(
        "words.translation_workflow.get_reference_translation",
        lambda *args, **kwargs: (None, None),
    )
    return workflow


def test_one_request_per_batch_with_ancient_languages_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient()
    missing = ["vi", "la", "ja", "ko", "sa", "sw", "ro", "pl", "th", "ms", "my", "km", "lo"]

    result = _workflow(monkeypatch, client).generate_translations_for_lemma(None, LEMMA, missing)

    assert client.calls == [
        ["vi", "ja", "ko", "sw", "ro", "pl", "th", "ms", "my", "km"],
        ["lo"],
        ["la", "sa"],
    ]
    assert sorted(result.translations) == sorted(missing)


def test_a_failed_batch_keeps_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient(fail=["la"])

    result = _workflow(monkeypatch, client).generate_translations_for_lemma(
        None, LEMMA, ["vi", "ja", "la"]
    )

    assert sorted(result.translations) == ["ja", "vi"]
    assert result.error is None


def test_every_batch_failing_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient(fail=["vi"])

    result = _workflow(monkeypatch, client).generate_translations_for_lemma(None, LEMMA, ["vi"])

    assert result.translations == {}
    assert result.error == "Failed to generate translations"
