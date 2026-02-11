#!/usr/bin/python3

"""Client for interacting with TranslateGemma models via LMStudio's OpenAI-compatible API.

TranslateGemma is a translation-only model that requires a specific prompt format:
- System message specifying source and target languages
- User message with two blank lines before the text to translate
- Returns plain text translations (no JSON schema support)
"""

import json
import logging
import re
from typing import Any, Dict, Optional

import requests
from requests.exceptions import RequestException

from clients.lmstudio_client import SERVER, PORT
from clients.types import Response
from storage.translation_helpers import LANGUAGE_NAMES
from util.telemetry import LLMUsage

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 250


class TranslateGemmaError(Exception):
    """Base exception for TranslateGemma client errors."""

    pass


class TranslateGemmaTimeoutError(TranslateGemmaError):
    """Raised when a TranslateGemma request times out."""

    pass


class TranslateGemmaRequestError(TranslateGemmaError):
    """Raised when a TranslateGemma request fails."""

    pass


class TranslateGemmaClient:
    """Client for making translation requests to TranslateGemma via LMStudio API."""

    def __init__(
        self,
        server: str = SERVER,
        port: int = PORT,
        timeout: int = DEFAULT_TIMEOUT,
        debug: bool = False,
    ):
        self.server = server
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{server}:{port}/v1"
        self.debug = debug
        if self.debug:
            logger.setLevel(logging.DEBUG)

    def _make_request(self, endpoint: str, data: Dict[str, Any]) -> requests.Response:
        """Make HTTP request to LMStudio API."""
        url = f"{self.base_url}/{endpoint}"

        if self.debug:
            logger.debug("Request to %s: %s", url, json.dumps(data, indent=2))

        try:
            response = requests.post(url, json=data, timeout=self.timeout)
            response.raise_for_status()
            return response

        except requests.exceptions.ConnectTimeout:
            raise TranslateGemmaTimeoutError(f"Connection timed out after {self.timeout}s")
        except requests.exceptions.ReadTimeout:
            raise TranslateGemmaTimeoutError(f"Response timed out after {self.timeout}s")
        except RequestException as e:
            if e.response is not None:
                error_msg = f"Error {e.response.status_code}: {e.response.text}"
            else:
                error_msg = str(e)
            raise TranslateGemmaRequestError(error_msg) from e

    def _get_language_name(self, lang_code: str) -> str:
        """Convert a 2-letter language code to its full name.

        Args:
            lang_code: Two-letter language code (e.g., 'en', 'fr')

        Returns:
            Full language name (e.g., 'English', 'French')
        """
        name = LANGUAGE_NAMES.get(lang_code)
        if name is None:
            raise ValueError(f"Unknown language code: {lang_code}")
        return name

    def generate_translation(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        model: str,
    ) -> Response:
        """Generate a translation using TranslateGemma's specific prompt format.

        Args:
            text: Text to translate
            source_lang: Source language code (e.g., 'en')
            target_lang: Target language code (e.g., 'fr')
            model: Model identifier for LMStudio

        Returns:
            Response with translated text in response_text
        """
        source_name = self._get_language_name(source_lang)
        target_name = self._get_language_name(target_lang)

        system_message = (
            f"You are a professional translator from {source_name} to "
            f"{target_name}. Provide only the translation without any explanation."
        )
        # TranslateGemma expects two blank lines before the text
        user_message = f"\n\n{text}"

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

        data: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        response = self._make_request("chat/completions", data)
        response_data = response.json()

        # Extract content from response
        content = ""
        if "choices" in response_data and len(response_data["choices"]) > 0:
            message = response_data["choices"][0].get("message", {})
            content = message.get("content", "").strip()

        # Extract usage information
        usage: Optional[LLMUsage] = None
        if "usage" in response_data:
            usage_data = response_data["usage"]
            converted_usage = {
                "prompt_tokens": usage_data.get("prompt_tokens", 0),
                "completion_tokens": usage_data.get("completion_tokens", 0),
                "total_duration": response.elapsed.total_seconds() * 1000,
            }
            usage = LLMUsage.from_api_response(converted_usage, model=model)

        return Response(
            response_text=content,
            structured_data={},
            usage=usage,
        )

    def generate_chat(
        self,
        prompt: str,
        model: str,
        brief: bool = False,
        json_schema: Optional[Any] = None,
        context: Optional[str] = None,
    ) -> Response:
        """Generate a chat response for unified_client compatibility.

        TranslateGemma only supports translation, so this method extracts
        source/target language from the context string and treats the prompt
        as text to translate.

        JSON schema is ignored since TranslateGemma only produces plain text.

        Args:
            prompt: Text to translate
            model: Model identifier
            brief: Ignored (TranslateGemma responses are always brief)
            json_schema: Ignored (TranslateGemma doesn't support structured output)
            context: Expected to contain language pair info, e.g.,
                     "translate from English to French" or "EN to FR"

        Returns:
            Response with translated text
        """
        if json_schema:
            logger.debug("TranslateGemma does not support JSON schema; ignoring schema")

        # Try to extract language pair from context
        source_lang = "en"
        target_lang = "fr"

        if context:
            extracted = self._extract_language_pair(context)
            if extracted:
                source_lang, target_lang = extracted

        return self.generate_translation(prompt, source_lang, target_lang, model)

    def _extract_language_pair(self, context: str) -> Optional[tuple[str, str]]:
        """Extract source and target language codes from a context string.

        Looks for patterns like:
        - "from English to French"
        - "EN to FR"
        - "translate en -> fr"

        Args:
            context: Context string potentially containing language info

        Returns:
            Tuple of (source_code, target_code) or None if not found
        """
        # Build reverse lookup: name -> code
        name_to_code = {name.lower(): code for code, name in LANGUAGE_NAMES.items()}

        # Pattern: "from <lang> to <lang>"
        match = re.search(r"from\s+(\w+)\s+to\s+(\w+)", context, re.IGNORECASE)
        if match:
            source_str = match.group(1).lower()
            target_str = match.group(2).lower()

            source_code = name_to_code.get(source_str, source_str)
            target_code = name_to_code.get(target_str, target_str)

            if source_code in LANGUAGE_NAMES and target_code in LANGUAGE_NAMES:
                return source_code, target_code

        # Pattern: "<code> to <code>" (2-letter codes)
        match = re.search(r"\b([a-z]{2})\s+to\s+([a-z]{2})\b", context, re.IGNORECASE)
        if match:
            source_code = match.group(1).lower()
            target_code = match.group(2).lower()
            if source_code in LANGUAGE_NAMES and target_code in LANGUAGE_NAMES:
                return source_code, target_code

        return None

    def warm_model(self, model: str) -> bool:
        """Initialize model for faster first inference."""
        try:
            data: Dict[str, Any] = {"model": model}
            response = self._make_request("chat", data)
            return bool(response.status_code == 200)
        except TranslateGemmaError:
            return False
