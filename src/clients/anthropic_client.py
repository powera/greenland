#!/usr/bin/python3
"""Client for interacting with Anthropic API using direct HTTP requests."""

import json
import logging
import os
import time
from typing import Dict, Optional, Any

import requests

import constants
from telemetry import LLMUsage
from clients.types import Response, Schema
import clients.lib
from clients.keys import load_key

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Model identifiers
TEST_MODEL = "claude-3-5-haiku-20241022"
PROD_MODEL = "claude-3-7-sonnet-20250219"
DEFAULT_MODEL = TEST_MODEL
DEFAULT_TIMEOUT = 50
API_BASE = "https://api.anthropic.com/v1"


def measure_completion(func):
    """Decorator to measure completion API call duration."""

    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        duration_ms = (time.time() - start_time) * 1000
        return result, duration_ms

    return wrapper


class AnthropicClient:
    """Client for making direct HTTP requests to Anthropic API."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT, cache: bool = True, debug: bool = False):
        """
        Initialize Anthropic client with API key.

        Args:
            timeout: Request timeout in seconds
            debug: Whether to enable debug logging
            default_system_prompt: Default system prompt to use for all requests
        """
        self.timeout = timeout
        self.debug = debug
        self.cache = cache

        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized AnthropicClient in debug mode")

        self.api_key = load_key("anthropic", required=False)
        if self.api_key:
            self.headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "anthropic-beta": "prompt-caching-2024-07-31",
            }
        else:
            self.headers = {}

    @measure_completion
    def _create_message(self, **kwargs) -> Dict:
        """Make direct HTTP request to Anthropic messages endpoint."""
        url = f"{API_BASE}/messages"

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
        """Simulate model warmup (not needed for Anthropic but kept for API compatibility)."""
        if self.debug:
            logger.debug("Model warmup not required for Anthropic: %s", model)
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
        Generate chat completion using Anthropic API.

        Args:
            prompt: The main prompt/question
            model: Model to use for generation
            brief: Whether to limit response length
            json_schema: Schema for structured response (if provided, returns JSON)
            context: Optional context.

        Returns:
            Response containing response_text, structured_data, and usage
            For text responses, structured_data will be empty dict
            For JSON responses, response_text will be empty string

        Raises:
            RuntimeError: If API key is not available
        """
        # Check if API key is available
        if not self.api_key:
            raise RuntimeError("Anthropic API key not available. Please ensure the key file exists.")

        if self.debug:
            logger.debug("Generating chat response")
            logger.debug("Model: %s", model)
            logger.debug("Brief mode: %s", brief)
            logger.debug("JSON schema: %s", json_schema)

            if context:
                logger.debug("Using provided context: %s", context)

        kwargs = {
            "model": model,
            "max_tokens": 512 if brief else 3192,
            "messages": [],
        }

        system_content = []
        if context:
            system_content.append({"type": "text", "text": context})

        if json_schema:
            # Convert Schema to Anthropic format
            if isinstance(json_schema, Schema):
                anthropic_schema = clients.lib.to_anthropic_schema(json_schema)
            elif isinstance(json_schema, dict):
                # Convert dict to Schema object first, then to Anthropic format
                schema_obj = clients.lib.schema_from_dict(json_schema)
                anthropic_schema = clients.lib.to_anthropic_schema(schema_obj)
            else:
                raise ValueError(f"Unexpected json_schema type: {type(json_schema)}")

            # Set up tools parameter for structured output
            kwargs["tools"] = [
                {
                    "type": "custom",
                    "name": (
                        json_schema.name
                        if isinstance(json_schema, Schema)
                        else "structured_response"
                    ),
                    "description": (
                        json_schema.description
                        if isinstance(json_schema, Schema)
                        else "Structured response schema"
                    ),
                    "input_schema": anthropic_schema,
                }
            ]

            # Force the model to use the tool
            kwargs["tool_choice"] = {
                "type": "tool",
                "name": (
                    json_schema.name if isinstance(json_schema, Schema) else "structured_response"
                ),
            }

            # Add schema explanation to system prompt for better results
            # Create a clean version of the schema for display, omitting unnecessary implementation details
            display_schema = {
                "type": "object",
                "properties": anthropic_schema.get("properties", {}),
                "required": anthropic_schema.get("required", []),
            }

            schema_prefix = f"""Please provide a response that matches exactly this schema:
{json.dumps(display_schema, indent=2)}

Your response must be valid JSON that follows the above schema."""

            if (
                self.cache and context and len(context) > 512
            ):  # Only cache if also a (long) system prompt
                system_content.append(
                    {"type": "text", "text": schema_prefix, "cache_control": {"type": "ephemeral"}}
                )
            else:
                system_content.append({"type": "text", "text": schema_prefix})

        # Add system content if we have any
        if system_content:
            kwargs["system"] = system_content

        # Add the user message
        kwargs["messages"] = [{"role": "user", "content": prompt}]

        completion_data, duration_ms = self._create_message(**kwargs)

        # Extract text or tool output from response
        structured_data = {}
        response_text = ""

        if "content" in completion_data and completion_data["content"]:
            # Check if there's tool use in the response
            tool_use = None
            for content_item in completion_data["content"]:
                if content_item.get("type") == "tool_use":
                    tool_use = content_item
                elif content_item.get("type") == "text":
                    response_text = content_item.get("text", "")

            # If we got structured data via tool use
            if tool_use and "input" in tool_use:
                structured_data = tool_use["input"]
            else:
                # No tool use found, try to extract JSON from text
                try:
                    # Try to extract JSON from the response text
                    import re

                    json_pattern = r"```json\s*([\s\S]*?)\s*```|^\s*({[\s\S]*})\s*$"
                    json_match = re.search(json_pattern, response_text)

                    if json_match:
                        # Use the first match group that isn't None
                        json_str = next(group for group in json_match.groups() if group is not None)
                        structured_data = json.loads(json_str)
                        response_text = ""  # Clear text since we extracted JSON
                    elif json_schema:
                        # If schema was provided but no code block found, try to parse the entire response
                        try:
                            structured_data = json.loads(response_text)
                            response_text = ""  # Clear text since we extracted JSON
                        except json.JSONDecodeError:
                            error_msg = f"Failed to parse JSON response from text: {response_text}"
                            logger.error(error_msg)
                            structured_data = {"error": error_msg}
                except Exception as e:
                    error_msg = f"Failed to parse JSON response: {str(e)}"
                    logger.error(error_msg)
                    structured_data = {"error": error_msg}
        else:
            logger.error("Unexpected response format from Anthropic API")
            structured_data = {"error": "Unexpected response format"}

        usage = LLMUsage.from_api_response(
            {
                "prompt_tokens": completion_data["usage"]["input_tokens"],
                "completion_tokens": completion_data["usage"]["output_tokens"],
                "total_duration": duration_ms,
            },
            model=model,
        )

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
client = AnthropicClient(debug=False)  # Set to True to enable debug logging


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
    Generate a chat response using Anthropic API.

    Args:
        prompt: The main prompt/question
        model: Model to use for generation
        brief: Whether to limit response length
        json_schema: Schema for structured response (if provided, returns JSON)
        context: Optional context to override the default system prompt

    Returns:
        Response containing response_text, structured_data, and usage
        For text responses, structured_data will be empty dict
        For JSON responses, response_text will be empty string
    """
    return client.generate_chat(prompt, model, brief, json_schema, context)


def set_system_prompt(system_prompt: str) -> None:
    """
    Set a new default system prompt for the default client.

    Args:
        system_prompt: New default system prompt to use
    """
    client.set_system_prompt(system_prompt)
