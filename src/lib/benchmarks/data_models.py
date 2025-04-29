#!/usr/bin/python3

"""Data models for benchmark system."""

import json
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Set


class AnswerType(str, Enum):
    """Enumeration of supported answer types."""
    FREE_TEXT = "free_text"
    MULTIPLE_CHOICE = "multiple_choice"
    JSON = "json"
    BOOLEAN = "boolean"
    NUMERIC = "numeric"


class Difficulty(str, Enum):
    """Enumeration of difficulty levels."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class EvaluationCriteria:
    """Defines how to evaluate responses."""
    exact_match: bool = True         # Whether to require exact string match
    case_sensitive: bool = False     # Whether to consider letter case
    contains: bool = False           # Whether answer just needs to contain correct text
    required_fields: List[str] = field(default_factory=list)  # Required fields for JSON
    tolerance: float = 0.0           # Tolerance for numeric answers
    
    def to_dict(self) -> Dict:
        """Convert to dictionary, removing default values."""
        result = {}
        defaults = EvaluationCriteria()
        
        for k, v in asdict(self).items():
            default_value = getattr(defaults, k)
            if v != default_value:
                result[k] = v
                
        return result


@dataclass
class BenchmarkQuestion:
    """Standardized benchmark question format."""
    # Core fields (required)
    question_text: str                      # The actual question text presented to the model
    answer_type: AnswerType                 # Format of expected answer
    correct_answer: Any                     # The expected correct answer
    
    # Optional metadata fields
    category: Optional[str] = None          # Question category or topic
    difficulty: Optional[Difficulty] = None # Difficulty level
    tags: List[str] = field(default_factory=list)  # List of tags for filtering/grouping
    
    # Optional fields for specific answer types
    choices: List[str] = field(default_factory=list)  # For multiple_choice questions
    schema: Optional[Dict] = None           # For JSON answer type
    evaluation_criteria: EvaluationCriteria = field(default_factory=EvaluationCriteria)

    def to_dict(self) -> Dict:
        """Convert to dictionary, removing None values."""
        result = {}
        for k, v in asdict(self).items():
            if k == "answer_type" and isinstance(v, AnswerType):
                result[k] = v.value
            elif k == "difficulty" and isinstance(v, Difficulty):
                result[k] = v.value
            elif k == "evaluation_criteria" and isinstance(v, EvaluationCriteria):
                criteria_dict = v.to_dict()
                if criteria_dict:  # Only include if non-default
                    result[k] = criteria_dict
            elif k == "tags" or k == "choices":
                if v:  # Only include non-empty lists
                    result[k] = v
            elif v is not None:
                result[k] = v
        return result


@dataclass
class BenchmarkResult:
    """Stores results and metadata for a benchmark run."""
    question_id: str
    score: int                    # 100 for correct, 0 for incorrect, or partial score
    eval_msec: int                # Evaluation time in milliseconds
    debug_json: Optional[str] = None  # Debug information (model response, etc.)
    thought_process: Optional[str] = None  # Add this line to store model's reasoning


@dataclass
class BenchmarkMetadata:
    """Metadata about a benchmark."""
    code: str                    # Identifier code (e.g., "0015_spell_check")
    name: str                    # Display name
    description: Optional[str] = None  # Description
    version: str = "1.0"         # Version of the benchmark
    tags: List[str] = field(default_factory=list)  # Tags for categorization
    max_score: int = 100         # Maximum possible score
