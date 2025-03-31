#!/usr/bin/python3

"""Generator for unit conversion benchmark questions."""

import json
import logging
import random
from typing import Dict, List, Optional, Tuple, Iterator

from lib.benchmarks.base_generator import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkMetadata, AnswerType, Difficulty, EvaluationCriteria
)
from lib.benchmarks.factory import generator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Benchmark code
BENCHMARK_CODE = "0022_unit_conversion"

# Default unit conversions if no file is provided
DEFAULT_CONVERSIONS = [
    {"from_unit": "pounds", "to_unit": "kilograms", "factor": 0.45359237, "precision": 1},
    {"from_unit": "kilograms", "to_unit": "pounds", "factor": 2.20462262, "precision": 1},
    {"from_unit": "miles", "to_unit": "kilometers", "factor": 1.60934, "precision": 1},
    {"from_unit": "kilometers", "to_unit": "miles", "factor": 0.621371, "precision": 2},
    {"from_unit": "inches", "to_unit": "centimeters", "factor": 2.54, "precision": 1},
    {"from_unit": "centimeters", "to_unit": "inches", "factor": 0.393701, "precision": 2},
    {"from_unit": "gallons", "to_unit": "liters", "factor": 3.78541, "precision": 1},
    {"from_unit": "liters", "to_unit": "gallons", "factor": 0.264172, "precision": 2},
    {"from_unit": "fahrenheit", "to_unit": "celsius", "special": "temp_f_to_c", "precision": 1},
    {"from_unit": "celsius", "to_unit": "fahrenheit", "special": "temp_c_to_f", "precision": 1}
]

