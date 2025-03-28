#!/usr/bin/python3

"""Base classes for implementing language model benchmarks."""

import json
import logging
import uuid
from typing import Dict, List, Optional, Any, Union, Tuple

import datastore.benchmarks
from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkResult, BenchmarkMetadata,
    AnswerType, Difficulty, EvaluationCriteria
)
import lib.score_table

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BenchmarkGenerator:
    """Base class for generating benchmark questions."""
    
    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """
        Initialize generator with benchmark metadata.
        
        Args:
            metadata: Benchmark metadata
            session: Optional database session
        """
        self.metadata = metadata
        self.session = session or datastore.benchmarks.create_dev_session()
        
        # Ensure benchmark exists in database
        success, msg = datastore.benchmarks.insert_benchmark(
            self.session,
            codename=self.metadata.code,
            displayname=self.metadata.name,
            description=self.metadata.description or self.__doc__
        )
        if not success and "already exists" not in msg:
            logger.error("Failed to create benchmark: %s", msg)

    def generate_question(self, *args, **kwargs) -> BenchmarkQuestion:
        """
        Generate a single benchmark question.
        
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement generate_question")

    def save_question(self, question: BenchmarkQuestion, custom_id: Optional[str] = None) -> str:
        """
        Save generated question to database with standardized ID format.
        
        Args:
            question: BenchmarkQuestion object
            custom_id: Optional custom ID suffix
            
        Returns:
            Generated question ID
        """
        # Generate standardized question ID
        if custom_id:
            question_id = f"{self.metadata.code}:{custom_id}"
        else:
            # Generate a unique identifier based on content
            unique_part = str(uuid.uuid4())[:8]
            question_id = f"{self.metadata.code}:{unique_part}"
        
        # Convert question to dictionary and save
        question_dict = question.to_dict()
        datastore.benchmarks.insert_question(
            self.session,
            question_id,
            self.metadata.code,
            json.dumps(question_dict)
        )
        
        return question_id
        
    def batch_save_questions(self, questions: List[BenchmarkQuestion], 
                            id_prefix: Optional[str] = None) -> List[str]:
        """
        Save multiple questions with sequential IDs.
        
        Args:
            questions: List of BenchmarkQuestion objects
            id_prefix: Optional prefix for the ID sequence
            
        Returns:
            List of generated question IDs
        """
        question_ids = []
        for idx, question in enumerate(questions):
            if id_prefix:
                custom_id = f"{id_prefix}:{idx}"
            else:
                custom_id = str(idx)
                
            question_id = self.save_question(question, custom_id)
            question_ids.append(question_id)
            
        return question_ids
    
    def load_to_database(self) -> None:
        """
        Load questions into database.
        
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement load_to_database")


