#!/usr/bin/python3
"""Unified client for routing requests to appropriate LLM backends."""

import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Tuple, Union

import benchmarks.datastore.common  # Assuming datastore.common is available
from clients import gemini_client, lmstudio_client, ollama_client
from clients.anthropic import client as anthropic_client
from clients.openai import client as openai_client
from clients.types import Response, Schema
from util.telemetry import LLMUsage

if TYPE_CHECKING:
    from storage.backend.config import DataSourceConfig

# Optional metrics callback - can be set by applications (e.g., Barsukas) to record LLM metrics
# Signature: (backend: str, model: str, duration_seconds: float, status: str,
#             tokens_in: int, tokens_out: int) -> None
_metrics_callback: Optional[Callable[[str, str, float, str, int, int], None]] = None


def set_llm_metrics_callback(
    callback: Optional[Callable[[str, str, float, str, int, int], None]],
) -> None:
    """Set a callback function to record LLM call metrics.

    This allows applications like Barsukas to inject their metrics recording
    without creating a hard dependency.

    Args:
        callback: Function with signature (backend, model, duration_seconds, status,
                 tokens_in, tokens_out) -> None, or None to disable metrics.
    """
    global _metrics_callback
    _metrics_callback = callback


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Default timeout values (in seconds)
DEFAULT_TIMEOUT = 150


