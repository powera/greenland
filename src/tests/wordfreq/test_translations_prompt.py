"""Tests for the word-translation prompt context and structured response schema.

The context is assembled per call: the ``translation_status`` taxonomy is added
only when a language scored on it (the ancient group) is among the targets, and
the reference translation is named dynamically rather than assumed to be
Lithuanian.  These tests pin both across several language sets.
"""

from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest

from clients.types import Schema
from wordfreq.translation.translations import query_translations


class _CapturingClient:
    def __init__(self) -> None:
        self.context: Optional[str] = None
        self.prompt: Optional[str] = None
        self.schema: Optional[Schema] = None

    def generate_chat(self, **kwargs: Any) -> SimpleNamespace:
        self.context = kwargs.get("context")
        self.prompt = kwargs.get("prompt")
        self.schema = kwargs.get("json_schema")
        return SimpleNamespace(structured_data={}, usage=None)


def _run(
    monkeypatch: pytest.MonkeyPatch,
    languages: List[str],
    reference: Tuple[str, str] = ("lt", "šuo"),
) -> _CapturingClient:
    """Issue one query_translations call and return the capturing client."""
    monkeypatch.setattr(
        "wordfreq.translation.translations.linguistic_db.log_query",
        lambda *args, **kwargs: None,
    )
    client = _CapturingClient()
    query_translations(
        client,
        english_word="dog",
        reference_translation=reference,
        definition="a domesticated carnivorous mammal",
        pos_type="noun",
        get_session_func=lambda: object(),
        languages=languages,
        model="test-model",
    )
    assert client.context is not None
    return client


def _language_properties(client: _CapturingClient, field: str) -> Dict[str, Any]:
    assert client.schema is not None
    return client.schema.properties[field].properties


# --- The context never hardcodes a reference language ----------------------


def test_context_does_not_name_lithuanian(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reference language is whichever one the lemma happens to have.

    The context used to assert the word "already has its ... Lithuanian
    translation", which contradicted the prompt whenever the reference was
    another language, and described data that was absent entirely when the
    reference was English.
    """
    client = _run(monkeypatch, ["es", "de"], reference=("zh", "狗"))
    assert "Lithuanian" not in client.context  # type: ignore[operator]
    assert "reference" in client.context  # type: ignore[operator]

    # The prompt, not the context, names the actual reference language.
    assert client.prompt is not None
    assert 'Chinese: "狗"' in client.prompt


def test_english_reference_leaves_no_dangling_reference_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With an English reference there is no second translation to show."""
    client = _run(monkeypatch, ["es"], reference=("en", "dog"))
    assert client.prompt is not None
    assert "(lemma form)\nDefinition:" in client.prompt
    assert "Lithuanian" not in client.context  # type: ignore[operator]


# --- The status taxonomy appears only for the ancient group ----------------


@pytest.mark.parametrize(
    "languages",
    [
        ["es-419", "zh-tw", "pt-br", "bs", "de", "it", "pt"],  # today's backfill
        ["es", "fr"],
        ["zh"],
    ],
)
def test_modern_languages_omit_status(
    monkeypatch: pytest.MonkeyPatch, languages: List[str]
) -> None:
    """No taxonomy in the context, and no status fields in the schema.

    A living language's status is "conventional" for nearly every word and is
    dropped before storage by translation_status_is_informative, so asking for
    it spends context on a classification that cannot inform anything.
    """
    client = _run(monkeypatch, languages)

    assert "historical/native fit" not in client.context  # type: ignore[operator]
    assert "modern_reimagining" not in client.context  # type: ignore[operator]
    assert "status note" not in client.context  # type: ignore[operator]
    # The placeholders must be substituted, never left in the rendered text.
    assert "{status_requirements}" not in client.context  # type: ignore[operator]
    assert "{status_note_instruction}" not in client.context  # type: ignore[operator]

    for lang_code in languages:
        from wordfreq.translation.constants import AVAILABLE_TRANSLATION_LANGUAGES_BY_CODE

        field = AVAILABLE_TRANSLATION_LANGUAGES_BY_CODE[lang_code]["field"]
        properties = _language_properties(client, field)
        assert "translation" in properties
        assert "translation_status" not in properties
        assert "translation_status_note" not in properties


@pytest.mark.parametrize(
    "languages",
    [
        ["la"],
        ["grc", "sa"],
        ["es", "la"],  # one ancient language pulls the taxonomy in for the batch
    ],
)
def test_ancient_languages_request_status(
    monkeypatch: pytest.MonkeyPatch, languages: List[str]
) -> None:
    """The ancient group is scored on the contrast, so it keeps the taxonomy."""
    client = _run(monkeypatch, languages)

    assert "historical/native fit" in client.context  # type: ignore[operator]
    assert "modern_reimagining" in client.context  # type: ignore[operator]
    assert "late_construction" in client.context  # type: ignore[operator]
    assert "Return an empty status note" in client.context  # type: ignore[operator]
    # Numbering stays contiguous with the shared requirements above it.
    assert "6. Ensure translations match" in client.context  # type: ignore[operator]
    assert "7. For each translation" in client.context  # type: ignore[operator]
    assert "8. For the ancient/classical" in client.context  # type: ignore[operator]

    from wordfreq.translation.constants import AVAILABLE_TRANSLATION_LANGUAGES_BY_CODE

    for lang_code in languages:
        field = AVAILABLE_TRANSLATION_LANGUAGES_BY_CODE[lang_code]["field"]
        properties = _language_properties(client, field)
        assert "translation_status" in properties
        assert "translation_status_note" in properties


def test_mixed_batch_gives_every_language_the_status_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The schema is uniform across a batch; only the batch as a whole decides.

    Splitting the shape per language within one response would complicate the
    parser for no gain - a living language's "conventional" is discarded on the
    way in either way.
    """
    client = _run(monkeypatch, ["es", "la"])
    assert "translation_status" in _language_properties(client, "spanish_translation")
    assert "translation_status" in _language_properties(client, "latin_translation")
