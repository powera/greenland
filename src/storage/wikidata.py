"""Helpers for resolving Wikidata Q-ids into concept seed data."""

from __future__ import annotations

import logging
from html.parser import HTMLParser
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote, unquote

import requests

from storage.models.concept import MAX_CONCEPT_SOURCES

logger = logging.getLogger(__name__)

QID_RE = re.compile(r"^Q[1-9][0-9]*$", re.IGNORECASE)
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIPEDIA_EXTRACT_URL = "https://{language_code}.wikipedia.org/w/api.php"
WIKISOURCE_SEARCH_URL = "https://en.wikisource.org/w/api.php"
DEFAULT_TIMEOUT_SECONDS = 10
MAX_HTTP_ATTEMPTS = 3
DEFAULT_USER_AGENT = os.environ.get(
    "GREENLAND_HTTP_USER_AGENT",
    "Greenland-Barsukas/1.0 (concept seeding; set GREENLAND_HTTP_USER_AGENT with contact)",
)
MAX_SOURCE_TEXT_CHARS = 12000
WIKIPEDIA_LEAD_THRESHOLD_CHARS = 10_000
EB1911_MAX_PARAGRAPHS = 10
EB1911_MAX_WORDS = 1200
EB1911_WIKIDATA_QID = "Q867541"
REGIONAL_WIKIPEDIA_LANGUAGE_CODES = ("de", "fr")


def _wikilink_markup(label: str, target: str) -> str:
    """Return a compact wiki-link marker for parsed article text."""
    clean_label = " ".join(label.split())
    clean_target = unquote(target).replace("_", " ").strip()
    if not clean_label or not clean_target:
        return clean_label
    if clean_label == clean_target:
        return f"[[{clean_target}]]"
    return f"[[{clean_target}|{clean_label}]]"


