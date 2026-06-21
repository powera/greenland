from __future__ import annotations

from typing import Any, Dict, Optional

import pytest
from agents.vovere import VovereAgent, html_to_text
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from storage.crud.concept import create_concept, get_wikidata_index, link_wikidata_concept
from storage.models.concept import Base
from storage.wikidata import (
    _eb1911_search_titles,
    _extract_eb1911_page_qids,
    _fetch_eb1911_source,
    _fetch_wikipedia_source,
    _html_to_text_with_wikilinks,
    _limit_eb1911_extract,
    _strip_eb1911_sections_index,
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


def test_wikipedia_html_to_text_preserves_wikilink_targets() -> None:
    html = """
    <div class="mw-parser-output">
      <p><b>Chicago</b> is on <a href="/wiki/Lake_Michigan">the lake</a> and in
      <a href="/wiki/Illinois">Illinois</a>.</p>
      <p><a href="/wiki/Help:Contents">Help</a> links are not article signals.</p>
    </div>
    """

    text = _html_to_text_with_wikilinks(html)

    assert "[[Lake Michigan|the lake]]" in text
    assert "[[Illinois]]" in text
    assert "[[Help:Contents" not in text


def test_wikipedia_html_to_text_removes_trailing_references() -> None:
    html = """
    <div class="mw-parser-output">
      <p>Useful article lead with <a href="/wiki/Chicago">Chicago</a>.</p>
      <h2>References</h2>
      <ol class="references"><li>Reference text should disappear.</li></ol>
      <h2>External links</h2>
      <p>External link text should disappear.</p>
    </div>
    """

    text = _html_to_text_with_wikilinks(html)

    assert "Useful article lead with [[Chicago]]." in text
    assert "References" not in text
    assert "Reference text should disappear" not in text
    assert "External link text should disappear" not in text


def test_wikipedia_source_uses_parsed_html_with_wikilinks(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_get_json(
        url: str, *, params: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        assert params is not None
        assert params.get("action") == "parse"
        return {
            "parse": {
                "title": "Chicago",
                "text": '<div class="mw-parser-output"><p>City in <a href="/wiki/Illinois">Illinois</a>.</p></div>',
            }
        }

    monkeypatch.setattr("storage.wikidata._get_json", fake_get_json)

    source = _fetch_wikipedia_source("Chicago")

    assert source is not None
    assert "[[Illinois]]" in source["text"]
    assert "wiki-link markers" in source["note"]


def test_wikipedia_source_uses_lead_for_long_articles(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[bool] = []

    def fake_fetch(
        page_title: str, *, language_code: str = "en", lead_only: bool = False
    ) -> Optional[Dict[str, str]]:
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


def test_eb1911_sections_index_is_removed_before_limiting() -> None:
    extract = """Sections
I.—Physical Geography
II.—Geology
III.—Climate
IV.—Fauna and Flora
V.—Population and Social Conditions

UNITED STATES, a federal republic of North America.

Second paragraph.
"""

    assert _strip_eb1911_sections_index(extract).startswith("UNITED STATES")
    limited_extract, intro_only = _limit_eb1911_extract(extract)

    assert (
        limited_extract
        == "UNITED STATES, a federal republic of North America.\n\nSecond paragraph."
    )
    assert intro_only is True


def test_eb1911_page_qids_use_p1343_p805_claims() -> None:
    entity = {
        "claims": {
            "P1343": [
                {
                    "mainsnak": {
                        "datavalue": {"value": {"id": "Q867541"}},
                    },
                    "qualifiers": {
                        "P805": [
                            {"datavalue": {"value": {"id": "Q64437865"}}},
                        ]
                    },
                },
                {
                    "mainsnak": {
                        "datavalue": {"value": {"id": "Q123"}},
                    },
                    "qualifiers": {
                        "P805": [
                            {"datavalue": {"value": {"id": "Q999"}}},
                        ]
                    },
                },
            ]
        }
    }

    assert _extract_eb1911_page_qids(entity) == ["Q64437865"]


def test_eb1911_source_uses_direct_existing_page_before_search(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []

    def fake_get_json(
        url: str, *, params: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        assert params is not None
        calls.append(params.get("action", ""))
        assert params.get("titles") == "1911 Encyclopædia Britannica/Chicago"
        return {
            "query": {
                "pages": [
                    {
                        "title": "1911 Encyclopædia Britannica/Chicago",
                        "extract": "Chicago EB1911 text",
                    }
                ]
            }
        }

    monkeypatch.setattr("storage.wikidata._get_json", fake_get_json)

    source = _fetch_eb1911_source("Chicago")

    assert source is not None
    assert source["url"] == "https://en.wikisource.org/wiki/1911_Encyclopædia_Britannica/Chicago"
    assert source["text"] == "Chicago EB1911 text"
    assert calls == ["query", "query"]


def test_eb1911_source_prefers_wikidata_p805_wikisource_page(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    entity = {
        "claims": {
            "P1343": [
                {
                    "mainsnak": {"datavalue": {"value": {"id": "Q867541"}}},
                    "qualifiers": {"P805": [{"datavalue": {"value": {"id": "Q64437865"}}}]},
                }
            ]
        }
    }

    def fake_fetch_entity(qid: str) -> Optional[Dict[str, Any]]:
        assert qid == "Q64437865"
        return {
            "sitelinks": {
                "enwikisource": {"title": "1911 Encyclopædia Britannica/Lincoln, Abraham"}
            }
        }

    def fake_get_json(
        url: str, *, params: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        assert params is not None
        assert params.get("titles") == "1911 Encyclopædia Britannica/Lincoln, Abraham"
        return {"query": {"pages": [{"extract": "Lincoln EB1911 text"}]}}

    monkeypatch.setattr("storage.wikidata._fetch_wikidata_entity", fake_fetch_entity)
    monkeypatch.setattr("storage.wikidata._get_json", fake_get_json)

    source = _fetch_eb1911_source("Abraham Lincoln", entity=entity)

    assert source is not None
    assert (
        source["url"]
        == "https://en.wikisource.org/wiki/1911_Encyclopædia_Britannica/Lincoln,_Abraham"
    )
    assert source["text"] == "Lincoln EB1911 text"


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
        "Wikipedia: Douglas Adams",
        "EB1911: Douglas Adams",
    ]
    assert all(not source["title"].startswith("Wikidata:") for source in seed.sources)


def test_fetch_wikidata_seed_can_include_regional_wikipedia_sources(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_get_json(
        url: str, *, params: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        if "Special:EntityData" in url:
            return {
                "entities": {
                    "Q1204": {
                        "labels": {"en": {"value": "Illinois"}},
                        "descriptions": {"en": {"value": "state of the United States"}},
                        "sitelinks": {
                            "enwiki": {"title": "Illinois"},
                            "dewiki": {"title": "Illinois"},
                            "frwiki": {"title": "Illinois"},
                        },
                    }
                }
            }
        if "rest_v1/page/summary" in url:
            return {"extract": "Illinois is a state. More text."}
        if "en.wikipedia.org/w/api.php" in url:
            return {"query": {"pages": [{"title": "Illinois", "extract": "English text"}]}}
        if "de.wikipedia.org/w/api.php" in url:
            return {"query": {"pages": [{"title": "Illinois", "extract": "German text"}]}}
        if "fr.wikipedia.org/w/api.php" in url:
            return {"query": {"pages": [{"title": "Illinois", "extract": "French text"}]}}
        if params and params.get("list") == "search":
            return {"query": {"search": []}}
        return {"query": {"pages": []}}

    monkeypatch.setattr("storage.wikidata._get_json", fake_get_json)

    seed = fetch_wikidata_concept_seed("Q1204", include_regional_wikis=True)

    assert seed is not None
    assert [source["title"] for source in seed.sources] == [
        "Wikipedia: Illinois",
        "Wikipedia (de): Illinois",
        "Wikipedia (fr): Illinois",
    ]
    assert "regional" in seed.sources[1]["note"].lower()
    assert all(not source["title"].startswith("Wikidata:") for source in seed.sources)


def test_get_json_retries_429_with_wikimedia_headers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[dict[str, Any]] = []

    class FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code
            self.headers: dict[str, str] = {"Retry-After": "0"}

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError("unexpected status")

        def json(self) -> dict[str, str]:
            return {"ok": "yes"}

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        calls.append(kwargs)
        return FakeResponse(429 if len(calls) == 1 else 200)

    monkeypatch.setattr("storage.wikidata.requests.get", fake_get)
    monkeypatch.setattr("storage.wikidata.time.sleep", lambda delay: None)

    from storage.wikidata import _get_json

    assert _get_json("https://en.wikisource.org/w/api.php", params={"action": "query"}) == {
        "ok": "yes"
    }
    assert len(calls) == 2
    assert calls[0]["headers"]["Api-User-Agent"]
    assert calls[0]["params"]["maxlag"] == "5"


def test_vovere_skips_wikidata_generation_sources() -> None:
    agent = VovereAgent.__new__(VovereAgent)

    messages = agent._build_source_messages(
        [
            {
                "url": "https://www.wikidata.org/wiki/Q12439",
                "title": "Wikidata: Detroit",
                "text": "Jump to content From Wikidata junk",
            }
        ]
    )

    assert messages == []


def test_vovere_html_to_text_removes_navigation_chrome() -> None:
    pytest.importorskip("bs4")
    html = """
    <html>
      <body>
        <nav>Main menu should disappear</nav>
        <header>Header should disappear</header>
        <main><p>Useful article text remains.</p></main>
        <footer>Footer should disappear</footer>
      </body>
    </html>
    """

    text = html_to_text(html)

    assert "Useful article text remains." in text
    assert "Main menu should disappear" not in text
    assert "Header should disappear" not in text
    assert "Footer should disappear" not in text


def test_vovere_uses_provided_source_text(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    agent = VovereAgent.__new__(VovereAgent)
    monkeypatch.setattr(agent, "fetch_source_text", lambda url: "fetched text")

    messages = agent._build_source_messages(
        [{"url": "https://example.invalid", "title": "Example", "text": "provided text"}]
    )

    assert len(messages) == 1
    assert "provided text" in messages[0]["content"]
    assert "fetched text" not in messages[0]["content"]