class UnifiedLLMClient:
    """Client for routing requests to appropriate LLM backend based on model name."""

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        debug: bool = True,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        google_api_key: Optional[str] = None,
    ):
        """
        Initialize client with configurable timeout and debug mode.

        Args:
            timeout: Request timeout in seconds for all backends
            debug: Whether to enable debug logging
            openai_api_key: Optional API key for OpenAI (avoids file-based key loading)
            anthropic_api_key: Optional API key for Anthropic (avoids file-based key loading)
            google_api_key: Optional API key for Google/Gemini (avoids file-based key loading)
        """
        self.timeout = timeout
        self.debug = debug
        self.default_model: Optional[str] = None
        self._model_resolution_cache: Dict[str, Tuple[str, str, Optional[str]]] = {}
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized UnifiedLLMClient (timeout=%ds)", timeout)

        # Initialize backend clients - debug logs only in client used
        # Pass API keys if provided (for API server use)
        self.ollama = ollama_client.OllamaClient(timeout=timeout, debug=False)
        self.lmstudio = lmstudio_client.LMStudioClient(timeout=timeout, debug=False)
        self.openai = openai_client.OpenAIClient(
            timeout=timeout, debug=False, api_key=openai_api_key
        )
        self.anthropic = anthropic_client.AnthropicClient(
            timeout=timeout, debug=False, api_key=anthropic_api_key
        )
        self.gemini = gemini_client.GeminiClient(
            timeout=timeout, debug=False, api_key=google_api_key
        )

    @classmethod
    def from_config(
        cls, config: "DataSourceConfig", timeout: int = DEFAULT_TIMEOUT
    ) -> "UnifiedLLMClient":
        """
        Create a UnifiedLLMClient from a DataSourceConfig.

        This extracts the model, debug settings, and optional API keys from the config.
        The model parameter from config will be used when making LLM requests.
        API keys from config (if provided) will be passed to the underlying clients,
        avoiding file-based key loading. This is useful for API server use where
        keys come from request parameters.

        Args:
            config: DataSourceConfig containing model, debug, API keys, and other configuration
            timeout: Request timeout in seconds for all backends

        Returns:
            UnifiedLLMClient instance with model, debug, and API keys from config

        Example:
            config = get_data_source_config(args)
            client = UnifiedLLMClient.from_config(config)
            # Client now has config.model and config.debug settings

            # For API server use with runtime API keys:
            config = DataSourceConfig(
                model="gpt-5-mini",
                openai_api_key="sk-...",
            )
            client = UnifiedLLMClient.from_config(config)
        """
        # Use debug setting from config
        debug = config.debug if hasattr(config, "debug") else False

        # Extract optional API keys from config
        openai_api_key = getattr(config, "openai_api_key", None)
        anthropic_api_key = getattr(config, "anthropic_api_key", None)
        google_api_key = getattr(config, "google_api_key", None)

        client = cls(
            timeout=timeout,
            debug=debug,
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            google_api_key=google_api_key,
        )
        # Store the model from config for use in requests
        # This allows agents to just call client methods without passing model each time
        client.default_model = config.model
        return client

    def _get_client(self, model: str) -> Tuple[
        Union[
            ollama_client.OllamaClient,
            lmstudio_client.LMStudioClient,
            openai_client.OpenAIClient,
            anthropic_client.AnthropicClient,
            gemini_client.GeminiClient,
        ],
        str,
        Optional[str],
    ]:
        """
        Get appropriate client for model and normalize model name.

        Args:
            model: Original model name/identifier (codename)

        Returns:
            Tuple of (client, normalized_model_name, expected_response_model_name)
        """
        client: Union[
            ollama_client.OllamaClient,
            lmstudio_client.LMStudioClient,
            openai_client.OpenAIClient,
            anthropic_client.AnthropicClient,
            gemini_client.GeminiClient,
            None,
        ] = None
        client_name: Optional[str] = None
        normalized_model = model
        expected_response_model: Optional[str] = None

        # Fast path: reuse previous resolution for this model codename.
        cached = self._model_resolution_cache.get(model)
        if cached is not None:
            cached_client_name, cached_normalized_model, cached_expected_response_model = cached
            if cached_client_name == "openai":
                return self.openai, cached_normalized_model, cached_expected_response_model
            if cached_client_name == "anthropic":
                return self.anthropic, cached_normalized_model, cached_expected_response_model
            if cached_client_name == "gemini":
                return self.gemini, cached_normalized_model, cached_expected_response_model
            if cached_client_name == "ollama":
                return self.ollama, cached_normalized_model, cached_expected_response_model
            if cached_client_name == "lmstudio":
                return self.lmstudio, cached_normalized_model, cached_expected_response_model

        # Check if this is a commercial API model first (skip database lookup)
        # These models can be routed directly based on their name
        # Exception: gpt-oss models should use database lookup
        if model.startswith("gpt-") and not model.startswith("gpt-oss"):
            client = self.openai
            client_name = "OpenAI"
            normalized_model = model
        elif model.startswith("claude-"):
            client = self.anthropic
            client_name = "Anthropic"
            normalized_model = model
        elif model.startswith("gemini-"):
            client = self.gemini
            client_name = "Gemini"
            normalized_model = model
        else:
            # For all other models, get the actual model path from database
            session = benchmarks.datastore.common.create_dev_session()
            try:
                model_info = benchmarks.datastore.common.get_model_by_codename(session, model)
            finally:
                session.close()
            if not model_info:
                raise ValueError(f"Model '{model}' not found in database")

            model_path = model_info.get("model_path")
            model_type = model_info.get("model_type")
            lmstudio_model_name = model_info.get("lmstudio_model_name")

            if not model_path or not model_type:
                raise ValueError(
                    f"Model '{model}' has incomplete configuration (path={model_path}, type={model_type})"
                )

            # Route to appropriate client based on model type and path
            if model_type == "remote":
                raise ValueError(f"Unknown remote model type for {model_path}")
            else:  # local models
                if model_path.startswith("lmstudio/"):
                    client = self.lmstudio
                    client_name = "LMStudio"
                    normalized_model = model_path[len("lmstudio/") :]
                    expected_response_model = (
                        lmstudio_model_name
                        if isinstance(lmstudio_model_name, str) and lmstudio_model_name
                        else None
                    )
                else:
                    # Default to Ollama for local models
                    client = self.ollama
                    client_name = "Ollama"
                    normalized_model = model_path
                    # Strip quantization suffix if present (e.g. ":Q4_0")
                    # But preserve base model name if no quantization
                    parts = model_path.split(":")
                    if len(parts) > 1:  # Has quantization suffix or other params
                        normalized_model = ":".join(parts[:-1])

        if client is None:
            raise ValueError(f"Could not determine client for model: {model}")

        backend_name = self._get_backend_name(client)
        self._model_resolution_cache[model] = (
            backend_name,
            normalized_model,
            expected_response_model,
        )

        return client, normalized_model, expected_response_model

    def _get_backend_name(
        self,
        client: Union[
            ollama_client.OllamaClient,
            lmstudio_client.LMStudioClient,
            openai_client.OpenAIClient,
            anthropic_client.AnthropicClient,
            gemini_client.GeminiClient,
        ],
    ) -> str:
        """Get the backend name for a client instance.

        Args:
            client: The LLM client instance.

        Returns:
            Backend name string (e.g., "openai", "anthropic", "gemini", "ollama", "lmstudio").
        """
        if isinstance(client, openai_client.OpenAIClient):
            return "openai"
        elif isinstance(client, anthropic_client.AnthropicClient):
            return "anthropic"
        elif isinstance(client, gemini_client.GeminiClient):
            return "gemini"
        elif isinstance(client, ollama_client.OllamaClient):
            return "ollama"
        elif isinstance(client, lmstudio_client.LMStudioClient):
            return "lmstudio"
        else:
            return "unknown"

    def warm_model(self, model: str, timeout: Optional[float] = None) -> bool:
        """Initialize model for faster first inference."""
        client, normalized_model, expected_response_model = self._get_client(model)
        if self.debug:
            logger.debug("Warming up model: %s", normalized_model)
        if isinstance(client, lmstudio_client.LMStudioClient):
            # Use lmstudio_model_name (expected_response_model) as the bare id for both
            # state polling and the load POST — it matches /api/v0/models "id" field.
            poll_name = expected_response_model or normalized_model
            return client.warm_model(poll_name, load_name=poll_name)
        return client.warm_model(normalized_model)

    def unload_model(self, model: str) -> bool:
        """Unload model from memory (LMStudio only; no-op for other backends)."""
        client, normalized_model, expected_response_model = self._get_client(model)
        if isinstance(client, lmstudio_client.LMStudioClient):
            if self.debug:
                logger.debug("Unloading model: %s", normalized_model)
            return client.unload_model(normalized_model)
        return True

    def generate_chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        brief: bool = False,
        json_schema: Optional[Union[Dict[str, Any], Schema]] = None,
        context: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Response:
        """
        Generate chat completion using appropriate backend.

        Args:
            prompt: The main prompt/question
            model: Model name (determines backend). If not provided, uses default_model from config.
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
            ValueError: If model is not provided and no default_model is set
        """
        # Use default model if not provided
        if model is None:
            if not hasattr(self, "default_model") or self.default_model is None:
                raise ValueError("No model specified and no default_model configured")
            model = self.default_model

        if self.debug:
            logger.debug(
                "Chat request: model=%s, brief=%s, schema=%s", model, brief, bool(json_schema)
            )

        # Get the appropriate client for this model
        client, normalized_model, expected_response_model = self._get_client(model)

        # Determine backend name for metrics and logging
        backend_name = self._get_backend_name(client)

        if self.debug:
            if normalized_model != model:
                logger.debug(
                    "Using %s client for model: %s (normalized from %s)",
                    backend_name,
                    normalized_model,
                    model,
                )
            else:
                logger.debug("Using %s client for model: %s", backend_name, model)
            client.debug = True

        # Track timing for metrics
        start_time = time.perf_counter()
        status = "success"
        tokens_in = 0
        tokens_out = 0

        try:
            generate_kwargs: Dict[str, Any] = {
                "prompt": prompt,
                "model": normalized_model,
                "brief": brief,
                "json_schema": json_schema,
                "context": context,
            }
            if isinstance(client, lmstudio_client.LMStudioClient):
                generate_kwargs["expected_response_model"] = expected_response_model

            result = client.generate_chat(**generate_kwargs)

            # Extract token usage if available
            if result.usage:
                tokens_in = result.usage.tokens_in
                tokens_out = result.usage.tokens_out

            # Always log token usage for all LLM queries
            response_type = "JSON" if json_schema else "text"
            if result.usage:
                logger.info(
                    "LLM Query Complete [%s] - Model: %s, Type: %s, In: %d, Out: %d, Total: %d, Cost: $%.6f",
                    normalized_model,
                    model,
                    response_type,
                    result.usage.tokens_in,
                    result.usage.tokens_out,
                    result.usage.total_tokens,
                    result.usage.cost,
                )

                if self.debug:
                    logger.debug(
                        "Chat complete: %s response, %d tokens",
                        response_type,
                        result.usage.total_tokens,
                    )
            else:
                logger.info(
                    "LLM Query Complete [%s] - Model: %s, Type: %s (no usage info)",
                    normalized_model,
                    model,
                    response_type,
                )

            return result

        except Exception as e:
            status = "error"
            logger.error("Chat generation failed: %s", str(e))
            raise

        finally:
            # Record metrics if callback is set
            if _metrics_callback is not None:
                duration = time.perf_counter() - start_time
                try:
                    _metrics_callback(
                        backend_name, normalized_model, duration, status, tokens_in, tokens_out
                    )
                except Exception as metrics_error:
                    logger.warning("Failed to record LLM metrics: %s", metrics_error)


# Lazy client instance - only created when first accessed
_client: Optional[UnifiedLLMClient] = None


def _get_client() -> UnifiedLLMClient:
    """Get or create the default client instance."""
    global _client
    if _client is None:
        _client = UnifiedLLMClient()
    return _client


# Expose key functions at module level for API compatibility
def warm_model(model: str, timeout: Optional[float] = None) -> bool:
    """Warm up a model for faster first inference."""
    return _get_client().warm_model(model, timeout)


def unload_model(model: str) -> bool:
    """Unload a model from memory."""
    return _get_client().unload_model(model)


def generate_chat(
    prompt: str,
    model: str,
    brief: bool = False,
    json_schema: Optional[Union[Dict[str, Any], Schema]] = None,
    context: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Response:
    """
    Generate a chat response using appropriate backend based on model name.

    Returns:
        Response data class containing response_text, structured_data, and usage
        For text responses, structured_data will be empty dict
        For JSON responses, response_text will be empty string
    """
    return _get_client().generate_chat(prompt, model, brief, json_schema, context, timeout)
