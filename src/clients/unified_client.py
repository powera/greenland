#!/usr/bin/python3
"""Unified client for routing requests to appropriate LLM backends."""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Any, List

from clients import ollama_client, openai_client, anthropic_client
from telemetry import LLMUsage

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class Response:
    """Container for response data."""
    response_text: str
    structured_data: Dict[str, Any]
    usage: LLMUsage

class UnifiedLLMClient:
    """Client for routing requests to appropriate LLM backend based on model name."""
    
    def __init__(self, debug: bool = False):
        """Initialize client with optional debug mode."""
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized UnifiedLLMClient in debug mode")
            
        # Initialize backend clients
        self.ollama = ollama_client.OllamaClient(debug=debug)
        self.openai = openai_client.OpenAIClient(debug=debug)
        self.anthropic = anthropic_client.AnthropicClient(debug=debug)
        
        # Model name prefixes for routing
        self.openai_prefixes = ['gpt-']
        self.anthropic_prefixes = ['claude-']
        
    def _get_client(self, model: str):
        """Get appropriate client for model."""
        if any(model.startswith(prefix) for prefix in self.openai_prefixes):
            if self.debug:
                logger.debug("Routing to OpenAI client for model: %s", model)
            return self.openai
        elif any(model.startswith(prefix) for prefix in self.anthropic_prefixes):
            if self.debug:
                logger.debug("Routing to Anthropic client for model: %s", model)
            return self.anthropic
        else:
            if self.debug:
                logger.debug("Routing to Ollama client for model: %s", model)
            return self.ollama

    def warm_model(self, model: str) -> bool:
        """Initialize model for faster first inference."""
        client = self._get_client(model)
        return client.warm_model(model)

    def generate_text(self, prompt: str, model: str) -> Tuple[str, LLMUsage]:
        """
        Generate text using appropriate backend.
        
        Args:
            prompt: Text prompt for generation
            model: Model name (determines backend)
            
        Returns:
            Tuple containing (generated_text, usage_info)
        """
        if self.debug:
            logger.debug("Generating text with model: %s", model)
            logger.debug("Prompt: %s", prompt)
            
        client = self._get_client(model)
        result, usage = client.generate_text(prompt, model)
        
        if self.debug:
            logger.debug("Generated text: %s", result)
            logger.debug("Usage metrics: %s", usage.to_dict())
            
        return result, usage

    def generate_chat(
        self,
        prompt: str,
        model: str,
        brief: bool = False,
        json_schema: Optional[Dict] = None,
        context: Optional[str] = None
    ) -> Response:
        """
        Generate chat completion using appropriate backend.
        
        Args:
            prompt: The main prompt/question
            model: Model name (determines backend)
            brief: Whether to limit response length
            json_schema: Schema for structured response (if provided, returns JSON)
            context: Optional context to include before the prompt
        
        Returns:
            Response containing response_text, structured_data, and usage_info
            For text responses, structured_data will be empty dict
            For JSON responses, response_text will be empty string
        """
        if self.debug:
            logger.debug("Generating chat response")
            logger.debug("Model: %s", model)
            logger.debug("Brief mode: %s", brief)
            logger.debug("Context: %s", context)
            logger.debug("JSON schema: %s", json_schema)
            
        client = self._get_client(model)
        response_text, structured_data, usage = client.generate_chat(
            prompt=prompt,
            model=model,
            brief=brief,
            json_schema=json_schema,
            context=context
        )
        
        if self.debug:
            logger.debug("Chat response: %s", response_text if response_text else "JSON response")
            logger.debug("Usage metrics: %s", usage.to_dict())
            
        return Response(
            response_text=response_text,
            structured_data=structured_data,
            usage=usage
        )

# Create default client instance
client = UnifiedLLMClient(debug=False)  # Set to True to enable debug logging

# Expose key functions at module level for API compatibility
def warm_model(model: str) -> bool:
    return client.warm_model(model)

def generate_text(prompt: str, model: str) -> Tuple[str, LLMUsage]:
    return client.generate_text(prompt, model)

def generate_chat(
    prompt: str,
    model: str,
    brief: bool = False,
    json_schema: Optional[Dict] = None,
    context: Optional[str] = None
) -> Tuple[str, Dict[str, Any], LLMUsage]:
    """
    Generate a chat response using appropriate backend based on model name.
    
    Returns:
        Tuple containing (response_text, structured_data, usage_info)
        For text responses, structured_data will be empty dict
        For JSON responses, response_text will be empty string
    """
    response = client.generate_chat(prompt, model, brief, json_schema, context)
    return response.response_text, response.structured_data, response.usage