@generator(BENCHMARK_CODE)
class UnitConversionGenerator(BenchmarkGenerator):
    """Generator for unit conversion benchmark questions."""
    
    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)
        
        # Configure strategy flags
        self.can_load_from_file = True  # Support loading from JSON files
        self.can_generate_locally = True  # Support generating locally with our algorithm
        self.can_generate_with_llm = False  # No need for LLM generation here
        
        # Set file paths for file-based generation
        self.questions_file_path = "conversions.json"
        
        # Preferred strategy order
        self.strategy_order = ["file", "local"]
        
        # Load conversion data
        self.conversions = self._load_conversion_data()
    
    def _load_conversion_data(self) -> List[Dict]:
        """Load conversion data from JSON file or use defaults."""
        try:
            # Use the base class's load_json_file method
            return self.load_json_file("conversions.json")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Couldn't load conversion data: {e}. Using defaults.")
            return DEFAULT_CONVERSIONS
    
    def _special_conversion(self, value: float, special_type: str) -> float:
        """Handle special conversions like temperature that aren't simple multiplication."""
        if special_type == "temp_f_to_c":
            return (value - 32) * 5/9
        elif special_type == "temp_c_to_f":
            return (value * 9/5) + 32
        else:
            logger.warning(f"Unknown special conversion type: {special_type}")
            return value
    
    def _get_value_range(self, unit: str) -> Tuple[float, float]:
        """Get a reasonable value range for a given unit."""
        ranges = {
            "pounds": (1, 500),
            "kilograms": (1, 200),
            "miles": (1, 1000),
            "kilometers": (1, 1000),
            "inches": (1, 100),
            "centimeters": (1, 200),
            "gallons": (1, 50),
            "liters": (1, 100),
            "fahrenheit": (-20, 120),
            "celsius": (-30, 50)
        }
        
        return ranges.get(unit, (1, 100))  # Default range if unit not found
    
    def _determine_difficulty(self, conversion: Dict) -> Difficulty:
        """Determine the difficulty of a conversion problem."""
        # Base difficulty on precision and whether it's special conversion
        if "special" in conversion:
            return Difficulty.MEDIUM
        elif conversion.get("precision", 1) > 1:
            return Difficulty.MEDIUM
        else:
            return Difficulty.EASY
    
    def _generate_conversion_question(self, conversion: Dict, value: Optional[float] = None) -> BenchmarkQuestion:
        """Helper method to generate a question from a conversion definition."""
        # Generate a random value if none provided
        if value is None:
            # Choose a reasonable range for the specific units
            min_val, max_val = self._get_value_range(conversion["from_unit"])
            value = round(random.uniform(min_val, max_val), 1)
        
        # Calculate the correct answer
        if "special" in conversion:
            correct_value = self._special_conversion(value, conversion["special"])
        else:
            correct_value = value * conversion["factor"]
        
        # Round to the specified precision
        precision = conversion.get("precision", 1)
        correct_value = round(correct_value, precision)
        
        # Format question text
        question_text = f"How many {conversion['to_unit']} is {value} {conversion['from_unit']}?"
        
        # Create evaluation criteria with tolerance
        # Special case for temperature - always allow 1-2 degree tolerance
        if conversion["from_unit"] in ["fahrenheit", "celsius"] or conversion["to_unit"] in ["fahrenheit", "celsius"]:
            # Fixed tolerance for temperature (1-2 degrees)
            tolerance = 1.5  
        else:
            # For other units, tolerance is relative to the value
            base_tolerance = 10**(-precision)  # Base precision
            relative_tolerance = abs(correct_value) * 0.01  # 1% relative tolerance
            tolerance = max(base_tolerance, relative_tolerance)
        
        eval_criteria = EvaluationCriteria(
            exact_match=False,
            tolerance=tolerance
        )
        
        return BenchmarkQuestion(
            question_text=question_text,
            answer_type=AnswerType.NUMERIC,
            correct_answer=correct_value,
            category="unit_conversion",
            difficulty=self._determine_difficulty(conversion),
            tags=[conversion["from_unit"], conversion["to_unit"]],
            evaluation_criteria=eval_criteria
        )
    
    def _generate_from_file(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """
        Generate questions from files.
        
        Yields:
            BenchmarkQuestion objects
        """
        try:
            # Try to load questions directly if they exist
            questions_data = self.load_json_file("questions.json")
            for item in questions_data:
                try:
                    question = BenchmarkQuestion(
                        question_text=item['question_text'],
                        answer_type=AnswerType(item['answer_type']),
                        correct_answer=item['correct_answer'],
                        category=item.get('category'),
                        difficulty=Difficulty(item['difficulty']) if 'difficulty' in item else None,
                        tags=item.get('tags', []),
                        evaluation_criteria=EvaluationCriteria(**item['evaluation_criteria']) 
                            if 'evaluation_criteria' in item else EvaluationCriteria()
                    )
                    yield question
                except (KeyError, ValueError) as e:
                    logger.warning(f"Error loading question from file: {e}")
                    continue
        except (FileNotFoundError, json.JSONDecodeError):
            # If no questions file exists, load conversion data and generate questions
            logger.info("No questions.json found, using conversion definitions to generate questions")
            conversion_data = self.conversions
            
            # Yield questions for each conversion type with a few different values
            for conversion in conversion_data:
                # Generate 3 questions per conversion type with different values
                for _ in range(3):
                    yield self._generate_conversion_question(conversion)
    
    def _generate_locally(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """
        Generate questions using local algorithms.
        
        Yields:
            BenchmarkQuestion objects
        """
        # We can generate an unlimited number of questions by randomly selecting
        # conversion types and values
        seen_questions = set()
        
        # Keep track of used conversion indices to cycle through all conversions
        conversion_indices = list(range(len(self.conversions)))
        random.shuffle(conversion_indices)
        
        # Use an infinitely cycling index
        idx = 0
        
        while True:
            # Get the next conversion definition
            conversion_idx = conversion_indices[idx % len(conversion_indices)]
            conversion = self.conversions[conversion_idx]
            
            # Generate a question with random values
            question = self._generate_conversion_question(conversion)
            
            # Skip duplicates
            question_key = (question.question_text, question.correct_answer)
            if question_key not in seen_questions:
                seen_questions.add(question_key)
                yield question
            
            # Advance to next conversion type
            idx += 1
            
            # Periodically clear the seen questions set to avoid memory issues
            # during long-running generation
            if len(seen_questions) > 1000:
                seen_questions.clear()