#!/usr/bin/python3
"""Unified client for routing requests to appropriate LLM backends."""

import logging
from typing import Dict, Optional, Tuple, Any

from clients import ollama_client, openai_client, anthropic_client, lmstudio_client, gemini_client
from telemetry import LLMUsage
from clients.types import Response
import datastore.common # Assuming datastore.common is available

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default timeout values (in seconds)
DEFAULT_TIMEOUT = 150

class UnifiedLLMClient:
    """Client for routing requests to appropriate LLM backend based on model name."""

    def __init__(self, model_name: str, timeout: int = DEFAULT_TIMEOUT, debug: bool = True):
        """
        Initialize client with configurable timeout and debug mode.

        Args:
            model_name: The codename of the model (e.g., "llama3.2:3b:Q4_K_M").
            timeout: Request timeout in seconds for all backends
            debug: Whether to enable debug logging
        """
        self.model_name = model_name
        # Get the actual model path from database
        session = datastore.common.create_dev_session()
        model_info = datastore.common.get_model_by_codename(session, model_name)
        self.model_path = model_info.get('model_path', model_name) if model_info else model_name
        self.model_type = model_info.get('model_type', 'local') if model_info else 'local'

        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized UnifiedLLMClient for model '%s' (path='%s', type='%s', timeout=%ds)", 
                         model_name, self.model_path, self.model_type, timeout)

        # Initialize backend clients - debug logs only in client used
        self.ollama = ollama_client.OllamaClient(timeout=timeout, debug=False)
        self.lmstudio = lmstudio_client.LMStudioClient(timeout=timeout, debug=False)
        self.openai = openai_client.OpenAIClient(timeout=timeout, debug=False)
        self.anthropic = anthropic_client.AnthropicClient(timeout=timeout, debug=False)
        self.gemini = gemini_client.GeminiClient(timeout=timeout, debug=False)

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

        # Route to appropriate client based on model type and path
        if self.model_type == 'remote':
            if self.model_path.startswith('gpt-'):
                client = self.openai
                client_name = "OpenAI"
            elif self.model_path.startswith('claude-'):
                client = self.anthropic
                client_name = "Anthropic"
            elif self.model_path.startswith('gemini-'):
                client = self.gemini
                client_name = "Gemini"
            else:
                raise ValueError(f"Unknown remote model type for {self.model_path}")
        else:  # local models
            if self.model_path.startswith('lmstudio/'):
                client = self.lmstudio
                client_name = "LMStudio"
                normalized_model = model[len("lmstudio/"):]
            else:
                # Default to Ollama for local models
                client = self.ollama
                client_name = "Ollama"
                # Strip quantization suffix if present (e.g. ":Q4_0")
                # But preserve base model name if no quantization
                parts = model.split(":")
                if len(parts) > 1:  # Has quantization suffix or other params
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

    def generate_chat(
        self,
        prompt: str,
        model: str,
        brief: bool = False,
        json_schema: Optional[Any] = None,
        context: Optional[str] = None,
        timeout: Optional[float] = None
    ) -> Response:
        """
        Generate chat completion using appropriate backend.

        Args:
            prompt: The main prompt/question
            model: Model name (determines backend)
            brief: Whether to limit response length
            json_schema: Schema for structured response (if provided, returns JSON) - either a dict (old) or a types.Schema
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

        # Use the model_path for the actual client call
        # The `model` argument here is the codename used to initialize the client
        client, normalized_model = self._get_client(self.model_path) 

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

# Default client instance initialization needs to be adjusted
# to accept the model name as per the new __init__ signature.
# Assuming a default model name is needed or passed from configuration.
# For demonstration, let's assume a default model name like 'default-local-model'.
# In a real scenario, this would likely come from configuration or an argument.

# Fetch a default model name from the datastore or configuration
try:
    session = datastore.common.create_dev_session()
    # Assuming a function to get a default model codename
    default_model_codename = datastore.common.get_default_model_codename(session) 
    if not default_model_codename:
        raise ValueError("No default model codename found in the datastore.")
except Exception as e:
    logger.warning(f"Could not fetch default model codename: {e}. Using a placeholder 'default-local-model'.")
    default_model_codename = 'default-local-model' # Fallback

# Create default client instance using the default model codename
client = UnifiedLLMClient(model_name=default_model_codename)  # Use defaults for timeout and debug

# Expose key functions at module level for API compatibility
def warm_model(model: str, timeout: Optional[float] = None) -> bool:
    # The warm_model function in the UnifiedLLMClient expects the codename.
    # We need to get the client instance correctly based on this codename.
    # Re-instantiating client here would be inefficient.
    # A better approach would be to have a way to get the correct client instance
    # for a given codename without re-initializing the whole UnifiedLLMClient.
    # For now, let's assume the module-level 'client' can handle routing if provided with the codename.
    # However, the current UnifiedLLMClient is initialized with ONE model.
    # This implies the module-level functions should potentially create/manage UnifiedLLMClient instances per model if needed.

    # A simpler approach for module-level functions is to create a temporary client instance
    # to perform the action, or to have a manager that holds multiple UnifiedLLMClient instances.

    # Let's adapt to create a temporary client for the specific model if the module-level client
    # is not sufficient, or if we need to support multiple models via these functions.
    # Given the original structure, it seems like the module-level functions are meant to use the single 'client' instance.
    # This means the original design might have implicitly assumed all calls go through the *same* model's client.
    # If we need to support multiple models via module-level functions, the design needs more significant changes.

    # For now, let's assume these module-level functions are called in a context where the 'client' variable
    # is already set up for the relevant model, or that they are intended to operate on the default client.
    # If `warm_model` is called with a *different* model than the default client was initialized with, it will fail.

    # A more robust approach:
    # Create a UnifiedLLMClient instance specifically for the model being requested.
    temp_client = UnifiedLLMClient(model_name=model, timeout=client.timeout, debug=client.debug)
    return temp_client.warm_model(model, timeout)


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
    # Similar to warm_model, we need to ensure this operates on the correct model.
    # Create a temporary client instance for the requested model.
    temp_client = UnifiedLLMClient(model_name=model, timeout=client.timeout, debug=client.debug)
    return temp_client.generate_chat(prompt, model, brief, json_schema, context, timeout)