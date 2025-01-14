#!/usr/bin/python3
"""Client for interacting with OpenAI API using direct HTTP requests."""

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Any, List

import requests
import tiktoken

import constants
from telemetry import LLMUsage
from clients.types import Response

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Model identifiers
TEST_MODEL = "gpt-4o-mini-2024-07-18"
PROD_MODEL = "gpt-4o-2024-11-20"
DEFAULT_MODEL = TEST_MODEL
DEFAULT_TIMEOUT = 50
API_BASE = "https://api.openai.com/v1"

def measure_completion(func):
    """Decorator to measure completion API call duration."""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        duration_ms = (time.time() - start_time) * 1000
        return result, duration_ms
    return wrapper

class OpenAIClient:
    """Client for making direct HTTP requests to OpenAI API."""
    
    def __init__(self, timeout: int = DEFAULT_TIMEOUT, debug: bool = False):
        """Initialize OpenAI client with API key."""
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized OpenAIClient in debug mode")
        self.api_key = self._load_key()
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def _load_key(self) -> str:
        """Load OpenAI API key from file."""
        key_path = os.path.join(constants.KEY_DIR, "openai.key")
        with open(key_path) as f:
            return f.read().strip()

    @measure_completion
    def _create_completion(self, **kwargs) -> Dict:
        """Make direct HTTP request to OpenAI chat completions endpoint."""
        url = f"{API_BASE}/chat/completions"
        
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
        """Simulate model warmup (not needed for OpenAI but kept for API compatibility)."""
        if self.debug:
            logger.debug("Model warmup not required for OpenAI: %s", model)
        return True

    def generate_text(self, prompt: str, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
        """Generate text completion using OpenAI API."""
        if self.debug:
            logger.debug("Generating text with model: %s", model)
            logger.debug("Prompt: %s", prompt)
            
        completion_data, duration_ms = self._create_completion(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_tokens=1536,
            temperature=0.15,
        )
        
        usage = LLMUsage.from_api_response(
            {
                "prompt_tokens": completion_data["usage"]["prompt_tokens"],
                "completion_tokens": completion_data["usage"]["completion_tokens"],
                "total_duration": duration_ms
            },
            model=model
        )
        
        result = completion_data["choices"][0]["message"]["content"]
        
        if self.debug:
            logger.debug("Generated text: %s", result)
            logger.debug("Usage metrics: %s", usage.to_dict())
                
        return result, usage

    def generate_chat(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        brief: bool = False,
        json_schema: Optional[Dict] = None,
        context: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any], LLMUsage]:
        """
        Generate chat completion using OpenAI API.
        
        Args:
            prompt: The main prompt/question
            model: Model to use for generation
            brief: Whether to limit response length
            json_schema: Schema for structured response (if provided, returns JSON)
            context: Optional context to include before the prompt
        
        Returns:
            Tuple containing (response_text, structured_data, usage_info)
            For text responses, structured_data will be empty dict
            For JSON responses, response_text will be empty string
        """
        if self.debug:
            logger.debug("Generating chat response")
            logger.debug("Model: %s", model)
            logger.debug("Brief mode: %s", brief)
            logger.debug("Context: %s", context)
            logger.debug("JSON schema: %s", json_dumps(json_schema, indent=2) if json_schema else None)
        
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "model": model,
            "messages": messages,
            "max_tokens": 256 if brief else 1536,
            "temperature": 0.45,
        }
        
        # If JSON schema provided, configure for structured response
        if json_schema:
            # Remove any minimum/maximum constraints from schema properties
            clean_schema = json_schema.copy()
            if "properties" in clean_schema:
                for prop in clean_schema["properties"].values():
                    if isinstance(prop, dict):
                        prop.pop("minimum", None)
                        prop.pop("maximum", None)
            
            clean_schema["additionalProperties"] = False
            kwargs["temperature"] = 0.15  # Lower temperature for structured output
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "Details",
                    "description": "N/A",
                    "strict": True,
                    "schema": clean_schema
                }
            }
        
        completion_data, duration_ms = self._create_completion(**kwargs)
        
        response_content = completion_data["choices"][0]["message"]["content"]
        usage = LLMUsage.from_api_response(
            {
                "prompt_tokens": completion_data["usage"]["prompt_tokens"],
                "completion_tokens": completion_data["usage"]["completion_tokens"],
                "total_duration": duration_ms
            },
            model=model
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
            logger.debug("Response text: %s", response_text if response_text else "JSON response")
            logger.debug("Usage metrics: %s", usage.to_dict())
        
        return response_text, structured_data, usage

# Create default client instance
client = OpenAIClient(debug=False)  # Set to True to enable debug logging

# Expose key functions at module level for API compatibility
def warm_model(model: str) -> bool:
    return client.warm_model(model)

def generate_text(prompt: str, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
    return client.generate_text(prompt, model)

def generate_chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    brief: bool = False,
    json_schema: Optional[Dict] = None,
    context: Optional[str] = None
) -> Tuple[str, Dict[str, Any], LLMUsage]:
    """
    Generate a chat response, either text or JSON.
    
    Returns:
        Tuple containing (response_text, structured_data, usage_info)
        For text responses, structured_data will be empty dict
        For JSON responses, response_text will be empty string
    """
    return client.generate_chat(prompt, model, brief, json_schema, context)
