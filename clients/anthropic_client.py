#!/usr/bin/python3
"""Client for interacting with Anthropic API."""

from dataclasses import dataclass
from typing import Dict, Tuple, Union
from anthropic import Anthropic

TEST_MODEL = "claude-3-haiku-20240307"
PROD_MODEL = "claude-3-5-sonnet-20240620"

@dataclass
class UsageInfo:
    """Tracks token usage and cost information."""
    tokens_in: int
    tokens_out: int
    cost: float

    @classmethod
    def from_completion(cls, usage, model: str = "haiku") -> 'UsageInfo':
        """Create UsageInfo from Anthropic completion usage data."""
        costs = {
            "haiku": {"input": 0.25, "output": 1.25},
            "sonnet": {"input": 3, "output": 15},
            "opus": {"input": 15, "output": 75},
        }
        
        cost = (usage.input_tokens * (costs[model]["input"] / 1000000) +
                usage.output_tokens * (costs[model]["output"] / 1000000))
                
        return cls(
            tokens_in=usage.input_tokens,
            tokens_out=usage.output_tokens,
            cost=cost
        )

class AnthropicClient:
    """Client for making requests to Anthropic API."""
    
    def __init__(self):
        """Initialize Anthropic client with API key."""
        self.client = Anthropic(api_key=self._load_key())

    def _load_key(self) -> str:
        """Load Anthropic API key from file."""
        with open("./keys/anthropic.key") as f:
            return f.read().strip()

    def generate_text(self, prompt: str, entry: str, 
                     model: str = TEST_MODEL) -> Tuple[str, Dict]:
        """Generate text completion from prompt and entry."""
        message = self.client.messages.create(
            max_tokens=1536,
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
        
        usage = UsageInfo.from_completion(message.usage)
        return message.content[0].text, vars(usage)

# Create default client instance
client = AnthropicClient()

# Expose key functions at module level for API compatibility
def generate_text(prompt: str, entry: str) -> Tuple[str, Dict]:
    return client.generate_text(prompt, entry)
