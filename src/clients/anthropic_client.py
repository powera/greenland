#!/usr/bin/python3
"""Client for interacting with Anthropic API."""

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Any, List
from anthropic import Anthropic

import constants
from telemetry import LLMUsage

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Model identifiers
TEST_MODEL = "claude-3-haiku-20240307"
PROD_MODEL = "claude-3-5-sonnet-20240620"
DEFAULT_MODEL = TEST_MODEL
DEFAULT_TIMEOUT = 50

@dataclass
class APIResponse:
    """Container for API response."""
    response_text: str
    usage: LLMUsage

def measure_completion(func):
    """Decorator to measure completion API call duration."""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        duration_ms = (time.time() - start_time) * 1000
        return result, duration_ms
    return wrapper

class AnthropicClient:
    """Client for making requests to Anthropic API."""
    
    def __init__(self, api_key: Optional[str] = None, debug: bool = False):
        """
        Initialize Anthropic client.
        
        Args:
            api_key: Optional API key (will load from file if not provided)
            debug: Enable debug logging
        """
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized AnthropicClient in debug mode")
            
        self.client = Anthropic(
            api_key=api_key or self._load_key()
        )

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
    def _create_completion(self, **kwargs) -> Any:
        """Create completion with timing measurement."""
        return self.client.messages.create(**kwargs)

    def warm_model(self, model: str) -> bool:
        """Model warmup (not needed for Anthropic but kept for API compatibility)."""
        if self.debug:
            logger.debug("Model warmup not required for Anthropic: %s", model)
        return True

    def generate_text(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 1536
    ) -> Tuple[str, LLMUsage]:
        """
        Generate text completion using Anthropic API.
        
        Args:
            prompt: The prompt/instruction for generation
            model: Model identifier to use
            max_tokens: Maximum tokens in response
            
        Returns:
            Tuple of (generated_text, usage_info)
        """
        if self.debug:
            logger.debug("Generating text with model: %s", model)
            logger.debug("Prompt: %s", prompt)
        
        message, duration_ms = self._create_completion(
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": prompt
            }],
            model=model
        )
        
        usage = LLMUsage.from_api_response(
            {
                "prompt_tokens": message.usage.input_tokens,
                "completion_tokens": message.usage.output_tokens,
                "total_duration": duration_ms
            },
            model=model
        )
        
        result = message.content[0].text
        
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
        Generate chat completion using Anthropic API.
        
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
            logger.debug("JSON schema: %s", json.dumps(json_schema, indent=2) if json_schema else None)
        
        system_prompt = context if context else "You are a helpful assistant."
        kwargs = {
            "max_tokens": 256 if brief else 1536,
            "messages": [{
                "role": "user",
                "content": prompt
            }],
            "model": model,
            "system": system_prompt
        }
        
        # Configure for JSON response if schema provided
        if json_schema:
            schema_prompt = f"""Provide a JSON response matching this schema:
{json.dumps(json_schema, indent=2)}"""
            kwargs["messages"][0]["content"] = f"{prompt}\n\n{schema_prompt}"
            kwargs["response_format"] = {"type": "json_object"}
        
        message, duration_ms = self._create_completion(**kwargs)
        
        response_content = message.content[0].text
        usage = LLMUsage.from_api_response(
            {
                "prompt_tokens": message.usage.input_tokens,
                "completion_tokens": message.usage.output_tokens,
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
client = AnthropicClient(debug=False)  # Set to True to enable debug logging

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
