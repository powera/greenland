#!/usr/bin/python3

"""Standardized tracking of LLM usage metrics and cost estimation."""

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ModelTier(Enum):
    """LLM model tiers for cost estimation."""

    # OpenAI models
    GPT4_MINI = auto()  # gpt-4o-mini models
    GPT4 = auto()  # gpt-4o models
    GPT_41_NANO = auto()  # gpt-4.1-nano models
    GPT_41_MINI = auto()  # gpt-4.1-mini models
    GPT_5_NANO = auto()  # gpt-5-nano models
    GPT_5_MINI = auto()  # gpt-5-mini models
    GPT_52 = auto()  # gpt-5.2 models
    GPT_54_NANO = auto()  # gpt-5.4-nano models
    GPT_54_MINI = auto()  # gpt-5.4-mini models
    GPT_56_LUNA = auto()  # gpt-5.6-luna models
    GPT_6_LUNA = auto()  # gpt-6-luna models

    # Anthropic models
    CLAUDE_HAIKU = auto()  # claude-3-5-haiku models

    # Gemini models
    GEMINI_FLASH = auto()  # gemini-2.5-flash models
    GEMINI_35_FLASH_LITE = auto()  # gemini-3.5-flash-lite models

    # DigitalOcean Gradient models (flat, vendor-embedded ids). Routed by the
    # "do/" prefix; the prefix is stripped before the name reaches here, so the
    # ids seen are e.g. "anthropic-claude-fable-5", "llama-4-maverick".
    DO_CLAUDE_FABLE = auto()  # anthropic-claude-fable-5
    DO_GPT_56_SOL = auto()  # openai-gpt-5.6-sol
    DO_LLAMA_4_MAVERICK = auto()  # llama-4-maverick
    DO_DEEPSEEK_V4_PRO = auto()  # deepseek-v4-pro
    DO_DEEPSEEK_4_FLASH = auto()  # deepseek-4-flash

    # Ollama cost is based on compute time
    OLLAMA = auto()  # All Ollama models


