#!/usr/bin/python3
"""Client for interacting with OpenAI API with two-phase responses."""

import json
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union, Any, List
import tiktoken
from openai import OpenAI
import os
import constants

# Configure logging with DEBUG level option
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TEST_MODEL = "gpt-4o-mini-2024-07-18"
PROD_MODEL = "gpt-4o-2024-11-20"
DEFAULT_MODEL = TEST_MODEL
DEFAULT_TIMEOUT = 50

@dataclass
class UsageInfo:
    """Tracks token usage and cost information."""
    tokens_in: int
    tokens_out: int
    total_msec: float
    cost: float

    @classmethod
    def from_completion(cls, completion, model: str = "gpt-4o-mini") -> 'UsageInfo':
        """Create UsageInfo from OpenAI completion usage data."""
        costs = {
            "gpt-4o-mini": {"input": .15, "output": .6},
            "gpt-4o": {"input": 2.5, "output": 10},
        }
        
        model_base = model.split("-")[0:2]
        model_costs = costs.get("-".join(model_base), costs["gpt-4o-mini"])
        
        cost = (completion.usage.prompt_tokens * (model_costs["input"] / 1000000) +
                completion.usage.completion_tokens * (model_costs["output"] / 1000000))
                
        return cls(
            tokens_in=completion.usage.prompt_tokens,
            tokens_out=completion.usage.completion_tokens,
            total_msec=completion.usage.total_tokens * 10,  # Rough estimate of processing time
            cost=cost
        )

    def combine(self, other: 'UsageInfo') -> 'UsageInfo':
        """Combine usage information from multiple responses."""
        return UsageInfo(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            total_msec=self.total_msec + other.total_msec,
            cost=self.cost + other.cost
        )

@dataclass
class TwoPhaseResponse:
    """Container for both free-form and structured responses."""
    free_response: str
    structured_response: Dict[str, Any]
    usage: UsageInfo

class OpenAIClient:
    """Client for making requests to OpenAI API with two-phase responses."""
    
    def __init__(self, timeout: int = DEFAULT_TIMEOUT, debug: bool = False):
        """Initialize OpenAI client with API key."""
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized OpenAIClient in debug mode")
        self.client = OpenAI(api_key=self._load_key())
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def _load_key(self) -> str:
        """Load OpenAI API key from file."""
        key_path = os.path.join(constants.KEY_DIR, "openai.key")
        with open(key_path) as f:
            return f.read().strip()

    def warm_model(self, model: str) -> bool:
        """Simulate model warmup (not needed for OpenAI but kept for API compatibility)."""
        if self.debug:
            logger.debug("Model warmup not required for OpenAI: %s", model)
        return True

    def generate_text(self, prompt: str, model: str = DEFAULT_MODEL) -> Tuple[str, UsageInfo]:
        """Generate text completion using OpenAI API."""
        if self.debug:
            logger.debug("Generating text with model: %s", model)
            logger.debug("Prompt: %s", prompt)
            
        completion = self.client.chat.completions.create(
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
        
        usage = UsageInfo.from_completion(completion, model)
        result = completion.choices[0].message.content
        
        if self.debug:
            logger.debug("Generated text: %s", result)
            logger.debug("Usage info: %s", vars(usage))
                
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
        
        completion = self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=256 if brief else 1536,
            temperature=0.45,
        )
        
        free_response = completion.choices[0].message.content
        free_usage = UsageInfo.from_completion(completion, model)
        
        if self.debug:
            logger.debug("Phase 1 response: %s", free_response)
            logger.debug("Phase 1 usage: %s", vars(free_usage))
        
        # Phase 2: Get structured response if schema provided
        if json_schema:
            structure_prompt = "Based on the previous response to the prompt, provide a structured response that matches the schema."
            
            if self.debug:
                logger.debug("Phase 2 structure prompt: %s", structure_prompt)
            
            completion = self.client.chat.completions.create(
                model=model,
                messages=messages + [
                    {"role": "assistant", "content": free_response},
                    {"role": "user", "content": structure_prompt}
                ],
                max_tokens=1536,
                temperature=0.15,
                response_format={"type": "json_object", "schema": json_schema}
            )
            
            json_response = completion.choices[0].message.content
            json_usage = UsageInfo.from_completion(completion, model)
            
            if self.debug:
                logger.debug("Phase 2 JSON response: %s", json_response)
                logger.debug("Phase 2 usage: %s", vars(json_usage))
            
            try:
                structured_response = json.loads(json_response)
            except json.JSONDecodeError:
                error_msg = f"Failed to parse JSON response: {json_response}"
                logger.error(error_msg)
                structured_response = {"error": error_msg}
        else:
            structured_response = {}
            json_usage = UsageInfo(0, 0, 0, 0)
        
        # Combine usage from both phases
        total_usage = free_usage.combine(json_usage)
        
        if self.debug:
            logger.debug("Total usage: %s", vars(total_usage))
        
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

def generate_text(prompt: str, model: str = DEFAULT_MODEL) -> Tuple[str, Dict]:
    result, usage = client.generate_text(prompt, model)
    return result, vars(usage)

def generate_chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    brief: bool = False,
    json_schema: Optional[Dict] = None,
    context: Optional[str] = None
) -> Tuple[str, Dict[str, Any], Dict]:
    """
    Generate a two-phase chat response.
    
    Returns:
        Tuple containing (free_response, structured_response, usage_info)
    """
    response = client.generate_chat(prompt, model, brief, json_schema, context)
    return response.free_response, response.structured_response, vars(response.usage)
