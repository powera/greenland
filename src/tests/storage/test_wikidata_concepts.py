from __future__ import annotations

from typing import Any, Dict, Optional

from agents.vovere import VovereAgent
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from storage.crud.concept import create_concept, get_wikidata_index, link_wikidata_concept
from storage.models.concept import Base
from storage.wikidata import (
    _eb1911_search_titles,
    _fetch_wikipedia_source,
    _limit_eb1911_extract,
    fetch_wikidata_concept_seed,
    normalize_qid,
)


def test_normalize_qid_accepts_canonical_ids() -> None:
    assert normalize_qid(" q42 ") == "Q42"
    assert normalize_qid("not-a-qid") is None
    assert normalize_qid("Q0") is None


def test_link_wikidata_concept_creates_reverse_index() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        concept = create_concept(session, title="Douglas Adams")
        assert concept is not None

        row = link_wikidata_concept(session, "q42", concept, notes="pytest")

        assert row is not None
        assert row.qid == "Q42"
        assert row.concept_id == concept.id
        assert row.rejected is False
        assert get_wikidata_index(session, "Q42") == row


def test_wikipedia_source_uses_lead_for_long_articles(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[bool] = []

    def fake_fetch(page_title: str, *, lead_only: bool = False) -> Optional[Dict[str, str]]:
        calls.append(lead_only)
        if lead_only:
            return {"title": page_title, "extract": "Lead section only"}
        return {"title": page_title, "extract": "Full article. " + ("x" * 10_001)}

    monkeypatch.setattr("storage.wikidata._fetch_wikipedia_extract", fake_fetch)

    source = _fetch_wikipedia_source("Long Article")

    assert source is not None
    assert source["text"] == "Lead section only"
    assert "lead section" in source["note"]
    assert calls == [False, True]


def test_eb1911_search_titles_include_last_first_variant() -> None:
    assert _eb1911_search_titles("Abraham Lincoln") == ["Abraham Lincoln", "Lincoln, Abraham"]


def test_eb1911_extract_uses_intro_for_long_pages() -> None:
    paragraphs = [f"Paragraph {index} text." for index in range(12)]

    extract, intro_only = _limit_eb1911_extract("\n\n".join(paragraphs))

    assert intro_only is True
    assert extract == "\n\n".join(paragraphs[:10])


def test_fetch_wikidata_seed_builds_sources_from_mocked_apis(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_get_json(
        url: str, *, params: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        if "Special:EntityData" in url:
            return {
                "entities": {
                    "Q42": {
                        "labels": {"en": {"value": "Douglas Adams"}},
                        "descriptions": {"en": {"value": "English writer and humorist"}},
                        "sitelinks": {"enwiki": {"title": "Douglas Adams"}},
                    }
                }
            }
        if "rest_v1/page/summary" in url:
            return {"extract": "Douglas Adams was an English author. More text."}
        if "en.wikipedia.org/w/api.php" in url:
            return {"query": {"pages": [{"title": "Douglas Adams", "extract": "Wikipedia text"}]}}
        if params and params.get("list") == "search":
            return {"query": {"search": [{"title": "1911 Encyclopædia Britannica/Adams, Douglas"}]}}
        return {"query": {"pages": [{"extract": "EB1911 text"}]}}

    monkeypatch.setattr("storage.wikidata._get_json", fake_get_json)

    seed = fetch_wikidata_concept_seed("q42")

    assert seed is not None
    assert seed.qid == "Q42"
    assert seed.title == "Douglas Adams"
    assert seed.summary == "English writer and humorist"
    assert [source["title"] for source in seed.sources] == [
        "Wikidata: Q42",
        "Wikipedia: Douglas Adams",
        "EB1911: Douglas Adams",
    ]


def test_vovere_uses_provided_source_text(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    agent = VovereAgent.__new__(VovereAgent)
    monkeypatch.setattr(agent, "fetch_source_text", lambda url: "fetched text")

    messages = agent._build_source_messages(
        [{"url": "https://example.invalid", "title": "Example", "text": "provided text"}]
    )

    assert len(messages) == 1
    assert "provided text" in messages[0]["content"]
    assert "fetched text" not in messages[0]["content"]
