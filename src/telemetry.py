#!/usr/bin/python3

"""Standardized tracking of LLM usage metrics and cost estimation."""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum, auto

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ModelTier(Enum):
    """LLM model tiers for cost estimation."""
    # OpenAI models
    GPT4_MINI = auto()  # gpt-4o-mini models
    GPT4 = auto()       # gpt-4o models
    
    # Anthropic models
    CLAUDE_HAIKU = auto()    # claude-3-haiku models
    CLAUDE_SONNET = auto()   # claude-3-sonnet models
    CLAUDE_OPUS = auto()     # claude-3-opus models
    
    # Ollama cost is based on compute time
    OLLAMA = auto()      # All Ollama models

class CostConfig:
    """Cost configurations for different model tiers."""
    
    # OpenAI costs per million tokens
    GPT4_COSTS = {
        ModelTier.GPT4_MINI: {"input": 0.15, "output": 0.6},   # $0.15/$0.60 per million
        ModelTier.GPT4: {"input": 2.5, "output": 10.0},        # $2.50/$10.00 per million
    }
    
    # Anthropic costs per million tokens
    CLAUDE_COSTS = {
        ModelTier.CLAUDE_HAIKU: {"input": 0.25, "output": 1.25},     # $0.25/$1.25 per million
        ModelTier.CLAUDE_SONNET: {"input": 3.0, "output": 15.0},     # $3.00/$15.00 per million
        ModelTier.CLAUDE_OPUS: {"input": 15.0, "output": 75.0},      # $15.00/$75.00 per million
    }
    
    # Ollama cost per compute second (estimated)
    OLLAMA_COST_PER_SEC = 0.000_05  # $0.05 per thousand seconds

    @classmethod
    def get_model_tier(cls, model_name: str) -> ModelTier:
        """Determine model tier from model name."""
        model_lower = model_name.lower()
        
        # OpenAI models
        if "gpt-4o-mini" in model_lower:
            return ModelTier.GPT4_MINI
        elif "gpt-4o" in model_lower:
            return ModelTier.GPT4
            
        # Anthropic models
        elif "claude" in model_lower:
            if "haiku" in model_lower:
                return ModelTier.CLAUDE_HAIKU
            elif "sonnet" in model_lower:
                return ModelTier.CLAUDE_SONNET
            elif "opus" in model_lower:
                return ModelTier.CLAUDE_OPUS
                
        # Default to Ollama for unknown models
        return ModelTier.OLLAMA

    @classmethod
    def estimate_cost(cls, 
                     tokens_in: int = 0, 
                     tokens_out: int = 0,
                     compute_ms: float = 0,
                     model: str = None) -> float:
        """
        Estimate cost based on usage and model tier.
        
        Args:
            tokens_in: Number of input tokens
            tokens_out: Number of output tokens
            compute_ms: Compute time in milliseconds (for Ollama)
            model: Model name/identifier
            
        Returns:
            Estimated cost in USD
        """
        if not model:
            logger.warning("No model specified for cost estimation")
            return 0.0
            
        tier = cls.get_model_tier(model)
        
        # Handle Ollama models (cost based on compute time)
        if tier == ModelTier.OLLAMA:
            compute_seconds = compute_ms / 1000
            return compute_seconds * cls.OLLAMA_COST_PER_SEC
            
        # Handle OpenAI models
        elif tier in cls.GPT4_COSTS:
            costs = cls.GPT4_COSTS[tier]
            return (
                (tokens_in * costs["input"] / 1_000_000) +
                (tokens_out * costs["output"] / 1_000_000)
            )
            
        # Handle Anthropic models
        elif tier in cls.CLAUDE_COSTS:
            costs = cls.CLAUDE_COSTS[tier]
            return (
                (tokens_in * costs["input"] / 1_000_000) +
                (tokens_out * costs["output"] / 1_000_000)
            )
            
        else:
            logger.warning(f"Unknown model tier for {model}, cannot estimate cost")
            return 0.0

@dataclass
class LLMUsage:
    """Tracks usage metrics for LLM operations.
    
    Required fields:
    - tokens_in: Number of input tokens
    - tokens_out: Number of output/generated tokens
    - cost: Cost in USD
    - total_msec: Total latency in milliseconds
    
    Optional fields can be passed as kwargs and will be stored in metadata dict.
    """
    
    tokens_in: int
    tokens_out: int
    cost: float
    total_msec: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api_response(cls, response_data: Dict[str, Any], model: str = None, **kwargs) -> 'LLMUsage':
        """Create LLMUsage from API response data.
        
        Supports OpenAI, Anthropic, and Ollama response formats.
        Additional kwargs are stored in metadata dict.
        """
        # Extract required fields with reasonable fallbacks
        tokens_in = response_data.get('prompt_tokens', 
                                    response_data.get('prompt_eval_count', 0))
        tokens_out = response_data.get('completion_tokens',
                                     response_data.get('eval_count', 0))
        
        # Convert duration from API format (if present)
        duration = response_data.get('total_duration', 0)
        if duration > 1000:  # Ollama returns nanoseconds
            duration = duration / 1_000_000  # Convert to milliseconds
            
        # Calculate cost if not provided
        cost = response_data.get('cost', CostConfig.estimate_cost(
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            compute_ms=duration,
            model=model
        ))
        
        # Store any additional fields from response_data or kwargs in metadata
        metadata = {}
        
        # Add any extra fields from response_data
        for key, value in response_data.items():
            if key not in ['prompt_tokens', 'completion_tokens', 'total_duration',
                          'prompt_eval_count', 'eval_count', 'cost']:
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
            metadata=metadata
        )

    def combine(self, other: 'LLMUsage') -> 'LLMUsage':
        """Combine usage metrics from multiple operations."""
        combined_metadata = self.metadata.copy()
        combined_metadata.update(other.metadata)
        
        return LLMUsage(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            cost=self.cost + other.cost,
            total_msec=self.total_msec + other.total_msec,
            metadata=combined_metadata
        )

    @property
    def total_tokens(self) -> int:
        """Total tokens used (input + output)."""
        return self.tokens_in + self.tokens_out

    def __str__(self) -> str:
        """Human readable format showing core metrics."""
        return (f"LLMUsage(tokens_in={self.tokens_in}, tokens_out={self.tokens_out}, "
                f"cost=${self.cost:.6f}, latency={self.total_msec:.1f}ms)")

    def to_dict(self) -> Dict[str, Any]:
        """Convert usage data to dictionary format."""
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "total_tokens": self.total_tokens,
            "cost": self.cost,
            "total_msec": self.total_msec,
            **self.metadata
        }
