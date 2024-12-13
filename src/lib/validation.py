#!/usr/bin/python3
"""Validation utilities for LLM responses."""

import enum
import json
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import pydantic

from clients import openai_client, ollama_client

VALIDATION_PROMPTS = {
    "definition": lambda response, expected, context: f"""Given this definition: "{response}"
Does this definition accurately describe the word "{expected}"?""",
    
    "general_knowledge": lambda response, expected, context: f"""Given this question and answer:
Question: {context}
Response: {response}
Expected: {expected}

Is this response correct?""",
    
    "ambiguous_meaning": lambda response, expected, context: f"""In this sentence: "{context}"
Are there multiple valid interpretations of the word "{expected}"?"""
}

@dataclass
class ValidationResult:
    """Results from validating LLM responses."""
    valid: bool
    confidence: float
    explanation: str
    expected: Optional[str] = None
    response: Optional[str] = None
    validator_results: List[Dict] = None

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
    
    def validate(
        self,
        response: str,
        task_type: str,
        expected: str = None,
        context: str = None,
        validator_models: tuple = ("qwen2.5:7b:Q4_K_M", "gemma2:9b:Q4_0")
    ) -> ValidationResult:
        """Validate a response for a given task type."""
        if task_type not in VALIDATION_PROMPTS:
            raise ValueError(f"Unsupported task type: {task_type}")

        validation_results = []
        schema = {
            "type": "object",
            "properties": {
                "explanation": {"type": "string"},
                "valid": {"type": "boolean"},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100}
            },
            "required": ["explanation", "valid", "confidence"]
        }

        prompt = VALIDATION_PROMPTS[task_type](response, expected, context) + """

Respond in JSON format with:
- explanation: brief reason for your decision
- valid: boolean indicating if the response is correct/valid
- confidence: 0-100 score of your confidence"""

        for model in validator_models:
            ollama_model = ":".join(model.split(":")[:-1])
            try:
                response_text, _ = ollama_client.generate_chat(
                    prompt,
                    ollama_model,
                    json_schema=schema,
                    structured_json=True
                )
                result = json.loads(response_text)
                validation_results.append({"validator_model": model, **result})
            except (json.JSONDecodeError, KeyError):
                validation_results.append({
                    "validator_model": model,
                    "explanation": "Failed to parse validator response",
                    "valid": False,
                    "confidence": 0
                })

        is_valid = all(r["valid"] for r in validation_results)
        avg_confidence = sum(r["confidence"] for r in validation_results) / len(validation_results)

        return ValidationResult(
            valid=is_valid,
            confidence=avg_confidence,
            explanation=validation_results[0]["explanation"],
            expected=expected,
            response=response,
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

def validate(*args, **kwargs) -> ValidationResult:
    return validator.validate(*args, **kwargs)

def validate_definition(response: str, expected: str, **kwargs) -> ValidationResult:
    return validate(response, "definition", expected, **kwargs)

def validate_general_knowledge(response: str, expected: str, context: str, **kwargs) -> ValidationResult:
    return validate(response, "general_knowledge", expected, context, **kwargs)

def evaluate_response(*args, **kwargs) -> Tuple[ResponseEvaluation, Dict]:
    return validator.evaluate_response(*args, **kwargs)
