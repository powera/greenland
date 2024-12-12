#!/usr/bin/python3
"""Client for interacting with OpenAI API."""

import enum
import json
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
import pydantic
import tiktoken
from openai import OpenAI

TEST_MODEL = "gpt-4o-mini-2024-07-18"
PROD_MODEL = "gpt-4o-2024-11-20"

@dataclass
class UsageInfo:
    """Tracks token usage and cost information."""
    tokens_in: int
    tokens_out: int
    cost: float

    @classmethod
    def from_completion(cls, usage, model: str = "gpt-4o-mini") -> 'UsageInfo':
        """Create UsageInfo from OpenAI completion usage data."""
        costs = {
            "gpt-4o-mini": {"input": .15, "output": .6},
            "gpt-4o": {"input": 2.5, "output": 10},
        }
        
        cost = (usage.prompt_tokens * (costs[model]["input"] / 1000000) +
                usage.completion_tokens * (costs[model]["output"] / 1000000))
                
        return cls(
            tokens_in=usage.prompt_tokens,
            tokens_out=usage.completion_tokens,
            cost=cost
        )

class OpenAIClient:
    """Client for making requests to OpenAI API."""
    
    PERSONAS = {
        "normal": "You are a helpful assistant.",
        "fifth_grader": """
This LLM responds like an educated but ordinary fifth grader. It expresses ideas clearly 
and uses simple, everyday language, avoiding advanced vocabulary or concepts. When explaining 
things, it breaks down concepts step by step, often comparing new ideas to familiar objects 
or experiences. It's curious and enthusiastic, asking questions when unsure and occasionally 
sharing personal thoughts or feelings, as many kids do. The tone is friendly, casual, and 
sincere—like talking to a peer or a favorite teacher.""",
    }

    def __init__(self):
        """Initialize OpenAI client with API key."""
        self.client = OpenAI(api_key=self._load_key())
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def _load_key(self) -> str:
        """Load OpenAI API key from file."""
        with open("./keys/openai.key") as f:
            return f.read().strip()

    def generate_text(self, prompt: str, sample: str, 
                     model: str = TEST_MODEL) -> Tuple[str, Dict]:
        """Generate text completion from sample and prompt."""
        if len(sample) > 52000:
            raise ValueError("Input data too long")

        completion = self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a concise assistant, answering this question "
                              f"about the user-provided text: {prompt}",
                },
                {
                    "role": "user",
                    "content": sample,
                },
            ],
            presence_penalty=0.25,
            max_tokens=1536,
            temperature=0.15,
        )

        usage = UsageInfo.from_completion(completion.usage)
        return completion.choices[0].message.content, vars(usage)

    def answer_question(self, prompt: str, persona: str = "normal",
                       model: str = TEST_MODEL) -> Tuple[str, Dict]:
        """Generate chat completion for given prompt."""
        if len(prompt) > 12000:
            raise ValueError("Input data too long")

        completion = self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": self.PERSONAS[persona],
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_tokens=1536,
            temperature=0.45,
        )

        usage = UsageInfo.from_completion(completion.usage)
        return completion.choices[0].message.content, vars(usage)

# Response evaluation schema and function (to be moved later)
class QualityRating(enum.Enum):
    BAD = "Bad"
    MEDIOCRE = "Mediocre"
    GOOD = "Good"
    VERY_GOOD = "Very good"
    EXCELLENT = "Excellent"

    def __str__(self):
        return self.value

class ResponseSchema(pydantic.BaseModel):
    is_refusal: bool
    overall_quality: QualityRating
    factual_errors: str
    verbosity: str
    repetition: str
    unwarranted_assumptions: str

def evaluate_response(original_prompt: str, original_response: str,
                     model: str = TEST_MODEL) -> Tuple[ResponseSchema, Dict]:
    """Evaluate quality of LLM response."""
    client = OpenAIClient()
    input_length = len(original_prompt) + len(original_response)
    if input_length > 12000:
        raise ValueError("Input data too long")

    completion = client.client.beta.chat.completions.parse(
        model=model,
        messages=[
            {
                "role": "system",
                "content": f"You are a concise assistant evaluating the output of "
                          f"another LLM. The original prompt was << {original_prompt} >>.\n\n"
                          "Comment on the quality of response, any factual errors, whether "
                          "the response was unnecessarily verbose or repetitive, and whether "
                          "any unwarranted assumptions were made in answering the prompt.",
            },
            {
                "role": "user",
                "content": original_response,
            },
        ],
        response_format=ResponseSchema,
        max_tokens=2048,
    )

    usage = UsageInfo.from_completion(completion.usage)
    return completion.choices[0].message.parsed, vars(usage)

# Create default client instance
client = OpenAIClient()

# Expose key functions at module level for API compatibility
def generate_text(prompt: str, sample: str) -> Tuple[str, Dict]:
    return client.generate_text(prompt, sample)

def answer_question(prompt: str, persona: str = "normal") -> Tuple[str, Dict]:
    return client.answer_question(prompt, persona)
