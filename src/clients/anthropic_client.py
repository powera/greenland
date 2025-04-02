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
from clients.types import Response

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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

    def __init__(self, timeout: int = DEFAULT_TIMEOUT, debug: bool = False):
        """Initialize Anthropic client with API key."""
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized AnthropicClient in debug mode")
        self.api_key = self._load_key()
        self.headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

    def _load_key(self) -> str:
        """Load Anthropic API key from file."""
        key_path = os.path.join(constants.KEY_DIR, "anthropic.key")
        try:
            with open(key_path) as f:
                return f.read().strip()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Anthropic API key not found at {key_path}. "
                "Please create this file with your API key."
            )

    @measure_completion
    def _create_message(self, **kwargs) -> Dict:
        """Make direct HTTP request to Anthropic messages endpoint."""
        url = f"{API_BASE}/messages"

        if self.debug:
            logger.debug("Making request to %s", url)
            logger.debug("Request data: %s", json.dumps(kwargs, indent=2))

        response = requests.post(
            url,
            headers=self.headers,
            json=kwargs,
            timeout=self.timeout
        )

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

    def generate_text(self, prompt: str, model: str = DEFAULT_MODEL) -> Response:
        """Generate text completion using Anthropic API."""
        if self.debug:
            logger.debug("Generating text with model: %s", model)
            logger.debug("Prompt: %s", prompt)

        completion_data, duration_ms = self._create_message(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_tokens=1536,
        )

        usage = LLMUsage.from_api_response(
            {
                "prompt_tokens": completion_data["usage"]["input_tokens"],
                "completion_tokens": completion_data["usage"]["output_tokens"],
                "total_duration": duration_ms
            },
            model=model
        )

        # Extract text from the first content block
        result = completion_data["content"][0]["text"]

        if self.debug:
            logger.debug("Generated text: %s", result)
            logger.debug("Usage metrics: %s", usage.to_dict())

        return Response(
            response_text=result,
            structured_data={},
            usage=usage
        )

    def generate_chat(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        brief: bool = False,
        json_schema: Optional[Dict] = None,
        context: Optional[str] = None
    ) -> Response:
        """
        Generate chat completion using Anthropic API.

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
            logger.debug("JSON schema: %s", json.dumps(json_schema, indent=2) if json_schema else None)

        system_prompt = context if context else "You are a helpful assistant."
        kwargs = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "system": system_prompt,
            "max_tokens": 256 if brief else 1536,
        }

        # If JSON schema provided, configure for structured response
        if json_schema:
            # Add the schema as a text prompt
            schema_prompt = f"""Please provide a JSON response matching exactly this schema:
{json.dumps(json_schema, indent=2)}

Your response must be valid JSON that matches the schema above.
Query: {prompt}"""
            kwargs["messages"][0]["content"] = schema_prompt

        completion_data, duration_ms = self._create_message(**kwargs)

        # Extract text from the first content block
        response_content = completion_data["content"][0]["text"]

        usage = LLMUsage.from_api_response(
            {
                "prompt_tokens": completion_data["usage"]["input_tokens"],
                "completion_tokens": completion_data["usage"]["output_tokens"],
                "total_duration": duration_ms
            },
            model=model
        )

        # Parse JSON response if schema was provided
        if json_schema:
            try:
                # Try to extract JSON from the response
                import re
                json_pattern = r'```json\s*([\s\S]*?)\s*```|^\s*({[\s\S]*})\s*$'
                json_match = re.search(json_pattern, response_content)

                if json_match:
                    # Use the first match group that isn't None
                    json_str = next(group for group in json_match.groups() if group is not None)
                else:
                    # If no code block, try to parse the entire response
                    json_str = response_content

                structured_data = json.loads(json_str)
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
            logger.debug("Response text: %s", response_text if response_text else "JSON response")
            logger.debug("Usage metrics: %s", usage.to_dict())

        return Response(
            response_text=response_text,
            structured_data=structured_data,
            usage=usage
        )

# Create default client instance
client = AnthropicClient(debug=False)  # Set to True to enable debug logging

# Expose key functions at module level for API compatibility
def warm_model(model: str) -> bool:
    return client.warm_model(model)

def generate_text(prompt: str, model: str = DEFAULT_MODEL) -> Response:
    """
    Generate text using Anthropic API.

    Returns:
        Response containing response_text, structured_data (empty dict), and usage
    """
    return client.generate_text(prompt, model)

def generate_chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    brief: bool = False,
    json_schema: Optional[Dict] = None,
    context: Optional[str] = None
) -> Response:
    """
    Generate a chat response using Anthropic API.

    Returns:
        Response containing response_text, structured_data, and usage
        For text responses, structured_data will be empty dict
        For JSON responses, response_text will be empty string
    """
    return client.generate_chat(prompt, model, brief, json_schema, context)
