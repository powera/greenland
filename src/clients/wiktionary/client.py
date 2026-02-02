"""Wiktionary API client for fetching linguistic data."""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class WiktionaryClient:
    """Client for accessing Wiktionary API and parsing wikitext."""

    # Wiktionary API endpoints
    API_URL = "https://en.wiktionary.org/w/api.php"

    # User-Agent header required by Wikimedia APIs
    # See: https://meta.wikimedia.org/wiki/User-Agent_policy
    DEFAULT_USER_AGENT = "LithuanianLinguisticBot/2.0 (Educational/Research; Python requests)"

    def __init__(
        self,
        timeout: int = 15,
        debug: bool = False,
        user_agent: Optional[str] = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        Initialize the Wiktionary client.

        Args:
            timeout: Request timeout in seconds
            debug: Enable debug logging
            user_agent: Custom User-Agent string (uses default if not provided)
            retry_count: Number of retries on transient failures
            retry_delay: Initial delay between retries (exponential backoff)
        """
        self.timeout = timeout
        self.debug = debug
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.headers = {"User-Agent": user_agent or self.DEFAULT_USER_AGENT}

        if debug:
            logger.setLevel(logging.DEBUG)

    def _make_request(
        self, params: Dict[str, Any], method: str = "GET"
    ) -> Optional[Dict[str, Any]]:
        """
        Make an API request with retry logic.

        Args:
            params: API parameters
            method: HTTP method (GET or POST)

        Returns:
            JSON response data or None on failure
        """
        last_error: Optional[Exception] = None

        for attempt in range(self.retry_count):
            try:
                if method == "GET":
                    response = requests.get(
                        self.API_URL,
                        params=params,
                        headers=self.headers,
                        timeout=self.timeout,
                    )
                else:
                    response = requests.post(
                        self.API_URL,
                        data=params,
                        headers=self.headers,
                        timeout=self.timeout,
                    )

                response.raise_for_status()
                return response.json()  # type: ignore[no-any-return]

            except requests.RequestException as e:
                last_error = e
                if attempt < self.retry_count - 1:
                    delay = self.retry_delay * (2**attempt)
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.retry_count}), "
                        f"retrying in {delay:.1f}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"Request failed after {self.retry_count} attempts: {e}")

        return None

    def fetch_page_wikitext(self, title: str) -> Optional[str]:
        """
        Fetch the raw wikitext content for a page.

        Args:
            title: Page title (word to look up)

        Returns:
            Raw wikitext content or None if not found
        """
        params = {
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
        }

        data = self._make_request(params)
        if not data:
            return None

        pages = data.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if page_id == "-1":
                if self.debug:
                    logger.debug(f"Page '{title}' not found in Wiktionary")
                return None

            revisions = page_data.get("revisions", [])
            if revisions:
                content: str = revisions[0].get("slots", {}).get("main", {}).get("*", "")
                return content

        return None

    def get_section_wikitext(self, word: str, language: str = "Lithuanian") -> Optional[str]:
        """
        Fetch wikitext for a specific language section directly.

        This is a convenience method that combines fetch_page_wikitext and
        extract_language_section.

        Args:
            word: The word to look up
            language: Language name (e.g., "Lithuanian", "French", "German")

        Returns:
            Language section wikitext or None if not found
        """
        wikitext = self.fetch_page_wikitext(word)
        if not wikitext:
            return None
        return self.extract_language_section(wikitext, language)

    def extract_language_section(
        self, wikitext: str, language: str = "Lithuanian"
    ) -> Optional[str]:
        """
        Extract a specific language section from Wiktionary wikitext.

        Args:
            wikitext: Full wikitext content
            language: Language name (e.g., "Lithuanian", "English")

        Returns:
            Language section text or None if not found
        """
        # Find the start of the language section (with optional spaces around heading)
        pattern = rf"==\s*{re.escape(language)}\s*=="
        heading_match = re.search(pattern, wikitext)
        if not heading_match:
            if self.debug:
                logger.debug(f"No {language} section found in wikitext")
            return None

        start = heading_match.start()

        # Find the next language section (next level-2 heading)
        rest = wikitext[heading_match.end() :]
        next_section_match = re.search(r"\n==\s*[A-Z][a-zA-Z\s]+\s*==", rest)

        if next_section_match:
            end = heading_match.end() + next_section_match.start()
            return wikitext[start:end]
        else:
            # Language section goes to end of document
            return wikitext[start:]

    def find_templates(self, wikitext: str, template_patterns: List[str]) -> List[Tuple[str, str]]:
        """
        Find all templates matching given patterns in wikitext.

        Args:
            wikitext: Wikitext to search
            template_patterns: List of regex patterns for template names

        Returns:
            List of tuples (template_name, full_template_text)
        """
        results: List[Tuple[str, str]] = []

        for pattern in template_patterns:
            # Match templates with the pattern
            # Templates are {{name|param1|param2|...}}
            # We need to handle nested templates carefully
            template_regex = rf"\{{\{{({pattern})[^}}]*\}}\}}"
            matches = re.finditer(template_regex, wikitext)
            for match in matches:
                template_name = match.group(1)
                template_text = match.group(0)
                results.append((template_name, template_text))

        return results

    def expand_template(self, template: str) -> Optional[str]:
        """
        Expand a wikitext template using the Wiktionary API.

        Args:
            template: Template text (e.g., "{{lt-noun-m-as-2|...}}")

        Returns:
            Expanded wikitext or None if expansion fails
        """
        params = {
            "action": "expandtemplates",
            "format": "json",
            "text": template,
            "prop": "wikitext",
        }

        data = self._make_request(params)
        if not data:
            return None

        if "error" in data:
            logger.warning(f"Error expanding template: {data['error']}")
            return None

        expanded: str = data.get("expandtemplates", {}).get("wikitext", "")
        return expanded

    def parse_to_html(self, wikitext: str) -> Optional[str]:
        """
        Parse wikitext to HTML using the Wiktionary API.

        Args:
            wikitext: Raw wikitext to parse (can include templates)

        Returns:
            Parsed HTML content or None if parsing fails
        """
        params = {
            "action": "parse",
            "format": "json",
            "text": wikitext,
            "prop": "text",
            "contentmodel": "wikitext",
            "disableeditsection": "true",
        }

        data = self._make_request(params)
        if not data:
            return None

        if "error" in data:
            logger.warning(f"Error parsing wikitext: {data['error']}")
            return None

        html: str = data.get("parse", {}).get("text", {}).get("*", "")
        return html

    def get_page_html(self, title: str) -> Optional[str]:
        """
        Get the rendered HTML for a Wiktionary page.

        Args:
            title: Page title

        Returns:
            Rendered HTML or None if not found
        """
        params = {
            "action": "parse",
            "format": "json",
            "page": title,
            "prop": "text",
            "disableeditsection": "true",
        }

        data = self._make_request(params)
        if not data:
            return None

        if "error" in data:
            if self.debug:
                logger.debug(f"Error fetching page HTML: {data['error']}")
            return None

        html: str = data.get("parse", {}).get("text", {}).get("*", "")
        return html

    def search_words(
        self, search_term: str, language: str = "Lithuanian", limit: int = 10
    ) -> List[str]:
        """
        Search for words in Wiktionary.

        Args:
            search_term: Term to search for
            language: Language to filter by (not directly supported, but useful for context)
            limit: Maximum number of results

        Returns:
            List of matching page titles
        """
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": search_term,
            "srlimit": limit,
        }

        data = self._make_request(params)
        if not data:
            return []

        results = data.get("query", {}).get("search", [])
        return [r["title"] for r in results]
