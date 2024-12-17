#!/usr/bin/python3
"""Client for interacting with OpenAI API with two-phase responses using direct HTTP requests."""

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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Model identifiers
TEST_MODEL = "gpt-4o-mini-2024-07-18"
PROD_MODEL = "gpt-4o-2024-11-20"
DEFAULT_MODEL = TEST_MODEL
DEFAULT_TIMEOUT = 50
API_BASE = "https://api.openai.com/v1"

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

class OpenAIClient:
    """Client for making direct HTTP requests to OpenAI API with two-phase responses."""
    
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
    ) -> TwoPhaseResponse:
        """
        Generate two-phase chat completion using OpenAI API.
        
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
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})
        
        completion_data, duration_ms = self._create_completion(
            model=model,
            messages=messages,
            max_tokens=256 if brief else 1536,
            temperature=0.45,
        )
        
        free_response = completion_data["choices"][0]["message"]["content"]
        free_usage = LLMUsage.from_api_response(
            {
                "prompt_tokens": completion_data["usage"]["prompt_tokens"],
                "completion_tokens": completion_data["usage"]["completion_tokens"],
                "total_duration": duration_ms
            },
            model=model
        )
        
        if self.debug:
            logger.debug("Phase 1 response: %s", free_response)
            logger.debug("Phase 1 usage metrics: %s", free_usage.to_dict())
        
        # Phase 2: Get structured response if schema provided
        if json_schema:
            structure_prompt = "Based on the previous response to the prompt, provide a structured response that matches the schema."
            
            if self.debug:
                logger.debug("Phase 2 structure prompt: %s", structure_prompt)
            
            completion_data, duration_ms = self._create_completion(
                model=model,
                messages=messages + [
                    {"role": "assistant", "content": free_response},
                    {"role": "user", "content": structure_prompt}
                ],
                max_tokens=1536,
                temperature=0.15,
                response_format={"type": "json_object", "schema": json_schema}
            )
            
            json_response = completion_data["choices"][0]["message"]["content"]
            json_usage = LLMUsage.from_api_response(
                {
                    "prompt_tokens": completion_data["usage"]["prompt_tokens"],
                    "completion_tokens": completion_data["usage"]["completion_tokens"],
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
    Generate a two-phase chat response.
    
    Returns:
        Tuple containing (free_response, structured_response, usage_info)
    """
    response = client.generate_chat(prompt, model, brief, json_schema, context)
    return response.free_response, response.structured_response, response.usage
