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
class TwoPhaseResponse:
    """Container for both free-form and structured responses."""
    free_response: str
    structured_response: Dict[str, Any]
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
    """Client for making requests to Anthropic API with two-phase responses."""
    
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
    ) -> TwoPhaseResponse:
        """
        Generate two-phase chat completion using Anthropic API.
        
        Args:
            prompt: The main prompt/question
            model: Model to use for generation
            brief: Whether to limit response length
            json_schema: Schema for structured response
            context: Optional context to include before the prompt
        
        Returns:
            TwoPhaseResponse containing both free-form and structured responses
        """
        if self.debug:
            logger.debug("Generating chat response")
            logger.debug("Model: %s", model)
            logger.debug("Brief mode: %s", brief)
            logger.debug("Context: %s", context)
            logger.debug("JSON schema: %s", json.dumps(json_schema, indent=2) if json_schema else None)
        
        # Phase 1: Get free-form response
        system_prompt = context if context else "You are a helpful assistant."
        
        message, duration_ms = self._create_completion(
            max_tokens=256 if brief else 1536,
            messages=[{
                "role": "user",
                "content": prompt
            }],
            model=model,
            system=system_prompt
        )
        
        free_response = message.content[0].text
        free_usage = LLMUsage.from_api_response(
            {
                "prompt_tokens": message.usage.input_tokens,
                "completion_tokens": message.usage.output_tokens,
                "total_duration": duration_ms
            },
            model=model
        )
        
        if self.debug:
            logger.debug("Phase 1 response: %s", free_response)
            logger.debug("Phase 1 usage metrics: %s", free_usage.to_dict())
        
        # Phase 2: Get structured response if schema provided
        if json_schema:
            structure_prompt = """Based on the previous response, provide a structured response that matches this schema:
            """ + json.dumps(json_schema, indent=2)
            
            message, duration_ms = self._create_completion(
                max_tokens=1536,
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": free_response},
                    {"role": "user", "content": structure_prompt}
                ],
                model=model,
                system=system_prompt,
                response_format={"type": "json_object"}
            )
            
            json_response = message.content[0].text
            json_usage = LLMUsage.from_api_response(
                {
                    "prompt_tokens": message.usage.input_tokens,
                    "completion_tokens": message.usage.output_tokens,
                    "total_duration": duration_ms
                },
                model=model
            )
            
            if self.debug:
                logger.debug("Phase 2 JSON response: %s", json_response)
                logger.debug("Phase 2 usage metrics: %s", json_usage.to_dict())
            
            try:
                structured_response = json.loads(json_response)
            except json.JSONDecodeError:
                error_msg = f"Failed to parse JSON response: {json_response}"
                logger.error(error_msg)
                structured_response = {"error": error_msg}
        else:
            structured_response = {}
            json_usage = LLMUsage(tokens_in=0, tokens_out=0, cost=0.0, total_msec=0)
        
        # Combine usage from both phases
        total_usage = free_usage.combine(json_usage)
        
        if self.debug:
            logger.debug("Total usage metrics: %s", total_usage.to_dict())
        
        return TwoPhaseResponse(
            free_response=free_response,
            structured_response=structured_response,
            usage=total_usage
        )

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
    Generate a two-phase chat response.
    
    Returns:
        Tuple containing (free_response, structured_response, usage_info)
    """
    response = client.generate_chat(prompt, model, brief, json_schema, context)
    return response.free_response, response.structured_response, response.usage
