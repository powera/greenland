#!/usr/bin/python3
"""Client for interacting with Google Gemini API using OpenAI compatibility layer."""

import json
import logging
import os
import time
from typing import Dict, Optional, Any

import requests
import tiktoken

import constants
from telemetry import LLMUsage
from clients.types import Response
import clients.lib

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Model identifiers
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TIMEOUT = 50
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def measure_completion(func):
    """Decorator to measure completion API call duration."""

    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        duration_ms = (time.time() - start_time) * 1000
        return result, duration_ms

    return wrapper


class GeminiClient:
    """Client for making requests to Google Gemini API via OpenAI compatibility layer."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT, debug: bool = False):
        """Initialize Gemini client with API key."""
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized GeminiClient in debug mode")
        self.api_key = self._load_key()
        self.headers = {"Content-Type": "application/json"}
        # Use the same tokenizer as OpenAI for token counting consistency
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def _load_key(self) -> str:
        """Load Google API key from file."""
        try:
            key_path = os.path.join(constants.KEY_DIR, "google.key")
            with open(key_path) as f:
                return f.read().strip()
        except:
            return ""  # Return empty string if key file not found

    @measure_completion
    def _create_completion(self, model: str, **kwargs) -> Dict:
        """Make direct HTTP request to Gemini chat completions endpoint."""
        url = f"{API_BASE}/{model}:generateContent?key={self.api_key}"

        if self.debug:
            logger.debug("Making request to %s", url)
            logger.debug("Request data: %s", json.dumps(kwargs, indent=2))

        response = requests.post(url, headers=self.headers, json=kwargs, timeout=self.timeout)

        if response.status_code != 200:
            error_msg = f"Error {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        return response.json()

    def warm_model(self, model: str) -> bool:
        """Simulate model warmup (not needed for Gemini but kept for API compatibility)."""
        if self.debug:
            logger.debug("Model warmup not required for Gemini: %s", model)
        return True

    def generate_chat(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        brief: bool = False,
        json_schema: Optional[Any] = None,
        context: Optional[str] = None,
    ) -> Response:
        """
        Generate chat completion using Gemini API.

        Args:
            prompt: The main prompt/question
            model: Model to use for generation
            brief: Whether to limit response length
            json_schema: Schema for structured response (if provided, returns JSON)
            context: Optional context to include before the prompt

        Returns:
            Response containing response_text, structured_data, and usage
            For text responses, structured_data will be empty dict
            For JSON responses, response_text will be empty string
        """
        if self.debug:
            logger.debug("Generating chat response")
            logger.debug("Model: %s", model)
            logger.debug("Brief mode: %s", brief)
            logger.debug("Context: %s", context)
            logger.debug("JSON schema: %s", json_schema)

        kwargs = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 256 if brief else 1536},
        }
        if context:
            kwargs["system_instruction"] = {"parts": [{"text": context}]}

        # If JSON schema provided, configure for structured response
        if json_schema:
            if isinstance(json_schema, clients.lib.Schema):
                schema_obj = json_schema
            else:
                schema_obj = clients.lib.schema_from_dict(json_schema)

            processed_schema = clients.lib.to_gemini_schema(schema_obj)
            kwargs["generationConfig"]["response_mime_type"] = "application/json"
            kwargs["generationConfig"]["response_schema"] = {
                "type": "ARRAY",
                "items": processed_schema,
            }

        completion_data, duration_ms = self._create_completion(model=model, **kwargs)

        response_content = completion_data["candidates"][0]["content"]["parts"][0]["text"]
        usage = LLMUsage.from_api_response(
            {
                "prompt_tokens": completion_data["usageMetadata"].get("promptTokenCount", 0),
                "completion_tokens": completion_data["usageMetadata"].get(
                    "candidatesTokenCount", 0
                ),
                "total_duration": duration_ms,
            },
            model=model,
        )

        # Parse JSON response if schema was provided
        if json_schema:
            try:
                # We seem to need the top-level response to be an array.
                structured_data = json.loads(response_content)[0]
                response_text = ""
            except json.JSONDecodeError:
                error_msg = f"Failed to parse JSON response: {response_content}"
                logger.error(error_msg)
                structured_data = {"error": error_msg}
                response_text = ""
        else:
            response_text = response_content
            structured_data = {}

        if self.debug:
            if response_text:
                logger.debug("Response text: %s", response_text)
            elif structured_data:
                logger.debug("Structured data: %s", structured_data)
            else:
                logger.debug("No response text or structured data")
            logger.debug("Usage metrics: %s", usage.to_dict())

        return Response(response_text=response_text, structured_data=structured_data, usage=usage)


# Create default client instance
client = GeminiClient(debug=False)  # Set to True to enable debug logging


# Expose key functions at module level for API compatibility
def warm_model(model: str) -> bool:
    return client.warm_model(model)


def generate_chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    brief: bool = False,
    json_schema: Optional[Any] = None,
    context: Optional[str] = None,
) -> Response:
    """
    Generate a chat response using Gemini API.

    Returns:
        Response containing response_text, structured_data, and usage
        For text responses, structured_data will be empty dict
        For JSON responses, response_text will be empty string
    """
    return client.generate_chat(prompt, model, brief, json_schema, context)
