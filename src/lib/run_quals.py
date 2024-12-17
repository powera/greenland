#!/usr/bin/python3
"""Runs qualification tests to evaluate advanced query responses."""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
import json

from clients import unified_client
from telemetry import LLMUsage
import datastore.quals
from advanced_queries import ResponseType, RESPONSE_CONFIGS

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

EVALUATOR_MODEL = "gpt-4o-mini"
TARGET_LENGTH = 500  # Standard length for all responses

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
    
    def __init__(self, model: str, session=None):
        """Initialize qualification test runner with model name."""
        self.model = model
        self.evaluator_model = EVALUATOR_MODEL
        self.topics: List[str] = []
        self.criteria: Dict[str, str] = {}
        self.session = session
        self.test_name = None  # Must be set by subclass
        self.response_type = None  # Must be set by subclass
        
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
                "explanation": {"type": "string"},
                "accuracy_score": {"type": "integer", "minimum": 0, "maximum": 10},
                "clarity_score": {"type": "integer", "minimum": 0, "maximum": 10},
                "completeness_score": {"type": "integer", "minimum": 0, "maximum": 10},
            },
            "required": ["explanation", "accuracy_score", "clarity_score", "completeness_score"]
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

    def run(self, save_to_db: bool = False) -> List[QualResult]:
        """Execute the qualification tests."""
        if not self.topics or not self.criteria or not self.test_name or not self.response_type:
            raise ValueError("Topics, criteria, test_name, and response_type must be defined in subclass")
            
        results = []
        total_score = 0
        
        config = RESPONSE_CONFIGS[self.response_type]
        for topic in self.topics:
            # Generate response using the appropriate response type configuration
            prompt = config.prompt_template.format(length=TARGET_LENGTH, topic=topic)
            response, _, gen_usage = unified_client.generate_chat(
                prompt,
                self.model,
                context=config.context_template.format(length=TARGET_LENGTH)
            )
            
            # Evaluate the response
            scores, evaluation, eval_usage = self.evaluate_response(
                topic,
                response,
                self.criteria
            )
            
            # Calculate average score
            avg_score = sum(scores.values()) // len(scores)
            total_score += avg_score
            
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
            
        # Save results to database if requested
        if save_to_db and self.session:
            overall_score = total_score / len(results)
            success, run_id = datastore.quals.insert_qual_run(
                self.session,
                self.model,
                self.test_name,
                overall_score,
                [vars(r) for r in results]
            )
            if not success:
                logger.error(f"Failed to save results to database: {run_id}")
            
        return results

class HistoricalAnalysisQual(QualTestRunner):
    """Qualification tests for historical analysis responses."""
    
    def __init__(self, model: str, session=None):
        super().__init__(model, session)
        self.test_name = "historical_analysis"
        self.response_type = ResponseType.HISTORICAL
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
    
    def __init__(self, model: str, session=None):
        super().__init__(model, session)
        self.test_name = "scientific_explanation"
        self.response_type = ResponseType.SCIENTIFIC
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
    
    def __init__(self, model: str, session=None):
        super().__init__(model, session)
        self.test_name = "technical_analysis"
        self.response_type = ResponseType.TECHNICAL
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

class BiographicalAnalysisQual(QualTestRunner):
    """Qualification tests for biographical analysis responses."""
    
    def __init__(self, model: str, session=None):
        super().__init__(model, session)
        self.test_name = "biographical_analysis"
        self.response_type = ResponseType.BIOGRAPHICAL
        self.topics = [
            "The life and achievements of Marie Curie",
            "Albert Einstein's contributions to physics",
            "Ada Lovelace's role in early computing"
        ]
        self.criteria = {
            "accuracy": "Biographical accuracy and proper timeline",
            "clarity": "Clear presentation of life events and achievements",
            "completeness": "Coverage of key life events and contributions"
        }

class LiteraryAnalysisQual(QualTestRunner):
    """Qualification tests for literary analysis responses."""
    
    def __init__(self, model: str, session=None):
        super().__init__(model, session)
        self.test_name = "literary_analysis"
        self.response_type = ResponseType.LITERARY
        self.topics = [
            "The plot and themes of 1984 by George Orwell",
            "The narrative structure of One Hundred Years of Solitude",
            "Character development in Pride and Prejudice"
        ]
        self.criteria = {
            "accuracy": "Accuracy of plot details and literary elements",
            "clarity": "Clear presentation of narrative elements",
            "completeness": "Coverage of key plot points and themes"
        }

class CulturalAnalysisQual(QualTestRunner):
    """Qualification tests for cultural analysis responses."""
    
    def __init__(self, model: str, session=None):
        super().__init__(model, session)
        self.test_name = "cultural_analysis"
        self.response_type = ResponseType.CULTURAL
        self.topics = [
            "The influence of jazz on American culture",
            "The role of tea ceremonies in Japanese society",
            "The impact of Renaissance art on European culture"
        ]
        self.criteria = {
            "accuracy": "Cultural accuracy and proper context",
            "clarity": "Clear explanation of cultural significance",
            "completeness": "Coverage of key cultural elements and impact"
        }

class AnalyticalResponseQual(QualTestRunner):
    """Qualification tests for analytical responses."""
    
    def __init__(self, model: str, session=None):
        super().__init__(model, session)
        self.test_name = "analytical_response"
        self.response_type = ResponseType.ANALYTICAL
        self.topics = [
            "The economic impact of automation on employment",
            "The effects of social media on political discourse",
            "The relationship between climate change and biodiversity"
        ]
        self.criteria = {
            "accuracy": "Analytical accuracy and evidence-based reasoning",
            "clarity": "Clear presentation of analysis and arguments",
            "completeness": "Coverage of key factors and implications"
        }

# Map of qualification test types to their runner classes
QUAL_TEST_CLASSES = {
    "historical": HistoricalAnalysisQual,
    "scientific": ScientificExplanationQual,
    "technical": TechnicalAnalysisQual,
    "biographical": BiographicalAnalysisQual,
    "literary": LiteraryAnalysisQual,
    "cultural": CulturalAnalysisQual,
    "analytical": AnalyticalResponseQual
}

def run_qual_test(test_type: str, model: str, save_to_db: bool = False, session=None) -> List[QualResult]:
    """
    Run a specific qualification test against a model.
    
    Args:
        test_type: Type of qualification test to run
        model: Model to test
        save_to_db: Whether to save results to database
        session: Optional database session (required if save_to_db is True)
        
    Returns:
        List of QualResults for each topic
    """
    test_class = QUAL_TEST_CLASSES.get(test_type)
    if not test_class:
        raise ValueError(f"Unknown qualification test type: {test_type}")
        
    if save_to_db and not session:
        session = datastore.quals.create_dev_session()
        
    test = test_class(model, session)
    return test.run(save_to_db)
