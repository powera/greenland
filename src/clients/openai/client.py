#!/usr/bin/python3
"""Client for interacting with OpenAI Responses API using direct HTTP requests."""

import json
import logging
import os
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

import requests

import clients.lib
import constants
from clients.keys import load_key
from clients.types import Response
from util.telemetry import LLMUsage

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Model identifiers
TEST_MODEL = "gpt-4o-mini-2024-07-18"
PROD_MODEL = "gpt-4o-2024-11-20"
DEFAULT_MODEL = TEST_MODEL
DEFAULT_TIMEOUT = 50
API_BASE = "https://api.openai.com/v1"


F = TypeVar("F", bound=Callable[..., Any])


def measure_completion(func: F) -> Callable[..., tuple[Any, float]]:
    """Decorator to measure completion API call duration."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> tuple[Any, float]:
        start_time = time.time()
        result = func(*args, **kwargs)
        duration_ms = (time.time() - start_time) * 1000
        return result, duration_ms

    return wrapper


class OpenAIClient:
    """Client for making direct HTTP requests to OpenAI Responses API."""

    def __init__(
        self, timeout: int = DEFAULT_TIMEOUT, debug: bool = False, api_key: Optional[str] = None
    ):
        """Initialize OpenAI client with API key.

        Args:
            timeout: Request timeout in seconds
            debug: Whether to enable debug logging
            api_key: Optional API key to use instead of loading from file.
                     Useful for API server use where keys come from request parameters.
        """
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized OpenAIClient in debug mode")

        # Use provided api_key if given, otherwise load from file
        self.api_key = api_key if api_key else load_key("openai", required=False)
        if self.api_key:
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        else:
            self.headers = {}
        import tiktoken

        self.encoder = tiktoken.get_encoding("cl100k_base")

    @measure_completion
    def _create_response(self, **kwargs: Any) -> Dict[str, Any]:
        """Make direct HTTP request to OpenAI responses endpoint."""
        url = f"{API_BASE}/responses"

        if self.debug:
            logger.debug("Making request to %s", url)
            logger.debug("Request data: %s", json.dumps(kwargs, indent=2))

        response = requests.post(url, headers=self.headers, json=kwargs, timeout=self.timeout)

        if response.status_code != 200:
            error_msg = f"Error {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        result: Dict[str, Any] = response.json()
        return result

    def warm_model(self, model: str) -> bool:
        """Simulate model warmup (not needed for OpenAI but kept for API compatibility)."""
        if self.debug:
            logger.debug("Model warmup not required for OpenAI: %s", model)
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
        Generate chat response using OpenAI Responses API.

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

        Raises:
            RuntimeError: If API key is not available
        """
        # Check if API key is available
        if not self.api_key:
            raise RuntimeError("OpenAI API key not available. Please ensure the key file exists.")

        if self.debug:
            logger.debug("Generating chat response")
            logger.debug("Model: %s", model)
            logger.debug("Brief mode: %s", brief)
            logger.debug("Context: %s", context)
            logger.debug("JSON schema: %s", json_schema)

        # Determine which token limit parameter to use based on model
        # Newer reasoning models (o1, gpt-5, o3) require max_output_tokens
        reasoning_models = ["o1-", "gpt-5-", "o3-"]
        uses_output_tokens = any(model.startswith(prefix) for prefix in reasoning_models)

        # gpt-5 models don't support custom temperature (only default value of 1)
        is_gpt5_model = model.startswith("gpt-5-")
        is_gpt5_nano_or_mini = model.startswith("gpt-5-nano") or model.startswith("gpt-5-mini")

        token_limit = 512 if brief else 4096
        request_kwargs: Dict[str, Any] = {
            "model": model,
            "input": prompt,
        }

        # Add instructions (system message) if context provided
        if context:
            request_kwargs["instructions"] = context

        # Only set temperature for models that support it
        if not is_gpt5_model:
            request_kwargs["temperature"] = 0.35

        # Set token limit parameter
        if uses_output_tokens:
            request_kwargs["max_output_tokens"] = token_limit
        else:
            # For non-reasoning models, we still use max_output_tokens in Responses API
            request_kwargs["max_output_tokens"] = token_limit

        # Set reasoning and text parameters for gpt-5-nano and gpt-5-mini
        if is_gpt5_nano_or_mini:
            request_kwargs["reasoning"] = {"effort": "minimal"}
            # Only set text verbosity if not overridden by JSON schema below
            if not json_schema:
                request_kwargs["text"] = {"verbosity": "low"}

        # If JSON schema provided, configure for structured response
        if json_schema:
            if isinstance(json_schema, clients.lib.Schema):
                schema_obj = json_schema
            else:
                schema_obj = clients.lib.schema_from_dict(json_schema)

            clean_schema = clients.lib.to_openai_schema(schema_obj)

            # Lower temperature for structured output (only for models that support it)
            if not is_gpt5_model:
                request_kwargs["temperature"] = 0.15

            # Use text.format for structured outputs in Responses API
            text_config: Dict[str, Any] = {
                "format": {
                    "type": "json_schema",
                    "name": "Details",
                    "description": "N/A",
                    "strict": True,
                    "schema": clean_schema,
                }
            }

            # For gpt-5-nano and gpt-5-mini, also include verbosity
            if is_gpt5_nano_or_mini:
                text_config["verbosity"] = "low"

            request_kwargs["text"] = text_config

        response_data, duration_ms = self._create_response(**request_kwargs)

        # Extract response content from Responses API structure
        response_content = ""
        if response_data.get("output"):
            # Look for the message output item (not reasoning)
            for output_item in response_data["output"]:
                if output_item.get("type") == "message" and output_item.get("content"):
                    for content_item in output_item["content"]:
                        if content_item.get("type") == "output_text":
                            response_content = content_item.get("text", "")
                            break
                    if response_content:
                        break

        if self.debug:
            logger.debug("Response content: %s", response_content)

        # Calculate token usage
        usage_data = response_data.get("usage", {})
        usage = LLMUsage.from_api_response(
            {
                "prompt_tokens": usage_data.get("input_tokens", 0),
                "completion_tokens": usage_data.get("output_tokens", 0),
                "total_duration": duration_ms,
            },
            model=model,
        )

        # Parse JSON response if schema was provided
        if json_schema:
            try:
                structured_data = json.loads(response_content)
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


# Lazy client instance - only created when first accessed
_client: Optional[OpenAIClient] = None


def _get_client() -> OpenAIClient:
    """Get or create the default client instance."""
    global _client
    if _client is None:
        _client = OpenAIClient(debug=False)
    return _client


# Expose key functions at module level for API compatibility
def warm_model(model: str) -> bool:
    return _get_client().warm_model(model)


def generate_chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    brief: bool = False,
    json_schema: Optional[Any] = None,
    context: Optional[str] = None,
) -> Response:
    """
    Generate a chat response using OpenAI Responses API.

    Returns:
        Response containing response_text, structured_data, and usage
        For text responses, structured_data will be empty dict
        For JSON responses, response_text will be empty string
    """
    return _get_client().generate_chat(prompt, model, brief, json_schema, context)
