#!/usr/bin/env python3
"""
Client for querying BARSUKAS server as a cache for translations.

This client provides read-only access to a remote BARSUKAS server's translation
database, allowing agents to reuse existing translations without making LLM calls.
"""

import logging
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


class BarsukasCacheClient:
    """Client for fetching cached translations from a BARSUKAS server."""

    def __init__(self, base_url: str, cache_only: bool = False, debug: bool = False):
        """
        Initialize the cache client.

        Args:
            base_url: Base URL of BARSUKAS server (e.g., "http://server:5000")
            cache_only: If True, raise errors on cache miss instead of returning None
            debug: Enable debug logging
        """
        self.base_url = base_url.rstrip("/")
        self.cache_only = cache_only
        self.debug = debug

        if debug:
            logger.setLevel(logging.DEBUG)

        logger.info(f"Initialized BARSUKAS cache client: {self.base_url}")
        if cache_only:
            logger.info("Cache-only mode enabled: will fail on cache miss")

    def get_translations(self, guid: str) -> Optional[Dict[str, str]]:
        """
        Fetch translations for a lemma from the cache.

        Args:
            guid: Lemma GUID (e.g., "N14_001")

        Returns:
            Dictionary mapping language codes to translations (e.g., {"lt": "valgyti", "fr": "manger"})
            Returns None on cache miss or network error (unless cache_only=True)

        Raises:
            CacheMissError: If cache_only=True and translations not found in cache
            CacheNetworkError: If cache_only=True and network error occurs
        """
        if not guid:
            if self.cache_only:
                raise CacheMissError("Cannot query cache: lemma has no GUID")
            logger.debug("Lemma has no GUID, skipping cache lookup")
            return None

        url = f"{self.base_url}/api/v1/lemma/{guid}/translations"

        try:
            logger.debug(f"Fetching translations from cache: {url}")
            response = requests.get(url, timeout=10)

            if response.status_code == 404:
                if self.cache_only:
                    raise CacheMissError(f"Lemma {guid} not found in cache (404)")
                logger.debug(f"Cache miss: lemma {guid} not found (404)")
                return None

            if response.status_code != 200:
                error_msg = f"Cache returned status {response.status_code} for {guid}"
                if self.cache_only:
                    raise CacheNetworkError(error_msg)
                logger.warning(f"{error_msg}, skipping cache")
                return None

            response_data = response.json()

            # Validate response format (API returns {"data": {...}, "metadata": {...}})
            if not isinstance(response_data, dict):
                error_msg = f"Cache returned invalid format for {guid}: expected dict, got {type(response_data)}"
                if self.cache_only:
                    raise CacheNetworkError(error_msg)
                logger.warning(f"{error_msg}, skipping cache")
                return None

            # Extract translations from the "data" field
            translations = response_data.get("data", {})
            if not isinstance(translations, dict):
                error_msg = f"Cache returned invalid 'data' field for {guid}: expected dict, got {type(translations)}"
                if self.cache_only:
                    raise CacheNetworkError(error_msg)
                logger.warning(f"{error_msg}, skipping cache")
                return None

            # Filter out empty translations
            filtered_translations = {
                lang_code: translation
                for lang_code, translation in translations.items()
                if translation and isinstance(translation, str) and translation.strip()
            }

            if not filtered_translations:
                if self.cache_only:
                    raise CacheMissError(f"Lemma {guid} has no translations in cache")
                logger.debug(f"Cache returned no translations for {guid}")
                return None

            logger.info(f"Cache hit for {guid}: {len(filtered_translations)} translations")
            logger.debug(f"Cached translations for {guid}: {filtered_translations}")
            return filtered_translations

        except requests.RequestException as e:
            error_msg = f"Network error fetching from cache for {guid}: {e}"
            if self.cache_only:
                raise CacheNetworkError(error_msg) from e
            logger.warning(f"{error_msg}, skipping cache")
            return None

    def get_pronunciations(self, guid: str, language: str = "en") -> Optional[Dict[str, str]]:
        """
        Fetch pronunciations for a lemma from the cache.

        Args:
            guid: Lemma GUID (e.g., "N14_001")
            language: Language code to get pronunciations for (default: "en")

        Returns:
            Dictionary with 'ipa' and 'phonetic' keys (e.g., {"ipa": "/iːt/", "phonetic": "EET"})
            Returns None on cache miss or network error (unless cache_only=True)

        Raises:
            CacheMissError: If cache_only=True and pronunciations not found in cache
            CacheNetworkError: If cache_only=True and network error occurs
        """
        if not guid:
            if self.cache_only:
                raise CacheMissError("Cannot query cache: lemma has no GUID")
            logger.debug("Lemma has no GUID, skipping cache lookup")
            return None

        url = f"{self.base_url}/api/v1/lemma/{guid}/pronunciations"

        try:
            logger.debug(f"Fetching pronunciations from cache: {url}?language={language}")
            response = requests.get(url, params={"language": language}, timeout=10)

            if response.status_code == 404:
                if self.cache_only:
                    raise CacheMissError(f"Lemma {guid} not found in cache (404)")
                logger.debug(f"Cache miss: lemma {guid} not found (404)")
                return None

            if response.status_code != 200:
                error_msg = f"Cache returned status {response.status_code} for {guid}"
                if self.cache_only:
                    raise CacheNetworkError(error_msg)
                logger.warning(f"{error_msg}, skipping cache")
                return None

            data = response.json()

            # The API returns {"data": {lang_code: {ipa: ..., phonetic: ...}}, "metadata": {...}}
            # Extract the language-specific pronunciation if it exists
            if not isinstance(data, dict) or "data" not in data:
                error_msg = f"Cache returned invalid format for {guid}: missing 'data' key"
                if self.cache_only:
                    raise CacheNetworkError(error_msg)
                logger.warning(f"{error_msg}, skipping cache")
                return None

            pronunciations = data["data"]

            if language not in pronunciations:
                if self.cache_only:
                    raise CacheMissError(f"Lemma {guid} has no {language} pronunciations in cache")
                logger.debug(f"Cache returned no {language} pronunciations for {guid}")
                return None

            pronunciation_data = pronunciations[language]

            # Check if at least one pronunciation is populated
            if not pronunciation_data.get("ipa") and not pronunciation_data.get("phonetic"):
                if self.cache_only:
                    raise CacheMissError(
                        f"Lemma {guid} has empty {language} pronunciations in cache"
                    )
                logger.debug(f"Cache returned empty {language} pronunciations for {guid}")
                return None

            logger.info(f"Cache hit for {guid} pronunciations ({language})")
            logger.debug(f"Cached pronunciations for {guid}: {pronunciation_data}")
            result: Dict[str, str] = pronunciation_data
            return result

        except requests.RequestException as e:
            error_msg = f"Network error fetching pronunciations from cache for {guid}: {e}"
            if self.cache_only:
                raise CacheNetworkError(error_msg) from e
            logger.warning(f"{error_msg}, skipping cache")
            return None


class CacheMissError(Exception):
    """Raised when cache_only=True and translation not found in cache."""

    pass


class CacheNetworkError(Exception):
    """Raised when cache_only=True and network error occurs."""

    pass