class CostConfig:
    """Cost configurations for different model tiers."""

    # Every table is USD per million tokens.  "input" prices an uncached input
    # token; "cached_input" a cache read and "cache_write" a token written to
    # the cache, each charged at "input" when the entry leaves it out.

    # OpenAI costs per million tokens.  OpenAI caches prompt prefixes on its
    # own; from gpt-5.6 a cache write costs 1.25x the input rate, while older
    # models write for free.
    GPT4_COSTS = {
        ModelTier.GPT4_MINI: {"input": 0.15, "cached_input": 0.075, "output": 0.6},
        ModelTier.GPT4: {"input": 2.5, "cached_input": 1.25, "output": 10.0},
        ModelTier.GPT_41_NANO: {"input": 0.1, "cached_input": 0.025, "output": 0.4},
        ModelTier.GPT_41_MINI: {"input": 0.4, "cached_input": 0.10, "output": 1.6},
        ModelTier.GPT_5_NANO: {"input": 0.05, "cached_input": 0.005, "output": 0.4},
        ModelTier.GPT_5_MINI: {"input": 0.25, "cached_input": 0.025, "output": 2.0},
        ModelTier.GPT_52: {"input": 1.75, "cached_input": 0.175, "output": 14.0},
        ModelTier.GPT_54_NANO: {"input": 0.20, "cached_input": 0.02, "output": 1.25},
        ModelTier.GPT_54_MINI: {"input": 0.75, "cached_input": 0.075, "output": 4.50},
        # Short-context rates for the Luna models; over 272K input is 2x the
        # input and cache rates and 1.5x output.
        ModelTier.GPT_56_LUNA: {
            "input": 0.20,
            "cached_input": 0.02,
            "cache_write": 0.25,
            "output": 1.20,
        },
        ModelTier.GPT_6_LUNA: {
            "input": 0.10,
            "cached_input": 0.01,
            "cache_write": 0.125,
            "output": 0.50,
        },
    }

    # Anthropic costs per million tokens.  A cache write costs more than an
    # ordinary input token, so a prompt read only once loses money by caching.
    CLAUDE_COSTS = {
        ModelTier.CLAUDE_HAIKU: {
            "input": 0.8,
            "cached_input": 0.08,
            "cache_write": 1.0,
            "output": 4,
        },
    }

    GEMINI_COSTS = {
        ModelTier.GEMINI_FLASH: {"input": 0.15, "output": 0.6},
        ModelTier.GEMINI_35_FLASH_LITE: {"input": 0.30, "output": 2.50},
    }

    # Synthetic placeholder rate for a DigitalOcean model whose real price has
    # not been looked up. Deliberately not free: a zero would make an unpriced
    # model look cheap in a cost comparison, which is the failure mode this
    # table exists to prevent. Every entry below currently carries a real rate;
    # this remains for the next model added before its price is known.
    DIGITALOCEAN_PLACEHOLDER_COST = {"input": 1.00, "output": 5.00}

    # DigitalOcean Gradient costs per million tokens. DO resells each vendor's
    # model at its own rate, so these are separate from the first-party tables
    # above even where the underlying model is the same.
    DIGITALOCEAN_COSTS = {
        ModelTier.DO_CLAUDE_FABLE: {"input": 10.00, "output": 50.00},
        ModelTier.DO_GPT_56_SOL: {"input": 5.00, "output": 30.00},
        ModelTier.DO_LLAMA_4_MAVERICK: {"input": 0.25, "output": 0.87},
        ModelTier.DO_DEEPSEEK_V4_PRO: {"input": 1.39, "output": 2.78},
        ModelTier.DO_DEEPSEEK_4_FLASH: {"input": 0.11, "output": 0.22},
    }

    # Model-name substrings that identify a DigitalOcean-hosted model. Used both
    # to pick a tier and to keep an unpriced DO model from falling through to
    # Ollama compute-time pricing in estimate_cost().
    DIGITALOCEAN_MODEL_MARKERS = (
        "anthropic-claude",
        "openai-gpt",
        "llama-",
        "deepseek-",
        "mistral-",
        "qwen-",
    )

    # Ollama cost per compute second (estimated)
    OLLAMA_COST_PER_SEC = 0.000_05  # $0.05 per thousand seconds

    @classmethod
    def get_model_tier(cls, model_name: str) -> ModelTier:
        """Determine model tier from model name."""
        model_lower = model_name.lower()

        # DigitalOcean-hosted models first: their ids embed a vendor name, so
        # "anthropic-claude-fable-5" contains "claude" and would otherwise be
        # priced as a first-party Anthropic model below.
        if "anthropic-claude-fable" in model_lower:
            return ModelTier.DO_CLAUDE_FABLE
        elif "openai-gpt-5.6-sol" in model_lower:
            return ModelTier.DO_GPT_56_SOL
        elif "llama-4-maverick" in model_lower:
            return ModelTier.DO_LLAMA_4_MAVERICK
        elif "deepseek-v4-pro" in model_lower:
            return ModelTier.DO_DEEPSEEK_V4_PRO
        elif "deepseek-4-flash" in model_lower:
            return ModelTier.DO_DEEPSEEK_4_FLASH

        # OpenAI models
        elif "gpt-4o-mini" in model_lower:
            return ModelTier.GPT4_MINI
        elif "gpt-4.1-nano" in model_lower:
            return ModelTier.GPT_41_NANO
        elif "gpt-4.1-mini" in model_lower:
            return ModelTier.GPT_41_MINI
        elif "gpt-4o" in model_lower:
            return ModelTier.GPT4
        elif "gpt-6-luna" in model_lower:
            return ModelTier.GPT_6_LUNA
        elif "gpt-5.6-luna" in model_lower:
            return ModelTier.GPT_56_LUNA
        elif "gpt-5.4-nano" in model_lower:
            return ModelTier.GPT_54_NANO
        elif "gpt-5.4-mini" in model_lower:
            return ModelTier.GPT_54_MINI
        elif "gpt-5-nano" in model_lower:
            return ModelTier.GPT_5_NANO
        elif "gpt-5-mini" in model_lower:
            return ModelTier.GPT_5_MINI
        elif "gpt-5.2" in model_lower:
            return ModelTier.GPT_52

        # Anthropic models
        elif "claude" in model_lower:
            if "haiku" in model_lower:
                return ModelTier.CLAUDE_HAIKU
        elif "gemini" in model_lower:
            if "gemini-3.5-flash-lite" in model_lower:
                return ModelTier.GEMINI_35_FLASH_LITE
            elif "flash" in model_lower:
                return ModelTier.GEMINI_FLASH

        # Local/Ollama models: fall back to compute-time pricing.
        # For remote models that reach here, estimate_cost() will log a warning
        # and return 0.0 rather than silently using Ollama time-based pricing.
        return ModelTier.OLLAMA

    @classmethod
    def estimate_cost(
        cls,
        tokens_in: int = 0,
        tokens_out: int = 0,
        compute_ms: float = 0,
        model: Optional[str] = None,
        cached_tokens_in: int = 0,
        cache_write_tokens_in: int = 0,
    ) -> float:
        """
        Estimate cost based on usage and model tier.

        Args:
            tokens_in: Number of input tokens, cached and cache-write ones included
            tokens_out: Number of output tokens
            compute_ms: Compute time in milliseconds (for Ollama)
            model: Model name/identifier
            cached_tokens_in: Input tokens read from the provider's prompt cache
            cache_write_tokens_in: Input tokens written to the prompt cache

        Returns:
            Estimated cost in USD
        """
        if not model:
            logger.warning("No model specified for cost estimation")
            return 0.0

        tier = cls.get_model_tier(model)

        # Handle Ollama/local models (cost based on compute time)
        if tier == ModelTier.OLLAMA:
            # Remote API models that weren't recognized should not fall back
            # to Ollama time-based pricing — return 0 and warn instead.
            model_lower = model.lower()
            remote_markers = ("gpt-", "claude", "gemini") + cls.DIGITALOCEAN_MODEL_MARKERS
            if any(marker in model_lower for marker in remote_markers):
                logger.warning(
                    "No token pricing configured for remote model '%s'. "
                    "Add it to CostConfig in telemetry.py.",
                    model,
                )
                return 0.0
            compute_seconds = compute_ms / 1000
            return compute_seconds * cls.OLLAMA_COST_PER_SEC

        for table in (cls.GPT4_COSTS, cls.CLAUDE_COSTS, cls.GEMINI_COSTS, cls.DIGITALOCEAN_COSTS):
            if tier in table:
                return cls._token_cost(
                    table[tier], tokens_in, tokens_out, cached_tokens_in, cache_write_tokens_in
                )

        logger.warning(f"Unknown model tier for {model}, cannot estimate cost")
        return 0.0

    @staticmethod
    def _token_cost(
        costs: Dict[str, float],
        tokens_in: int,
        tokens_out: int,
        cached_tokens_in: int,
        cache_write_tokens_in: int,
    ) -> float:
        """Price one call from a per-million-token rate table."""
        uncached_tokens_in = max(tokens_in - cached_tokens_in - cache_write_tokens_in, 0)
        input_cost = (
            uncached_tokens_in * costs["input"]
            + cached_tokens_in * costs.get("cached_input", costs["input"])
            + cache_write_tokens_in * costs.get("cache_write", costs["input"])
        )
        return (input_cost + tokens_out * costs["output"]) / 1_000_000


