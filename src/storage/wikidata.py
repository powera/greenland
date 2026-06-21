"""Helpers for resolving Wikidata Q-ids into concept seed data."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import requests

from storage.models.concept import MAX_CONCEPT_SOURCES

logger = logging.getLogger(__name__)

QID_RE = re.compile(r"^Q[1-9][0-9]*$", re.IGNORECASE)
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIPEDIA_EXTRACT_URL = "https://en.wikipedia.org/w/api.php"
WIKISOURCE_SEARCH_URL = "https://en.wikisource.org/w/api.php"
DEFAULT_TIMEOUT_SECONDS = 10
MAX_SOURCE_TEXT_CHARS = 12000
WIKIPEDIA_LEAD_THRESHOLD_CHARS = 10_000
EB1911_MAX_PARAGRAPHS = 10
EB1911_MAX_WORDS = 1200


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


def _get_json(url: str, *, params: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    """Fetch JSON with a short timeout, returning None on HTTP/network errors."""
    try:
        response = requests.get(
            url,
            params=params,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            headers={"User-Agent": "Greenland-Barsukas/1.0 (Wikidata concept seeding)"},
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        logger.warning("Failed to fetch JSON from %s: %s", url, error)
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _extract_english_value(values: Dict[str, Dict[str, str]]) -> str:
    """Extract an English Wikidata label/description value."""
    english = values.get("en", {})
    return str(english.get("value", "")).strip()


def _fetch_wikipedia_extract(
    page_title: str, *, lead_only: bool = False
) -> Optional[Dict[str, str]]:
    """Fetch a Wikipedia plain-text extract for a page."""
    # TODO: Switch source hydration to a local Wikipedia dump so concept creation
    # does not depend on live API availability and repeated network calls.
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
    payload = _get_json(WIKIPEDIA_EXTRACT_URL, params=params)
    pages = (payload or {}).get("query", {}).get("pages", [])
    if not pages:
        return None
    page = pages[0]
    extract = str(page.get("extract", "")).strip()
    title = str(page.get("title", page_title)).strip() or page_title
    if not extract:
        return None
    return {"title": title, "extract": extract}


def _fetch_wikipedia_source(page_title: str) -> Optional[Dict[str, Any]]:
    """Return a Wikipedia source dict with full short articles or lead-only long articles."""
    page_extract = _fetch_wikipedia_extract(page_title)
    if page_extract is None:
        return None
    extract = page_extract["extract"]
    title = page_extract["title"]
    note = "Plain-text Wikipedia article extract for concept generation."
    if len(extract) > WIKIPEDIA_LEAD_THRESHOLD_CHARS:
        lead_extract = _fetch_wikipedia_extract(title, lead_only=True)
        if lead_extract is not None:
            extract = lead_extract["extract"]
            title = lead_extract["title"]
        note = (
            "Plain-text Wikipedia lead section for concept generation; full article exceeded 10 KB."
        )
    return {
        "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
        "title": f"Wikipedia: {title}",
        "note": note,
        "text": extract[:MAX_SOURCE_TEXT_CHARS],
    }


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


def _fetch_eb1911_source(title: str, label: str = "") -> Optional[Dict[str, Any]]:
    """Try to find an EB1911 Wikisource page for the topic and return its extract."""
    page_title = _search_eb1911_page_title(_eb1911_search_titles(title, label))
    if page_title is None:
        return None
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
    extract = str(pages[0].get("extract", "")).strip()
    if not extract:
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


def fetch_wikidata_concept_seed(raw_qid: str) -> Optional[WikidataConceptSeed]:
    """Resolve a Wikidata Q-id into a concept title, summary, and default sources."""
    qid = normalize_qid(raw_qid)
    if qid is None:
        return None

    payload = _get_json(WIKIDATA_ENTITY_URL.format(qid=qid))
    entity = (payload or {}).get("entities", {}).get(qid)
    if not isinstance(entity, dict):
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
            WIKIPEDIA_SUMMARY_URL.format(title=enwiki_title.replace(" ", "%20"))
        )
        extract = str((summary_payload or {}).get("extract", "")).strip()
        summary = extract.split(".")[0].strip() + "." if extract and not description else summary

    sources: List[Dict[str, Any]] = [
        {
            "url": f"https://www.wikidata.org/wiki/{qid}",
            "title": f"Wikidata: {qid}",
            "note": "Wikidata entity used to seed the concept title and summary.",
        }
    ]
    if enwiki_title:
        wikipedia_source = _fetch_wikipedia_source(enwiki_title)
        if wikipedia_source is not None:
            sources.append(wikipedia_source)
    eb1911_source = _fetch_eb1911_source(title, label)
    if eb1911_source is not None:
        sources.append(eb1911_source)

    return WikidataConceptSeed(
        qid=qid,
        title=title,
        summary=summary,
        sources=sources[:MAX_CONCEPT_SOURCES],
    )
