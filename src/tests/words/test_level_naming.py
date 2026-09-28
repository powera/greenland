"""Level naming against a stub LLM client: what gets written, and what is kept."""

from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Tuple

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from storage.crud.curriculum_level import get_curriculum_level, set_curriculum_level
from storage.models.schema import Base, Lemma
from words import level_naming


class StubClient:
    """Returns queued structured payloads and records each prompt."""

    def __init__(self, payloads: List[Dict[str, Any]]) -> None:
        self.payloads = list(payloads)
        self.prompts: List[str] = []

    def generate_chat(self, prompt: str, model: str, json_schema: Dict[str, Any]) -> Any:
        self.prompts.append(prompt)
        return SimpleNamespace(structured_data=self.payloads.pop(0))


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        for index, text in enumerate(["apple", "bread", "cheese"]):
            database_session.add(
                Lemma(
                    guid=f"N01_{index:03d}",
                    lemma_text=text,
                    definition_text=f"a {text}",
                    pos_type="noun",
                    pos_subtype="food",
                    difficulty_level=100,
                    frequency_rank=index + 1,
                )
            )
        database_session.flush()
        yield database_session


def _use(monkeypatch: pytest.MonkeyPatch, client: StubClient) -> None:
    def resolve(config: Any) -> Tuple[StubClient, str]:
        return client, "stub-model"

    monkeypatch.setattr(level_naming, "_resolve_client", resolve)


def test_generate_names_an_unnamed_level_from_its_words(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_curriculum_level(session, 105, name="Food & Drink")
    client = StubClient([{"name": "Food 2", "cefr": "A2", "rationale": "groceries"}])
    _use(monkeypatch, client)

    result = level_naming.generate_level_name(session, 100)

    assert result["written"]
    row = get_curriculum_level(session, 100)
    assert row is not None and (row.name, row.cefr) == ("Food 2", "A2")
    # Words most frequent first, and the other levels' titles for series naming.
    assert "- apple (noun/food)" in client.prompts[0]
    assert client.prompts[0].index("apple") < client.prompts[0].index("cheese")
    assert "- 105: Food & Drink" in client.prompts[0]


def test_generate_keeps_an_existing_name_unless_overwriting(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_curriculum_level(session, 100, name="Groceries", cefr="A1", prerequisites=[20])
    client = StubClient([{"name": "Food 2", "cefr": "B1", "rationale": ""}])
    _use(monkeypatch, client)

    assert not level_naming.generate_level_name(session, 100)["written"]
    assert client.prompts == []

    level_naming.generate_level_name(session, 100, overwrite=True)
    row = get_curriculum_level(session, 100)
    assert row is not None
    # The name is replaced; the hand-set CEFR and prerequisites are not.
    assert (row.name, row.cefr, row.get_prerequisites()) == ("Food 2", "A1", [20])


def test_generate_refuses_an_empty_level(session: Session) -> None:
    with pytest.raises(ValueError, match="no words"):
        level_naming.generate_level_name(session, 500)


def test_translate_fills_missing_languages_only(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_curriculum_level(session, 100, name="Food 2", translations={"es": "Comida 2"})
    client = StubClient(
        [
            {
                "translations": [
                    {"language": "lt", "name": "Maistas 2"},
                    {"language": "fr", "name": "Nourriture 2"},
                    {"language": "de", "name": "unrequested"},
                ]
            }
        ]
    )
    _use(monkeypatch, client)

    written = level_naming.translate_level_name(session, 100, languages=["es", "lt", "fr"])

    assert written == {"lt": "Maistas 2", "fr": "Nourriture 2"}
    row = get_curriculum_level(session, 100)
    assert row is not None
    assert row.get_translations() == {"es": "Comida 2", "fr": "Nourriture 2", "lt": "Maistas 2"}
    # Spanish already had a name, so it was not asked for.
    assert "- es:" not in client.prompts[0] and "- lt:" in client.prompts[0]


def test_translate_with_nothing_missing_makes_no_call(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_curriculum_level(session, 100, name="Food 2", translations={"es": "Comida 2"})
    client = StubClient([])
    _use(monkeypatch, client)

    assert level_naming.translate_level_name(session, 100, languages=["es"]) == {}
    assert client.prompts == []