@dataclass
class LLMUsage:
    """Tracks usage metrics for LLM operations.

    Required fields:
    - tokens_in: Number of input tokens
    - tokens_out: Number of output/generated tokens
    - cost: Cost in USD
    - total_msec: Total latency in milliseconds

    The prompt-cache counts are a breakdown of tokens_in, not an addition to it:
    - cached_tokens_in: Input tokens read from the provider's prompt cache
    - cache_write_tokens_in: Input tokens written to it (Anthropic, OpenAI gpt-5.6+)

    Optional fields can be passed as kwargs and will be stored in metadata dict.
    """

    tokens_in: int
    tokens_out: int
    cost: float
    total_msec: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    cached_tokens_in: int = 0
    cache_write_tokens_in: int = 0

    @classmethod
    def from_api_response(
        cls, response_data: Dict[str, Any], model: Optional[str] = None, **kwargs: Any
    ) -> "LLMUsage":
        """Create LLMUsage from API response data.

        Supports OpenAI, Anthropic, and Ollama response formats.
        Additional kwargs are stored in metadata dict.
        """
        # Extract required fields with reasonable fallbacks
        tokens_in = response_data.get("prompt_tokens", response_data.get("prompt_eval_count", 0))
        tokens_out = response_data.get("completion_tokens", response_data.get("eval_count", 0))
        cached_tokens_in = response_data.get("cached_tokens", 0) or 0
        cache_write_tokens_in = response_data.get("cache_write_tokens", 0) or 0

        # Convert duration from API format (if present)
        duration = response_data.get("total_duration", 0)
        # TODO: fix hackiness
        if duration > 1000000:  # Ollama returns nanoseconds
            duration = duration / 1_000_000  # Convert to milliseconds

        # Calculate cost if not provided
        cost = response_data.get(
            "cost",
            CostConfig.estimate_cost(
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                compute_ms=duration,
                model=model,
                cached_tokens_in=cached_tokens_in,
                cache_write_tokens_in=cache_write_tokens_in,
            ),
        )

        # Store any additional fields from response_data or kwargs in metadata
        metadata = {}

        # Add any extra fields from response_data
        for key, value in response_data.items():
            if key not in [
                "prompt_tokens",
                "completion_tokens",
                "total_duration",
                "prompt_eval_count",
                "eval_count",
                "cost",
                "cached_tokens",
                "cache_write_tokens",
            ]:
                metadata[key] = value
                logger.debug(f"Storing extra API response field in metadata: {key}")

        # Add any kwargs
        for key, value in kwargs.items():
            metadata[key] = value
            logger.debug(f"Storing kwarg in metadata: {key}")

        return cls(
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
            total_msec=duration,
            metadata=metadata,
            cached_tokens_in=cached_tokens_in,
            cache_write_tokens_in=cache_write_tokens_in,
        )

    def combine(self, other: "LLMUsage") -> "LLMUsage":
        """Combine usage metrics from multiple operations."""
        combined_metadata = self.metadata.copy()
        combined_metadata.update(other.metadata)

        return LLMUsage(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            cost=self.cost + other.cost,
            total_msec=self.total_msec + other.total_msec,
            metadata=combined_metadata,
            cached_tokens_in=self.cached_tokens_in + other.cached_tokens_in,
            cache_write_tokens_in=self.cache_write_tokens_in + other.cache_write_tokens_in,
        )

    @property
    def total_tokens(self) -> int:
        """Total tokens used (input + output)."""
        return self.tokens_in + self.tokens_out

    def __str__(self) -> str:
        """Human readable format showing core metrics."""
        return (
            f"LLMUsage(tokens_in={self.tokens_in}, tokens_out={self.tokens_out}, "
            f"cost=${self.cost:.6f}, latency={self.total_msec:.1f}ms)"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert usage data to dictionary format."""
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "total_tokens": self.total_tokens,
            "cached_tokens_in": self.cached_tokens_in,
            "cache_write_tokens_in": self.cache_write_tokens_in,
            "cost": self.cost,
            "total_msec": self.total_msec,
            **self.metadata,
        }