class _WikiLinkHTMLTextParser(HTMLParser):
    """Small HTML-to-text parser that emits wiki-link markers for article links."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self.skip_depth = 0
        self.current_href = ""
        self.current_label_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr_map = {name: value or "" for name, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if self.skip_depth:
            self.skip_depth += 1
            return
        if tag in {"script", "style", "table"} or classes.intersection(
            {"navbox", "vertical-navbox", "metadata", "ambox", "infobox", "sidebar"}
        ):
            self.skip_depth += 1
            return
        if tag == "a":
            self.current_href = attr_map.get("href", "")
            self.current_label_parts = []
        elif tag in {"p", "div", "li", "br", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag == "a" and self.current_href:
            label = "".join(self.current_label_parts)
            if self.current_href.startswith("/wiki/") and ":" not in self.current_href.removeprefix(
                "/wiki/"
            ):
                self.parts.append(_wikilink_markup(label, self.current_href.removeprefix("/wiki/")))
            else:
                self.parts.append(label)
            self.current_href = ""
            self.current_label_parts = []
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.current_href:
            self.current_label_parts.append(data)
        else:
            self.parts.append(data)

    def get_text(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _html_to_text_with_wikilinks(html: str) -> str:
    """Convert parsed Wikimedia HTML to text while preserving internal link targets."""
    parser = _WikiLinkHTMLTextParser()
    parser.feed(html)
    return parser.get_text()


def _fetch_wikipedia_parsed_text(
    page_title: str, *, language_code: str = "en", lead_only: bool = False
) -> Optional[Dict[str, str]]:
    """Fetch parsed Wikipedia text with wiki-link markers preserved."""
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "text",
        "redirects": "1",
        "disableeditsection": "1",
        "format": "json",
        "formatversion": "2",
    }
    if lead_only:
        params["section"] = "0"
    payload = _get_json(WIKIPEDIA_EXTRACT_URL.format(language_code=language_code), params=params)
    parsed_page = (payload or {}).get("parse", {})
    html = str(parsed_page.get("text", "")).strip()
    title = str(parsed_page.get("title", page_title)).strip() or page_title
    if not html:
        return None
    text = _html_to_text_with_wikilinks(html)
    if not text:
        return None
    return {"title": title, "extract": text}


def _word_count(text: str) -> int:
    """Return a simple whitespace-delimited word count."""
    return len(text.split())


def _limit_eb1911_extract(extract: str) -> tuple[str, bool]:
    """Return an EB1911 extract limited to an intro-sized excerpt when needed."""
    paragraphs = [
        paragraph.strip() for paragraph in re.split(r"\n\s*\n", extract) if paragraph.strip()
    ]
    if len(paragraphs) <= EB1911_MAX_PARAGRAPHS and _word_count(extract) <= EB1911_MAX_WORDS:
        return extract, False

    selected_paragraphs: List[str] = []
    selected_words = 0
    for paragraph in paragraphs:
        paragraph_words = _word_count(paragraph)
        if selected_paragraphs and (
            len(selected_paragraphs) >= EB1911_MAX_PARAGRAPHS
            or selected_words + paragraph_words > EB1911_MAX_WORDS
        ):
            break
        selected_paragraphs.append(paragraph)
        selected_words += paragraph_words
        if len(selected_paragraphs) >= EB1911_MAX_PARAGRAPHS or selected_words >= EB1911_MAX_WORDS:
            break

    if not selected_paragraphs:
        return " ".join(extract.split()[:EB1911_MAX_WORDS]), True
    return "\n\n".join(selected_paragraphs), True


def _eb1911_search_titles(title: str, label: str = "") -> List[str]:
    """Return likely EB1911 page-title candidates for a Wikidata concept."""
    candidates: List[str] = []
    for raw_title in (title, label):
        clean_title = raw_title.strip()
        if not clean_title:
            continue
        candidates.append(clean_title)
        parts = clean_title.split()
        if len(parts) == 2:
            candidates.append(f"{parts[1]}, {parts[0]}")
    deduped: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.casefold()
        if normalized not in seen:
            deduped.append(candidate)
            seen.add(normalized)
    return deduped


@dataclass(frozen=True)
class WikidataConceptSeed:
    """Concept seed data derived from a Wikidata entity."""

    qid: str
    title: str
    summary: str
    sources: List[Dict[str, Any]] = field(default_factory=list)


def normalize_qid(raw_qid: str) -> Optional[str]:
    """Return canonical uppercase Q-id, or None if the input is invalid."""
    qid = raw_qid.strip().upper()
    if QID_RE.match(qid):
        return qid
    return None


def _retry_delay_seconds(response: requests.Response, attempt_index: int) -> float:
    """Return a short retry delay for rate-limited Wikimedia responses."""
    retry_after = response.headers.get("Retry-After", "").strip()
    if retry_after.isdigit():
        return min(float(retry_after), 5.0)
    fallback_delay: float = 0.5 * float(2**attempt_index)
    return min(fallback_delay, 5.0)


def _get_json(url: str, *, params: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    """Fetch JSON with Wikimedia-friendly headers and limited 429 retries."""
    request_params = dict(params or {})
    if "/w/api.php" in url:
        request_params.setdefault("maxlag", "5")
        request_params.setdefault("format", "json")

    last_error: Optional[Exception] = None
    for attempt_index in range(MAX_HTTP_ATTEMPTS):
        try:
            response = requests.get(
                url,
                params=request_params or None,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Api-User-Agent": DEFAULT_USER_AGENT,
                },
            )
            if response.status_code in {429, 503} and attempt_index < MAX_HTTP_ATTEMPTS - 1:
                time.sleep(_retry_delay_seconds(response, attempt_index))
                continue
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt_index < MAX_HTTP_ATTEMPTS - 1 and isinstance(error, requests.HTTPError):
                error_response = error.response
                if error_response is not None and error_response.status_code in {429, 503}:
                    time.sleep(_retry_delay_seconds(error_response, attempt_index))
                    continue
            break
        if isinstance(payload, dict):
            return payload
        return None

    logger.warning("Failed to fetch JSON from %s: %s", url, last_error)
    return None


def _extract_entity_qid(snak: Dict[str, Any]) -> Optional[str]:
    """Extract a Wikidata entity Q-id from a claim snak."""
    data_value = snak.get("datavalue", {})
    value = data_value.get("value", {})
    if not isinstance(value, dict):
        return None
    raw_id = value.get("id")
    if isinstance(raw_id, str):
        return normalize_qid(raw_id)
    numeric_id = value.get("numeric-id")
    if isinstance(numeric_id, int):
        return normalize_qid(f"Q{numeric_id}")
    return None


def _fetch_wikidata_entity(qid: str) -> Optional[Dict[str, Any]]:
    """Fetch a single Wikidata entity JSON object."""
    payload = _get_json(WIKIDATA_ENTITY_URL.format(qid=qid))
    entity = (payload or {}).get("entities", {}).get(qid)
    if isinstance(entity, dict):
        return entity
    return None


def _extract_english_value(values: Dict[str, Dict[str, str]]) -> str:
    """Extract an English Wikidata label/description value."""
    english = values.get("en", {})
    return str(english.get("value", "")).strip()


def _fetch_wikipedia_extract(
    page_title: str, *, language_code: str = "en", lead_only: bool = False
) -> Optional[Dict[str, str]]:
    """Fetch Wikipedia article text, preserving wiki-link markers when possible."""
    # TODO: Switch source hydration to a local Wikipedia dump so concept creation
    # does not depend on live API availability and repeated network calls.
    parsed_text = _fetch_wikipedia_parsed_text(
        page_title, language_code=language_code, lead_only=lead_only
    )
    if parsed_text is not None:
        return parsed_text

    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "exsectionformat": "plain",
        "redirects": "1",
        "titles": page_title,
        "format": "json",
        "formatversion": "2",
    }
    if lead_only:
        params["exintro"] = "1"
    payload = _get_json(WIKIPEDIA_EXTRACT_URL.format(language_code=language_code), params=params)
    pages = (payload or {}).get("query", {}).get("pages", [])
    if not pages:
        return None
    page = pages[0]
    extract = str(page.get("extract", "")).strip()
    title = str(page.get("title", page_title)).strip() or page_title
    if not extract:
        return None
    return {"title": title, "extract": extract}


def _fetch_wikipedia_source(
    page_title: str, *, language_code: str = "en", regional_note: bool = False
) -> Optional[Dict[str, Any]]:
    """Return a Wikipedia source dict with full short articles or lead-only long articles."""
    page_extract = _fetch_wikipedia_extract(page_title, language_code=language_code)
    if page_extract is None:
        return None
    extract = page_extract["extract"]
    title = page_extract["title"]
    note = (
        "Wikipedia article extract for concept generation; internal links are preserved "
        "as wiki-link markers when available."
    )
    if len(extract) > WIKIPEDIA_LEAD_THRESHOLD_CHARS:
        lead_extract = _fetch_wikipedia_extract(title, language_code=language_code, lead_only=True)
        if lead_extract is not None:
            extract = lead_extract["extract"]
            title = lead_extract["title"]
        note = (
            "Wikipedia lead section for concept generation; full article exceeded 10 KB. "
            "Internal links are preserved as wiki-link markers when available."
        )
    if regional_note:
        note = (
            f"{note} Regional Wikipedia source ({language_code}); use as a supplementary "
            "perspective because coverage and framing may reflect local editorial bias."
        )
    source_label = "Wikipedia" if language_code == "en" else f"Wikipedia ({language_code})"
    return {
        "url": f"https://{language_code}.wikipedia.org/wiki/{title.replace(' ', '_')}",
        "title": f"{source_label}: {title}",
        "note": note,
        "text": extract[:MAX_SOURCE_TEXT_CHARS],
    }


def _extract_eb1911_page_qids(entity: Dict[str, Any]) -> List[str]:
    """Extract EB1911 article item Q-ids from Wikidata P1343/P805 claims."""
    page_qids: List[str] = []
    seen_qids: set[str] = set()
    for claim in entity.get("claims", {}).get("P1343", []):
        if not isinstance(claim, dict):
            continue
        mainsnak = claim.get("mainsnak", {})
        if not isinstance(mainsnak, dict):
            continue
        if _extract_entity_qid(mainsnak) != EB1911_WIKIDATA_QID:
            continue
        qualifiers = claim.get("qualifiers", {})
        if not isinstance(qualifiers, dict):
            continue
        for qualifier in qualifiers.get("P805", []):
            if not isinstance(qualifier, dict):
                continue
            page_qid = _extract_entity_qid(qualifier)
            if page_qid is not None and page_qid not in seen_qids:
                page_qids.append(page_qid)
                seen_qids.add(page_qid)
    return page_qids


def _extract_wikisource_title(entity: Dict[str, Any]) -> str:
    """Extract an English Wikisource title from a Wikidata entity."""
    sitelinks = entity.get("sitelinks", {})
    if not isinstance(sitelinks, dict):
        return ""
    return str(sitelinks.get("enwikisource", {}).get("title", "")).strip()


def _fetch_eb1911_page_extract(page_title: str) -> Optional[str]:
    """Fetch a Wikisource plain-text extract for an EB1911 page title."""
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "titles": page_title,
        "format": "json",
        "formatversion": "2",
    }
    payload = _get_json(WIKISOURCE_SEARCH_URL, params=params)
    pages = (payload or {}).get("query", {}).get("pages", [])
    if not pages:
        return None
    page = pages[0]
    if page.get("missing"):
        return None
    extract = str(page.get("extract", "")).strip()
    if not extract:
        return None
    return extract


def _find_existing_eb1911_page_title(candidates: Sequence[str]) -> Optional[str]:
    """Return the first direct EB1911 page title that has extractable text."""
    for candidate in candidates:
        page_title = f"1911 Encyclopædia Britannica/{candidate}"
        if _fetch_eb1911_page_extract(page_title) is not None:
            return page_title
    return None


def _search_eb1911_page_title(candidates: Sequence[str]) -> Optional[str]:
    """Return the first Wikisource EB1911 page title matching any candidate."""
    for candidate in candidates:
        search_title = f"1911 Encyclopædia Britannica/{candidate}"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": f'intitle:"{search_title}"',
            "srlimit": "1",
            "format": "json",
        }
        search_payload = _get_json(WIKISOURCE_SEARCH_URL, params=params)
        results = (search_payload or {}).get("query", {}).get("search", [])
        if results:
            page_title = str(results[0].get("title", "")).strip()
            if page_title:
                return page_title

        params = {
            "action": "query",
            "list": "search",
            "srsearch": f'"1911 Encyclopædia Britannica/{candidate}"',
            "srlimit": "1",
            "format": "json",
        }
        search_payload = _get_json(WIKISOURCE_SEARCH_URL, params=params)
        results = (search_payload or {}).get("query", {}).get("search", [])
        if results:
            page_title = str(results[0].get("title", "")).strip()
            if page_title:
                return page_title
    return None


def _fetch_eb1911_source(
    title: str, label: str = "", entity: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Try to find an EB1911 Wikisource page for the topic and return its extract."""
    page_title = None
    if entity is not None:
        for page_qid in _extract_eb1911_page_qids(entity):
            page_entity = _fetch_wikidata_entity(page_qid)
            if page_entity is None:
                continue
            page_title = _extract_wikisource_title(page_entity)
            if page_title:
                break
    extract = None
    if page_title:
        extract = _fetch_eb1911_page_extract(page_title)
    if extract is None:
        candidates = _eb1911_search_titles(title, label)
        page_title = _find_existing_eb1911_page_title(candidates)
        if page_title is None:
            page_title = _search_eb1911_page_title(candidates)
        if page_title is None:
            return None
        extract = _fetch_eb1911_page_extract(page_title)
    if extract is None or page_title is None:
        return None
    extract, intro_only = _limit_eb1911_extract(extract)
    note = "1911 Encyclopædia Britannica text from Wikisource."
    if intro_only:
        note = "1911 Encyclopædia Britannica intro excerpt from Wikisource; full page exceeded the concept-generation size limit."
    return {
        "url": f"https://en.wikisource.org/wiki/{page_title.replace(' ', '_')}",
        "title": f"EB1911: {title}",
        "note": note,
        "text": extract[:MAX_SOURCE_TEXT_CHARS],
    }


