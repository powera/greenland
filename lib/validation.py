#!/usr/bin/python3
"""Validation utilities for LLM responses."""

import enum
import json
from dataclasses import dataclass
from typing import Dict, List, Tuple
import pydantic

from clients import openai_client, ollama_client

@dataclass
class ValidationResult:
    """Base class for validation results."""
    valid: bool
    confidence: float
    explanation: str

@dataclass 
class DefinitionValidation(ValidationResult):
    """Results from validating word definitions."""
    definition: str
    expected_word: str
    likely_word: str
    validator_results: List[Dict]

class QualityRating(enum.Enum):
    """Quality levels for response evaluation."""
    BAD = "Bad"
    MEDIOCRE = "Mediocre"
    GOOD = "Good"
    VERY_GOOD = "Very good"
    EXCELLENT = "Excellent"

    def __str__(self):
        return self.value

class ResponseEvaluation(pydantic.BaseModel):
    """Schema for response quality evaluation."""
    is_refusal: bool
    overall_quality: QualityRating
    factual_errors: str
    verbosity: str
    repetition: str
    unwarranted_assumptions: str

class ResponseValidator:
    """Utilities for validating LLM responses."""
        
    def validate_definition(
        self, 
        definition: str,
        expected_word: str,
        validator_models: tuple = ("granite3-dense:8b:Q4_K_M", "qwen2.5:7b:Q4_K_M")
    ) -> DefinitionValidation:
        """Validate that a definition correctly defines the expected word."""
        validation_results = []
        schema = {
            "type": "object",
            "properties": {
                "matches_word": {"type": "boolean"},
                "likely_word": {"type": "string"},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                "explanation": {"type": "string"}
            },
            "required": ["matches_word", "likely_word"]
        }

        for model in validator_models:
            ollama_model = ":".join(model.split(":")[:-1])
            prompt = f"""Given this definition: "{definition}"
Does this definition accurately describe the word "{expected_word}"?

Respond in JSON format with these fields:
- matches_word: boolean indicating if the definition matches the word
- likely_word: what word you think this actually defines
- confidence: 0-100 score of your confidence
- explanation: brief reason for your decision"""

            response_text, _ = ollama_client.generate_chat(
                prompt,
                ollama_model,
                json_schema=schema,
                structured_json=True
            )
            
            try:
                result = json.loads(response_text)
                validation_results.append({"validator_model": model, **result})
            except json.JSONDecodeError:
                validation_results.append({
                    "validator_model": model,
                    "matches_word": False,
                    "likely_word": "INVALID_RESPONSE",
                    "confidence": 0,
                    "explanation": "Failed to parse validator response"
                })

        valid_count = sum(1 for r in validation_results if r["matches_word"])
        avg_confidence = sum(r.get("confidence", 0) 
                           for r in validation_results) / len(validation_results)

        return DefinitionValidation(
            valid=valid_count >= len(validator_models) / 2,
            confidence=avg_confidence,
            explanation=validation_results[0].get("explanation", ""),
            definition=definition,
            expected_word=expected_word,
            likely_word=validation_results[0].get("likely_word", ""),
            validator_results=validation_results
        )

    def evaluate_response(
        self,
        original_prompt: str,
        original_response: str,
        model: str = openai_client.TEST_MODEL
    ) -> Tuple[ResponseEvaluation, Dict]:
        """Evaluate quality of LLM response."""
        if len(original_prompt) + len(original_response) > 12000:
            raise ValueError("Input data too long")

        completion = openai_client.client.client.beta.chat.completions.parse(
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
            response_format=ResponseEvaluation,
            max_tokens=2048,
        )

        usage = {"tokens_in": completion.usage.prompt_tokens,
                "tokens_out": completion.usage.completion_tokens,
                "cost": openai_client.estimate_cost(completion.usage)}
        return completion.choices[0].message.parsed, usage

# Create default validator instance
validator = ResponseValidator()

# Expose key functions at module level
def validate_definition(*args, **kwargs) -> DefinitionValidation:
    return validator.validate_definition(*args, **kwargs)

def evaluate_response(*args, **kwargs) -> Tuple[ResponseEvaluation, Dict]:
    return validator.evaluate_response(*args, **kwargs)
