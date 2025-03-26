#!/usr/bin/python3
"""Unified client for routing requests to appropriate LLM backends."""

import logging
from typing import Dict, Optional, Tuple, Any

from clients import ollama_client, openai_client
from telemetry import LLMUsage
from clients.types import Response

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default timeout values (in seconds)
DEFAULT_TIMEOUT = 50

class UnifiedLLMClient:
    """Client for routing requests to appropriate LLM backend based on model name."""
    
    def __init__(self, timeout: int = DEFAULT_TIMEOUT, debug: bool = False):
        """
        Initialize client with configurable timeout and debug mode.
        
        Args:
            timeout: Request timeout in seconds for all backends
            debug: Whether to enable debug logging
        """
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized UnifiedLLMClient (timeout=%ds)", timeout)
            
        # Initialize backend clients - debug logs only in client used
        self.ollama = ollama_client.OllamaClient(timeout=timeout, debug=False)
        self.openai = openai_client.OpenAIClient(timeout=timeout, debug=False)
        #self.anthropic = anthropic_client.AnthropicClient(timeout=timeout, debug=False)
        
        # Model name prefixes for routing
        self.openai_prefixes = ['gpt-']
        self.anthropic_prefixes = ['claude-']
        
    def _get_client(self, model: str) -> Tuple[Any, str]:
        """
        Get appropriate client for model and normalize model name.
        
        Args:
            model: Original model name/identifier
            
        Returns:
            Tuple of (client, normalized_model_name)
        """
        client = None
        client_name = None
        normalized_model = model
        
        if any(model.startswith(prefix) for prefix in self.openai_prefixes):
            client = self.openai
            client_name = "OpenAI"
        elif any(model.startswith(prefix) for prefix in self.anthropic_prefixes):
            client = self.anthropic
            client_name = "Anthropic"
        else:
            client = self.ollama
            client_name = "Ollama"
            # Strip quantization suffix if present (e.g. ":Q4_0")
            # But preserve base model name if no quantization
            parts = model.split(":")
            if len(parts) > 2:  # Has quantization suffix
                normalized_model = ":".join(parts[:-1])
            
        if self.debug:
            if normalized_model != model:
                logger.debug("Using %s client for model: %s (normalized from %s)", 
                           client_name, normalized_model, model)
            else:
                logger.debug("Using %s client for model: %s", client_name, model)
            client.debug = True
            
        return client, normalized_model

    def warm_model(self, model: str, timeout: Optional[float] = None) -> bool:
        """Initialize model for faster first inference."""
        client, normalized_model = self._get_client(model)
        if self.debug:
            logger.debug("Warming up model: %s", normalized_model)
        return client.warm_model(normalized_model)

    def generate_text(self, prompt: str, model: str, timeout: Optional[float] = None) -> Response:
        """
        Generate text using appropriate backend.
        
        Args:
            prompt: Text prompt for generation
            model: Model name (determines backend)
            timeout: Optional timeout override in seconds
            
        Returns:
            Response data class containing response_text, structured_data, and usage
            
        Raises:
            TimeoutError: If request exceeds configured timeout
            ConnectionError: If connection to backend fails
            RuntimeError: For other request failures
        """
        if self.debug:
            logger.debug("Text generation request: model=%s", model)
            
        client, normalized_model = self._get_client(model)
        try:
            result = client.generate_text(prompt, normalized_model)
            
            if self.debug:
                logger.debug("Generation complete: %d chars, %d tokens", 
                            len(result.response_text), result.usage.total_tokens)
                            
            return result
            
        except Exception as e:
            logger.error("Text generation failed: %s", str(e))
            raise

    def generate_chat(
        self,
        prompt: str,
        model: str,
        brief: bool = False,
        json_schema: Optional[Dict] = None,
        context: Optional[str] = None,
        timeout: Optional[float] = None
    ) -> Response:
        """
        Generate chat completion using appropriate backend.
        
        Args:
            prompt: The main prompt/question
            model: Model name (determines backend)
            brief: Whether to limit response length
            json_schema: Schema for structured response (if provided, returns JSON)
            context: Optional context to include before the prompt
            timeout: Optional timeout override in seconds
        
        Returns:
            Response containing response_text, structured_data, and usage
            For text responses, structured_data will be empty dict
            For JSON responses, response_text will be empty string
            
        Raises:
            TimeoutError: If request exceeds configured timeout  
            ConnectionError: If connection to backend fails
            RuntimeError: For other request failures
        """
        if self.debug:
            logger.debug("Chat request: model=%s, brief=%s, schema=%s", 
                        model, brief, bool(json_schema))
            
        client, normalized_model = self._get_client(model)
        try:
            result = client.generate_chat(
                prompt=prompt,
                model=normalized_model,
                brief=brief,
                json_schema=json_schema,
                context=context
            )
            
            if self.debug:
                response_type = "JSON" if json_schema else "text"
                logger.debug("Chat complete: %s response, %d tokens", 
                            response_type, result.usage.total_tokens)
                
            return result
            
        except Exception as e:
            logger.error("Chat generation failed: %s", str(e))
            raise

# Create default client instance
client = UnifiedLLMClient()  # Use defaults for timeout and debug

# Expose key functions at module level for API compatibility
def warm_model(model: str, timeout: Optional[float] = None) -> bool:
    return client.warm_model(model, timeout)

def generate_text(prompt: str, model: str, timeout: Optional[float] = None) -> Response:
    """
    Generate text using appropriate backend based on model name.
    
    Returns:
        Response data class containing response_text, structured_data, and usage
    """
    return client.generate_text(prompt, model, timeout)

def generate_chat(
    prompt: str,
    model: str,
    brief: bool = False,
    json_schema: Optional[Dict] = None,
    context: Optional[str] = None,
    timeout: Optional[float] = None
) -> Response:
    """
    Generate a chat response using appropriate backend based on model name.
    
    Returns:
        Response data class containing response_text, structured_data, and usage
        For text responses, structured_data will be empty dict
        For JSON responses, response_text will be empty string
    """
    return client.generate_chat(prompt, model, brief, json_schema, context, timeout)
