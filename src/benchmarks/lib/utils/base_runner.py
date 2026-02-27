import json
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

import benchmarks.datastore.benchmarks as datastore_benchmarks
import benchmarks.datastore.common as datastore_common
import benchmarks.benchmark_constants as benchmark_constants
import benchmarks.validation
from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    BenchmarkResult,
    Difficulty,
    EvaluationCriteria,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_TOLERANCE = 0.01


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
        self.logger = logger  # TODO: don't use self

        self.session = datastore_benchmarks.create_dev_session()

        # Handle quantization suffix in model names
        # For remote API models, use the model codename as-is
        if "gpt-" in self.model or "claude-" in self.model or "gemini-" in self.model:
            self.remote_model = self.model
        else:
            # Check if this is an lmstudio model by looking up model_path in database
            model_info = datastore_common.get_model_by_codename(self.session, self.model)
            if model_info and model_info.get("model_path", "").startswith("lmstudio/"):
                # For lmstudio models, use the codename as-is (no quantization stripping)
                self.remote_model = self.model
            else:
                # For Ollama models, strip quantization suffix if present (e.g., ":Q4_0")
                self.remote_model = ":".join(model.split(":")[:-1])

    def load_questions(self) -> List[Dict]:
        """Load benchmark questions from database."""
        return datastore_benchmarks.load_all_questions_for_benchmark(
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
                return (
                    actual_response["answer"].strip().lower() == str(correct_answer).strip().lower()
                )
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
            return (
                str(actual_response).lower() in ("true", "false")
                and str(actual_response).lower() == str(correct_answer).lower()
            )

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
        success, run_id = datastore_benchmarks.insert_run(
            self.session,
            self.model,
            self.metadata.code,
            score,
            run_details=[vars(d) for d in details],
        )

        if not success:
            logger.error("Error saving results: %s", run_id)
            return -1

        return run_id

    def handle_timeout(self, question_id: str, error: OllamaTimeoutError) -> BenchmarkResult:
        """Handle timeout error and return appropriate benchmark result."""
        logger.warning("Timeout occurred for question %s: %s", question_id, str(error))
        return BenchmarkResult(
            question_id=question_id,
            score=0,
            eval_msec=0,
            debug_json=json.dumps({"error": "Request timeout", "details": str(error)}),
        )

    def _extract_error_text(self, result: BenchmarkResult) -> str:
        """Extract a normalized error string from benchmark debug metadata."""
        if not result.debug_json:
            return ""
        try:
            payload = json.loads(result.debug_json)
        except (TypeError, json.JSONDecodeError):
            return ""
        if not isinstance(payload, dict):
            return ""
        error = payload.get("error")
        return str(error).lower() if error else ""

    def _is_server_error(self, result: BenchmarkResult) -> bool:
        """Return True for transport/server failures (but not unexpected-response errors)."""
        error_text = self._extract_error_text(result)
        if not error_text:
            return False
        if "unexpected response" in error_text:
            return False
        server_markers = [
            "server error",
            "error 5",
            "http 5",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
            "connection refused",
            "connection aborted",
            "connection reset",
            "temporarily unavailable",
            "request timeout",
            "timed out",
        ]
        return any(marker in error_text for marker in server_markers)

    def _is_successful_result(self, result: BenchmarkResult) -> bool:
        """Return True when a question finished with a model response (correct or incorrect)."""
        return bool(result.eval_msec > 0 and not self._extract_error_text(result))

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
                prompt=prompt, model=self.remote_model, json_schema=schema, context=context
            )

            # Evaluate response
            is_correct = self.evaluate_response(
                question_data, schema and response.structured_data or response.response_text
            )

            # Build debug information
            debug_info = self.build_debug_info(question_data, response, is_correct)

            # Return benchmark result
            return BenchmarkResult(
                question_id=question_id,
                score=100 if is_correct else 0,
                eval_msec=int(response.usage.total_msec),
                debug_json=json.dumps(debug_info) if debug_info else None,
                thought_process=(
                    response.additional_thought if response.additional_thought else None
                ),
                cost_usd=response.usage.cost if response.usage else None,
            )

        except OllamaTimeoutError as e:
            return self.handle_timeout(question_id, e)
        except Exception as e:
            logger.error("Error processing question %s: %s", question_id, e)
            return BenchmarkResult(
                question_id=question_id,
                score=0,
                eval_msec=0,
                debug_json=json.dumps({"error": str(e)}),
            )

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """Build debug information for benchmark results."""
        # Default implementation - subclasses can override
        if hasattr(response, "structured_data") and response.structured_data:
            return {
                "response": response.structured_data,
                "expected": question_data.get("correct_answer"),
                "is_correct": is_correct,
            }
        else:
            return {
                "response": response.response_text,
                "expected": question_data.get("correct_answer"),
                "is_correct": is_correct,
            }

    def run_sample(self, num_questions: int = 5) -> List[BenchmarkResult]:
        """
        Run a small sample of the benchmark for testing purposes.

        Args:
            num_questions: Number of questions to sample

        Returns:
            List of benchmark results
        """
        # Load questions
        all_questions = self.load_questions()
        if not all_questions:
            self.logger.error("No questions found for benchmark %s", self.metadata.code)
            return []

        # Sample questions
        sample_questions = random.sample(all_questions, min(num_questions, len(all_questions)))

        # Process each question
        self.logger.info("Running sample of %d questions", len(sample_questions))
        results = []
        for question in sample_questions:
            result = self.process_question(question)
            results.append(result)

        # Calculate score
        score = self.calculate_score(results)
        correct_count = sum(1 for r in results if r.score == 100)
        self.logger.info(
            "Sample complete. Score: %d/100 (%d/%d correct)",
            score,
            correct_count,
            len(results),
        )

        return results

    def close(self) -> None:
        """Close the database session, returning the connection to the pool."""
        if self.session is not None:
            self.session.close()

    def run(self) -> int:
        """Execute the benchmark and return the run ID."""
        try:
            return self._run_inner()
        finally:
            self.close()

    def _run_inner(self) -> int:
        """Execute the benchmark (session lifetime managed by run())."""
        # Load questions for this benchmark
        questions = self.load_questions()
        if not questions:
            logger.error("No questions found for benchmark %s", self.metadata.code)
            return -1

        # Warm up the model
        logger.info("Warming up model %s...", self.model)
        self.warm_up()

        # Process each question
        logger.info(
            "Running %s benchmark with %d questions...",
            self.metadata.code,
            len(questions),
        )
        results = []
        server_error_count = 0
        aborted_for_server_errors = False
        for idx, question in enumerate(questions):
            logger.info(
                "Processing question %d/%d: %s",
                idx + 1,
                len(questions),
                question["question_id"],
            )
            result = self.process_question(question)
            results.append(result)

            if self._is_server_error(result):
                server_error_count += 1
                if server_error_count > 3:
                    logger.error(
                        "Aborting benchmark %s for model %s after %d server errors",
                        self.metadata.code,
                        self.model,
                        server_error_count,
                    )
                    aborted_for_server_errors = True
                    break

        if aborted_for_server_errors:
            logger.info("Unloading model %s after aborted run...", self.model)
            unified_client.unload_model(self.remote_model)
            return -1

        successful_results = [result for result in results if self._is_successful_result(result)]
        if not successful_results:
            logger.warning(
                "No successful responses for benchmark %s model %s; skipping database write",
                self.metadata.code,
                self.model,
            )
            logger.info("Unloading model %s...", self.model)
            unified_client.unload_model(self.remote_model)
            return -1

        # Calculate score
        score = self.calculate_score(results)
        correct_count = sum(1 for r in results if r.score == 100)
        logger.info(
            "Benchmark complete. Score: %d/100 (%d/%d correct)",
            score,
            correct_count,
            len(results),
        )

        # Save results to database
        run_id = self.save_results(score, results)
        logger.info("Results saved with run ID: %s", run_id)

        # Unload model to free memory for the next benchmark
        logger.info("Unloading model %s...", self.model)
        unified_client.unload_model(self.remote_model)

        return run_id
