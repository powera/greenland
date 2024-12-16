#!/usr/bin/python3
"""Client for interacting with Anthropic API."""

import os
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from anthropic import Anthropic

import constants

# Model identifiers
TEST_MODEL = "claude-3-haiku-20240307"
PROD_MODEL = "claude-3-5-sonnet-20240620"

# Cost per million tokens for different model tiers
COST_PER_MILLION_TOKENS = {
    "haiku": {
        "input": 0.25,   # $0.25 per million input tokens
        "output": 1.25   # $1.25 per million output tokens
    },
    "sonnet": {
        "input": 3.0,    # $3.00 per million input tokens
        "output": 15.0   # $15.00 per million output tokens
    },
    "opus": {
        "input": 15.0,   # $15.00 per million input tokens
        "output": 75.0   # $75.00 per million output tokens
    }
}

@dataclass
class UsageInfo:
    """Tracks token usage and cost information for Anthropic API calls."""
    tokens_in: int
    tokens_out: int
    cost: float

    @classmethod
    def from_completion(cls, usage, model: str = "haiku") -> 'UsageInfo':
        """
        Create UsageInfo from Anthropic completion usage data.
        
        Args:
            usage: Usage data from Anthropic completion
            model: Model tier ('haiku', 'sonnet', or 'opus')
            
        Returns:
            UsageInfo instance with calculated costs
        """
        if model not in COST_PER_MILLION_TOKENS:
            raise ValueError(f"Unknown model tier: {model}")
            
        costs = COST_PER_MILLION_TOKENS[model]
        cost = (
            (usage.input_tokens * costs["input"] / 1_000_000) +
            (usage.output_tokens * costs["output"] / 1_000_000)
        )
                
        return cls(
            tokens_in=usage.input_tokens,
            tokens_out=usage.output_tokens,
            cost=cost
        )

class AnthropicClient:
    """Client for making requests to Anthropic API."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Anthropic client.
        
        Args:
            api_key: Optional API key (will load from file if not provided)
        """
        self.client = Anthropic(
            api_key=api_key or self._load_key()
        )

    def _load_key(self) -> str:
        """
        Load Anthropic API key from file.
        
        Returns:
            API key string
            
        Raises:
            FileNotFoundError: If key file doesn't exist
        """
        key_path = os.path.join(constants.KEY_DIR, "anthropic.key")
        try:
            with open(key_path) as f:
                return f.read().strip()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Anthropic API key not found at {key_path}. "
                "Please create this file with your API key."
            )

    def generate_text(
        self,
        prompt: str,
        entry: str,
        model: str = TEST_MODEL,
        max_tokens: int = 1536
    ) -> Tuple[str, Dict]:
        """
        Generate text completion from prompt and entry.
        
        Args:
            prompt: The instruction/question to guide generation
            entry: The input text to analyze/respond to
            model: Model identifier to use
            max_tokens: Maximum tokens in response
            
        Returns:
            Tuple of (generated_text, usage_info)
        """
        message = self.client.messages.create(
            max_tokens=max_tokens,
            system="You are a concise assistant. Answer the following question "
                   f"about the user-provided text: {prompt}",
            messages=[
                {
                    "role": "user",
                    "content": entry,
                }
            ],
            model=model
        )
        
        # Determine model tier from model string
        model_tier = "haiku" if "haiku" in model.lower() else \
                    "sonnet" if "sonnet" in model.lower() else \
                    "opus" if "opus" in model.lower() else "haiku"
        
        usage = UsageInfo.from_completion(message.usage, model_tier)
        return message.content[0].text, vars(usage)

# Create default client instance
client = AnthropicClient()

# Expose key functions at module level for API compatibility
def generate_text(prompt: str, entry: str) -> Tuple[str, Dict]:
    """
    Generate text using default client instance.
    
    Args:
        prompt: The instruction/question to guide generation
        entry: The input text to analyze/respond to
        
    Returns:
        Tuple of (generated_text, usage_info)
    """
    return client.generate_text(prompt, entry)
