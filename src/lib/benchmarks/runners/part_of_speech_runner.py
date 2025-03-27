#!/usr/bin/python3

"""Runner for part of speech benchmark."""

import json
import logging
import time
from typing import Dict, List, Optional, Any, Tuple

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.data_models import BenchmarkMetadata, BenchmarkResult
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@runner("0032_part_of_speech")
class PartOfSpeechRunner(BenchmarkRunner):
    """Runner for part of speech benchmark tests."""
    
    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """Initialize runner with model name and benchmark metadata."""
        super().__init__(model, metadata)
        
    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt and context for part of speech question.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        question_info = json.loads(question_data["question_info_json"])
        
        prompt = question_info["question_text"]
        schema = question_info.get("schema")
        
        # Create system context with instructions
        context = """
        You are a language expert tasked with identifying parts of speech in sentences.
        
        Analyze the sentence carefully and identify the part of speech of the specified word.
        
        Valid parts of speech include: noun, verb, adjective, adverb, pronoun, preposition, conjunction, interjection, and determiner.
        
        Provide a concise response with just the part of speech, following the provided schema.
        """
        
        return prompt, schema, context
        
    def run(self) -> int:
        """
        Execute the part of speech benchmark.
        
        Returns:
            Run ID of the saved results
        """
        # Initialize results
        results = []
        
        # Load questions from database
        questions = self.load_questions()
        logger.info("Running part of speech benchmark with %d questions on model %s", 
                   len(questions), self.model)
        
        # Warm up model (if needed)
        self.warm_up()
        
        # Process each question
        for question in questions:
            question_id = question["question_id"]
            logger.debug("Processing question: %s", question_id)
            
            # Prepare prompt and context
            prompt, schema, context = self.prepare_prompt(question)
            
            try:
                # Start timing
                start_time = time.time()
                
                # Generate response from model
                response = unified_client.generate_chat(
                    prompt=prompt,
                    model=self.remote_model,
                    json_schema=schema,
                    context=context
                )
                
                # End timing and convert to milliseconds
                eval_time_ms = int((time.time() - start_time) * 1000)
                
                # Extract structured response
                if schema:
                    model_answer = response.structured_data
                else:
                    model_answer = response.response_text
                
                # Load question info to get correct answer
                question_info = json.loads(question["question_info_json"])
                
                # Evaluate response
                is_correct = self.evaluate_response(question_info, model_answer)
                
                # Create result with score (100 if correct, 0 if incorrect)
                result = BenchmarkResult(
                    question_id=question_id,
                    score=100 if is_correct else 0,
                    eval_msec=eval_time_ms,
                    debug_json=json.dumps({
                        "prompt": prompt,
                        "model_answer": model_answer,
                        "expected_answer": question_info.get("correct_answer"),
                        "is_correct": is_correct
                    })
                )
                
            except OllamaTimeoutError as e:
                result = self.handle_timeout(question_id, e)
                
            except Exception as e:
                logger.error("Error processing question %s: %s", question_id, str(e))
                result = BenchmarkResult(
                    question_id=question_id,
                    score=0,
                    eval_msec=0,
                    debug_json=json.dumps({"error": str(e)})
                )
                
            results.append(result)
            
        # Calculate overall score and save results
        score = self.calculate_score(results)
        logger.info("Benchmark score for model %s: %d", self.model, score)
        
        # Save results to database
        run_id = self.save_results(score, results)
        
        return run_id

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if the model's part of speech identification is correct.
        
        Args:
            question_data: Question data from database
            response: Model response (format depends on benchmark)
            
        Returns:
            Boolean indicating whether response is correct
        """
        # Get expected answer
        correct_answer = question_data.get("correct_answer", {})
        expected_pos = correct_answer.get("part_of_speech", "").lower()
        
        # Get model's answer
        if isinstance(response, dict) and "part_of_speech" in response:
            model_pos = response["part_of_speech"].lower()
        else:
            # Try to extract from text response
            model_pos = str(response).lower()
            
        # Normalize common variations
        normalized_pos = model_pos.strip()
        
        # Handle common variations in responses
        if normalized_pos in ["noun", "nouns"]:
            normalized_pos = "noun"
        elif normalized_pos in ["verb", "verbs", "action verb"]:
            normalized_pos = "verb"
        elif normalized_pos in ["adjective", "adjectives", "adj", "adj."]:
            normalized_pos = "adjective"
        elif normalized_pos in ["adverb", "adverbs", "adv", "adv."]:
            normalized_pos = "adverb"
        elif normalized_pos in ["preposition", "prepositions", "prep", "prep."]:
            normalized_pos = "preposition"
        elif normalized_pos in ["conjunction", "conjunctions", "conj", "conj."]:
            normalized_pos = "conjunction"
        elif normalized_pos in ["pronoun", "pronouns", "pron", "pron."]:
            normalized_pos = "pronoun"
        elif normalized_pos in ["determiner", "determiners", "det", "det."]:
            normalized_pos = "determiner"
        elif normalized_pos in ["interjection", "interjections", "interj", "interj."]:
            normalized_pos = "interjection"
            
        # Check if the normalized answer matches the expected part of speech
        return normalized_pos == expected_pos