class BenchmarkRunner:
    """Base class for running benchmarks against models."""
    
    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """
        Initialize benchmark runner with model name.
        
        Args:
            model: Name of the model to benchmark
            metadata: Benchmark metadata
        """
        self.model = model
        self.metadata = metadata
        
        # Handle quantization suffix in model names
        if "gpt-" in self.model or "claude-" in self.model:
            self.remote_model = self.model
        else:
            # Strip quantization suffix if present (e.g., ":Q4_0")
            self.remote_model = ":".join(model.split(":")[:-1])
            
        self.session = datastore.benchmarks.create_dev_session()
        
    def load_questions(self) -> List[Dict]:
        """Load benchmark questions from database."""
        return datastore.benchmarks.load_all_questions_for_benchmark(
            self.session, self.metadata.code
        )
        
    def warm_up(self) -> None:
        """Warm up model before running benchmark."""
        unified_client.warm_model(self.remote_model)

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt and context for the question.  Must be implemented by subclasses.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        raise NotImplementedError("Subclasses must implement run method")
        
    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if a response is correct according to question criteria.
        
        Args:
            question_data: Question data from database
            response: Model response (format depends on benchmark)
            
        Returns:
            Boolean indicating whether response is correct
        """
        answer_type = question_data.get("answer_type", AnswerType.FREE_TEXT.value)
        correct_answer = question_data.get("correct_answer")
        eval_criteria = question_data.get("evaluation_criteria", {})
        
        # Handle case where response is a dictionary with a single key
        # for the answer (common in structured responses)
        actual_response = response
        
        if answer_type == AnswerType.FREE_TEXT.value:
            # For free text, check based on evaluation criteria
            if eval_criteria.get("contains", False):
                return str(correct_answer).lower() in str(actual_response).lower()
            else:
                return str(actual_response).strip().lower() == str(correct_answer).strip().lower()
                
        elif answer_type == AnswerType.MULTIPLE_CHOICE.value:
            # For multiple choice, normalize strings
            if isinstance(actual_response, dict) and "answer" in actual_response:
                return actual_response["answer"].strip().lower() == str(correct_answer).strip().lower()
            else:
                return str(actual_response).strip().lower() == str(correct_answer).strip().lower()
                
        elif answer_type == AnswerType.JSON.value:
            # For JSON responses, check required fields
            if not isinstance(actual_response, dict):
                return False
                
            # Get required fields or use all fields in correct_answer
            required_fields = eval_criteria.get("required_fields", [])
            if not required_fields and isinstance(correct_answer, dict):
                required_fields = list(correct_answer.keys())
                
            for field in required_fields:
                if field not in actual_response or actual_response[field] != correct_answer[field]:
                    return False
            return True
            
        elif answer_type == AnswerType.BOOLEAN.value:
            # For boolean answers
            return str(actual_response).lower() in ("true", "false") and \
                   str(actual_response).lower() == str(correct_answer).lower()
                   
        elif answer_type == AnswerType.NUMERIC.value:
            # For numeric answers, check within tolerance
            try:
                tolerance = float(eval_criteria.get("tolerance", 0.0))
                actual_value = float(actual_response)
                expected_value = float(correct_answer)
                return abs(actual_value - expected_value) <= tolerance
            except (ValueError, TypeError):
                return False
        
        # Default fallback - exact match
        return str(actual_response).strip() == str(correct_answer).strip()
        
    def save_results(self, score: int, details: List[BenchmarkResult]) -> int:
        """
        Save benchmark results to database.
        
        Args:
            score: Overall benchmark score (0-100)
            details: List of individual question results
            
        Returns:
            Run ID of the saved results
        """
        success, run_id = datastore.benchmarks.insert_run(
            self.session, 
            self.model,
            self.metadata.code,
            score,
            run_details=[vars(d) for d in details]
        )
        
        if not success:
            logger.error("Error saving results: %s", run_id)
            return -1
            
        # Update score tables
        self._update_scoretable(run_id)
        return run_id
            
    def _update_scoretable(self, run_id: int) -> None:
        """Update score table with new results."""
        lib.score_table.generate_run_detail_by_id(run_id, self.session)
        lib.score_table.generate_dashboard(self.session)

    def handle_timeout(self, question_id: str, error: OllamaTimeoutError) -> BenchmarkResult:
        """Handle timeout error and return appropriate benchmark result."""
        logger.warning("Timeout occurred for question %s: %s", question_id, str(error))
        return BenchmarkResult(
            question_id=question_id,
            score=0,
            eval_msec=0,
            debug_json=json.dumps({"error": "Request timeout", "details": str(error)})
        )
        
    def calculate_score(self, results: List[BenchmarkResult]) -> int:
        """
        Calculate overall benchmark score from individual results.
        
        Args:
            results: List of BenchmarkResult objects
            
        Returns:
            Integer score from 0-100
        """
        if not results:
            return 0
            
        # Count correct answers (score of 100 means correct)
        correct_count = sum(1 for r in results if r.score == 100)
        total_count = len(results)
        
        # Calculate percentage
        score = (correct_count / total_count) * 100 if total_count > 0 else 0
        
        return int(score)
        
    def process_question(self, question: Dict) -> BenchmarkResult:
        """Process a single benchmark question."""
        question_data = json.loads(question["question_info_json"])
        question_id = question["question_id"]
        
        try:
            # Prepare the prompt
            prompt, schema, context = self.prepare_prompt(question_data)
            
            # Generate response
            response = unified_client.generate_chat(
                prompt=prompt,
                model=self.remote_model,
                json_schema=schema,
                context=context
            )
            
            # Evaluate response
            is_correct = self.evaluate_response(question_data, 
                                               schema and response.structured_data or response.response_text)
            
            # Build debug information
            debug_info = self.build_debug_info(question_data, response, is_correct)
            
            # Return benchmark result
            return BenchmarkResult(
                question_id=question_id,
                score=100 if is_correct else 0,
                eval_msec=int(response.usage.total_msec),
                debug_json=json.dumps(debug_info) if debug_info else None
            )
            
        except OllamaTimeoutError as e:
            return self.handle_timeout(question_id, e)
        except Exception as e:
            logger.error(f"Error processing question {question_id}: {str(e)}")
            return BenchmarkResult(
                question_id=question_id,
                score=0,
                eval_msec=0,
                debug_json=json.dumps({"error": str(e)})
            )
            
    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """Build debug information for benchmark results."""
        # Default implementation - subclasses can override
        if hasattr(response, 'structured_data') and response.structured_data:
            return {
                "response": response.structured_data,
                "expected": question_data.get("correct_answer"),
                "is_correct": is_correct
            }
        else:
            return {
                "response": response.response_text,
                "expected": question_data.get("correct_answer"),
                "is_correct": is_correct
            }
    

    def run(self) -> int:
        """Execute the benchmark and return the run ID."""
        # Load questions for this benchmark
        questions = self.load_questions()
        if not questions:
            logger.error(f"No questions found for benchmark {self.metadata.code}")
            return -1
            
        # Warm up the model
        logger.info(f"Warming up model {self.model}...")
        self.warm_up()
        
        # Process each question
        logger.info(f"Running {self.metadata.code} benchmark with {len(questions)} questions...")
        results = []
        for idx, question in enumerate(questions):
            logger.info(f"Processing question {idx+1}/{len(questions)}: {question['question_id']}")
            result = self.process_question(question)
            results.append(result)
            
        # Calculate score
        score = self.calculate_score(results)
        correct_count = sum(1 for r in results if r.score == 100)
        logger.info(f"Benchmark complete. Score: {score}/100 ({correct_count}/{len(results)} correct)")
        
        # Save results to database
        run_id = self.save_results(score, results)
        logger.info(f"Results saved with run ID: {run_id}")
        
        return run_id
