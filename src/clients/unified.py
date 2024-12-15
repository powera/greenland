#!/usr/bin/python3
"""Unified client for routing requests to appropriate LLM backends."""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Any, List

from clients import ollama_client, openai_client

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
        
        # Model name prefixes for routing
        self.openai_prefixes = ['gpt-', 'text-', 'dalle-']
        
    def _is_openai_model(self, model: str) -> bool:
        """Determine if model is an OpenAI model based on prefix."""
        return any(model.startswith(prefix) for prefix in self.openai_prefixes)
        
    def _route_to_client(self, model: str):
        """Get appropriate client for model."""
        if self._is_openai_model(model):
            if self.debug:
                logger.debug("Routing to OpenAI client for model: %s", model)
            return self.openai
        else:
            if self.debug:
                logger.debug("Routing to Ollama client for model: %s", model)
            return self.ollama

    def warm_model(self, model: str) -> bool:
        """Initialize model for faster first inference."""
        client = self._route_to_client(model)
        return client.warm_model(model)

    def generate_text(self, prompt: str, model: str) -> Tuple[str, Dict]:
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
            
        client = self._route_to_client(model)
        result, usage = client.generate_text(prompt, model)
        
        if self.debug:
            logger.debug("Generated text: %s", result)
            logger.debug("Usage info: %s", usage)
            
        return result, usage

    def generate_chat(
        self,
        prompt: str,
        model: str,
        brief: bool = False,
        json_schema: Optional[Dict] = None,
        context: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any], Dict]:
        """
        Generate chat completion using appropriate backend.
        
        Args:
            prompt: The main prompt/question
            model: Model name (determines backend)
            brief: Whether to limit response length
            json_schema: Schema for structured response
            context: Optional context to include before the prompt
        
        Returns:
            Tuple containing (free_response, structured_response, usage_info)
        """
        if self.debug:
            logger.debug("Generating chat response")
            logger.debug("Model: %s", model)
            logger.debug("Brief mode: %s", brief)
            logger.debug("Context: %s", context)
            logger.debug("JSON schema: %s", json_schema)
            
        client = self._route_to_client(model)
        return client.generate_chat(prompt, model, brief, json_schema, context)

# Create default client instance
client = UnifiedLLMClient(debug=False)  # Set to True to enable debug logging

# Expose key functions at module level for API compatibility
def warm_model(model: str) -> bool:
    return client.warm_model(model)

def generate_text(prompt: str, model: str) -> Tuple[str, Dict]:
    return client.generate_text(prompt, model)

def generate_chat(
    prompt: str,
    model: str,
    brief: bool = False,
    json_schema: Optional[Dict] = None,
    context: Optional[str] = None
) -> Tuple[str, Dict[str, Any], Dict]:
    """
    Generate a chat response using appropriate backend based on model name.
    
    Returns:
        Tuple containing (free_response, structured_response, usage_info)
    """
    return client.generate_chat(prompt, model, brief, json_schema, context)
