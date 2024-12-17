#!/usr/bin/python3
"""Runs qualification tests to evaluate advanced query responses."""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
import json

from clients import unified_client
from telemetry import LLMUsage

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

EVALUATOR_MODEL = "gpt-4o-mini"

@dataclass
class QualResult:
    """Stores results and metadata for a qualification test run."""
    topic_id: str
    accuracy_score: int  # 0-10
    clarity_score: int   # 0-10
    completeness_score: int  # 0-10
    avg_score: int
    eval_msec: int
    response_text: str
    evaluation_text: str
    debug_json: Optional[str] = None

class QualTestRunner:
    """Base class for running qualification tests."""
    
    def __init__(self, model: str):
        """Initialize qualification test runner with model name."""
        self.model = model
        self.evaluator_model = EVALUATOR_MODEL
        self.topics: List[str] = []
        self.criteria: Dict[str, str] = {}
        
    def evaluate_response(
        self,
        topic: str,
        response: str,
        criteria: Dict[str, str]
    ) -> Tuple[Dict[str, int], str, LLMUsage]:
        """
        Evaluate a response using the evaluator model.
        
        Args:
            topic: The topic that was queried
            response: The response to evaluate
            criteria: Dictionary of criteria and their descriptions
            
        Returns:
            Tuple of (scores_dict, evaluation_text, usage_metrics)
        """
        context = f"""You are evaluating the quality of a response about: {topic}

Evaluate the response according to these criteria:
{chr(10).join(f'- {k}: {v}' for k, v in criteria.items())}

Score each criterion from 0-10 (10 being best) and provide a brief explanation."""

        schema = {
            "type": "object",
            "properties": {
                "accuracy_score": {"type": "integer", "minimum": 0, "maximum": 10},
                "clarity_score": {"type": "integer", "minimum": 0, "maximum": 10},
                "completeness_score": {"type": "integer", "minimum": 0, "maximum": 10},
                "explanation": {"type": "string"}
            },
            "required": ["accuracy_score", "clarity_score", "completeness_score", "explanation"]
        }

        prompt = f"""Evaluate this response:

{response}"""

        _, evaluation, usage = unified_client.generate_chat(
            prompt=prompt,
            model=self.evaluator_model,
            json_schema=schema,
            context=context
        )
        
        scores = {
            "accuracy": evaluation["accuracy_score"],
            "clarity": evaluation["clarity_score"],
            "completeness": evaluation["completeness_score"]
        }
        
        return scores, evaluation["explanation"], usage

    def run(self) -> List[QualResult]:
        """Execute the qualification tests."""
        if not self.topics or not self.criteria:
            raise ValueError("Topics and criteria must be defined in subclass")
            
        results = []
        
        for topic in self.topics:
            # Generate response using advanced query
            response, _, gen_usage = unified_client.generate_chat(
                topic,
                self.model,
                context="Provide a comprehensive analysis with accurate information and clear explanations."
            )
            
            # Evaluate the response
            scores, evaluation, eval_usage = self.evaluate_response(
                topic,
                response,
                self.criteria
            )
            
            # Calculate average score
            avg_score = sum(scores.values()) // len(scores)
            
            # Create result object
            result = QualResult(
                topic_id=topic,
                accuracy_score=scores["accuracy"],
                clarity_score=scores["clarity"],
                completeness_score=scores["completeness"],
                avg_score=avg_score,
                eval_msec=int(gen_usage.total_msec + eval_usage.total_msec),
                response_text=response,
                evaluation_text=evaluation,
                debug_json=json.dumps({
                    "generation_usage": gen_usage.to_dict(),
                    "evaluation_usage": eval_usage.to_dict()
                })
            )
            
            results.append(result)
            
        return results

class HistoricalAnalysisQual(QualTestRunner):
    """Qualification tests for historical analysis responses."""
    
    def __init__(self, model: str):
        super().__init__(model)
        self.topics = [
            "The causes and effects of the Industrial Revolution",
            "The impact of the printing press on medieval Europe",
            "The role of trade routes in ancient civilizations"
        ]
        self.criteria = {
            "accuracy": "Factual correctness and proper chronology",
            "clarity": "Clear organization and logical flow of ideas",
            "completeness": "Coverage of major events and their significance"
        }

class ScientificExplanationQual(QualTestRunner):
    """Qualification tests for scientific explanation responses."""
    
    def __init__(self, model: str):
        super().__init__(model)
        self.topics = [
            "The process of photosynthesis in plants",
            "How black holes form and evolve",
            "The mechanics of plate tectonics"
        ]
        self.criteria = {
            "accuracy": "Scientific accuracy and use of current understanding",
            "clarity": "Clear explanation of complex concepts",
            "completeness": "Coverage of key principles and mechanisms"
        }

class TechnicalAnalysisQual(QualTestRunner):
    """Qualification tests for technical analysis responses."""
    
    def __init__(self, model: str):
        super().__init__(model)
        self.topics = [
            "How public key encryption works",
            "The architecture of modern CPUs",
            "The principles of machine learning algorithms"
        ]
        self.criteria = {
            "accuracy": "Technical accuracy and proper terminology",
            "clarity": "Clear explanation of complex technical concepts",
            "completeness": "Coverage of key components and processes"
        }

# Map of qualification test types to their runner classes
QUAL_TEST_CLASSES = {
    "historical": HistoricalAnalysisQual,
    "scientific": ScientificExplanationQual,
    "technical": TechnicalAnalysisQual
}

def run_qual_test(test_type: str, model: str) -> List[QualResult]:
    """
    Run a specific qualification test against a model.
    
    Args:
        test_type: Type of qualification test to run
        model: Model to test
        
    Returns:
        List of QualResults for each topic
    """
    test_class = QUAL_TEST_CLASSES.get(test_type)
    if not test_class:
        raise ValueError(f"Unknown qualification test type: {test_type}")
        
    test = test_class(model)
    return test.run()
