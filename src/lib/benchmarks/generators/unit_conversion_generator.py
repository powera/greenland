#!/usr/bin/python3

"""Generator for unit conversion benchmark questions."""

import json
import logging
import os
import random
from typing import Dict, List, Optional, Any, Tuple

from lib.benchmarks.base import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkMetadata, AnswerType, Difficulty, EvaluationCriteria
)
from lib.benchmarks.factory import generator
import constants

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
        self.conversions = self._load_conversion_data()
        
    def _load_conversion_data(self) -> List[Dict]:
        """Load conversion data from JSON file or use defaults."""
        file_path = os.path.join(constants.BENCHMARK_DATA_DIR, 
                               "0022_unit_conversion", "conversions.json")
        
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    logger.info(f"Loading conversion data from {file_path}")
                    return json.load(f)
            else:
                logger.warning(f"Conversion file not found at {file_path}. Using defaults.")
                return DEFAULT_CONVERSIONS
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading conversion data: {e}. Using defaults.")
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
    
    def generate_question(self, conversion: Dict, value: Optional[float] = None) -> BenchmarkQuestion:
        """Generate a single unit conversion question."""
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
        # Tolerance is typically higher for larger values
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
    
    def load_to_database(self, num_questions: int = 40) -> List[str]:
        """Generate and load questions into the database."""
        questions = []
        question_ids = []
        
        # Ensure we generate a balanced mix of conversions
        cycles = (num_questions + len(self.conversions) - 1) // len(self.conversions)
        
        for _ in range(cycles):
            # Shuffle to get a mix of conversion types
            random.shuffle(self.conversions)
            for conversion in self.conversions:
                if len(questions) >= num_questions:
                    break
                questions.append(self.generate_question(conversion))
        
        # Save the questions to the database
        for i, question in enumerate(questions):
            question_id = self.save_question(question, f"q{i+1}")
            question_ids.append(question_id)
            logger.info(f"Created question {question_id}: {question.question_text}")
        
        return question_ids