def fetch_wikidata_concept_seed(
    raw_qid: str, *, include_regional_wikis: bool = False
) -> Optional[WikidataConceptSeed]:
    """Resolve a Wikidata Q-id into a concept title, summary, and default sources."""
    qid = normalize_qid(raw_qid)
    if qid is None:
        return None

    entity = _fetch_wikidata_entity(qid)
    if entity is None:
        return None

    label = _extract_english_value(entity.get("labels", {}))
    description = _extract_english_value(entity.get("descriptions", {}))
    sitelinks = entity.get("sitelinks", {})
    enwiki_title = str(sitelinks.get("enwiki", {}).get("title", "")).strip()
    title = enwiki_title or label
    if not title:
        return None

    summary = description
    if enwiki_title:
        summary_payload = _get_json(
            WIKIPEDIA_SUMMARY_URL.format(title=quote(enwiki_title, safe=""))
        )
        extract = str((summary_payload or {}).get("extract", "")).strip()
        summary = extract.split(".")[0].strip() + "." if extract and not description else summary

    sources: List[Dict[str, Any]] = []
    if enwiki_title:
        wikipedia_source = _fetch_wikipedia_source(enwiki_title)
        if wikipedia_source is not None:
            sources.append(wikipedia_source)
    if include_regional_wikis:
        for language_code in REGIONAL_WIKIPEDIA_LANGUAGE_CODES:
            regional_title = str(sitelinks.get(f"{language_code}wiki", {}).get("title", "")).strip()
            if not regional_title:
                continue
            regional_source = _fetch_wikipedia_source(
                regional_title, language_code=language_code, regional_note=True
            )
            if regional_source is not None:
                sources.append(regional_source)
    eb1911_source = _fetch_eb1911_source(title, label, entity)
    if eb1911_source is not None:
        sources.append(eb1911_source)

    return WikidataConceptSeed(
        qid=qid,
        title=title,
        summary=summary,
        sources=sources[:MAX_CONCEPT_SOURCES],
    )
