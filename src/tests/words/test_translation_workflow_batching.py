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
    assert result.failed_languages == ["la"]


def test_every_batch_failing_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient(fail=["vi"])

    result = _workflow(monkeypatch, client).generate_translations_for_lemma(None, LEMMA, ["vi"])

    assert result.translations == {}
    assert result.error == "Failed to generate translations"


class _AncientStatusClient(_FakeClient):
    """Answers Latin in the object shape the ancient-group schema asks for."""

    def query_translations(self, **kwargs: Any) -> Tuple[Dict[str, Any], bool]:
        self.calls.append(kwargs["languages"])
        return {
            LANG_CODE_TO_LLM_FIELD["la"]: {
                "translation": "aeroplanum",
                "confidence": 0.95,
                "translation_status": "late_construction",
                "translation_status_note": "Neo-Latin coinage",
            }
        }, True


def test_ancient_status_is_saved(monkeypatch: pytest.MonkeyPatch) -> None:
    """--guid runs store translation_status the way --level runs do."""
    workflow = _workflow(monkeypatch, _AncientStatusClient())
    generated = workflow.generate_translations_for_lemma(None, LEMMA, ["la"])

    expected = {
        "la": {
            "translation_status": "late_construction",
            "translation_status_note": "Neo-Latin coinage",
        }
    }
    assert generated.metadata == expected

    stored_metadata: List[Dict[str, Any]] = []

    def _capture_store(
        session: Any, lemma: Lemma, texts: Any, metadata: Any, *args: Any, **kwargs: Any
    ) -> None:
        stored_metadata.append(metadata)

    class _Session:
        def commit(self) -> None:
            pass

    monkeypatch.setattr("words.translation_workflow.store_translations_by_language", _capture_store)
    workflow.save_lemma_translations(_Session(), LEMMA, generated, ["la"])

    assert stored_metadata == [expected]


class _RatedClient(_FakeClient):
    """Answers each language with ``new-<code>`` at the confidence in ``ratings``."""

    def __init__(self, ratings: Dict[str, float], fail: Optional[List[str]] = None) -> None:
        super().__init__(fail=fail)
        self.ratings = ratings

    def query_translations(self, **kwargs: Any) -> Tuple[Dict[str, Any], bool]:
        languages: List[str] = kwargs["languages"]
        self.calls.append(languages)
        if set(languages) & set(self.fail):
            return {}, False
        return {
            LANG_CODE_TO_LLM_FIELD[code]: {
                "translation": f"new-{code}",
                "confidence": self.ratings.get(code, 0.95),
            }
            for code in languages
        }, True


def test_regenerate_overwrites_only_usable_answers_for_the_chosen_languages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing is cleared up front: a failed or uncertain language keeps its text."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from storage.crud.lemma import add_lemma
    from storage.models.schema import Base
    from storage.translation_helpers import get_translation, set_translation

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        lemma = add_lemma(
            session,
            lemma_text="dog",
            definition_text="a domesticated carnivore",
            pos_type="noun",
            auto_generate_guid=False,
        )
        for code in ["fr", "de", "it", "la"]:
            set_translation(session, lemma, code, f"old-{code}")
        session.commit()

        client = _RatedClient({"de": 0.2}, fail=["la"])
        workflow = _workflow(monkeypatch, client)
        generated, outcome = workflow.regenerate_lemma_translations(
            session, lemma, ["fr", "de", "la"]
        )

        assert generated.failed_languages == ["la"]
        assert outcome.written == ["fr"]
        assert outcome.uncertain == ["de"]
        assert get_translation(session, lemma, "fr") == "new-fr"
        assert get_translation(session, lemma, "de") == "old-de"  # below the floor
        assert get_translation(session, lemma, "la") == "old-la"  # batch failed
        assert get_translation(session, lemma, "it") == "old-it"  # not requested
