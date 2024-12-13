#!/usr/bin/python3
"""Runs benchmarks against language models."""

import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import benchmarks.datastore
from clients import ollama_client
import lib.score_table

@dataclass
class BenchmarkResult:
    """Stores results and metadata for a benchmark run."""
    question_id: str
    score: int
    eval_msec: int
    debug_json: Optional[str] = None

class BenchmarkRunner:
    """Base class for running benchmarks against models."""
    
    def __init__(self, model: str):
        """Initialize benchmark runner with model name."""
        self.model = model
        self.ollama_model = ":".join(model.split(":")[:-1])  # Strip quantization
        self.session = benchmarks.datastore.create_dev_session()
        
    def load_questions(self, benchmark: str) -> List[Dict]:
        """Load benchmark questions from database."""
        return benchmarks.datastore.load_all_questions_for_benchmark(self.session, benchmark)
        
    def warm_up(self):
        """Warm up model before running benchmark."""
        ollama_client.warm_model(self.ollama_model)
        
    def save_results(self, benchmark: str, score: int, details: List[BenchmarkResult]) -> None:
        """Save benchmark results to database."""
        success, run_id = benchmarks.datastore.insert_run(
            self.session, 
            self.model,
            benchmark,
            score,
            run_details=[vars(d) for d in details]
        )
        if not success:
            print(f"Error saving results: {run_id}")
        self._update_scoretable(run_id)
            
    def _update_scoretable(self, run_id: int) -> None:
        """Update score table with new results."""
        lib.score_table.generate_run_detail_by_id(run_id, self.session)
        lib.score_table.generate_dashboard(self.session)

class SpellCheckBenchmark(BenchmarkRunner):
    """Benchmark for testing spell checking abilities."""
    
    def __init__(self, model: str):
        super().__init__(model)
        self.context = """You are a spell checking assistant. For each sentence, identify:
1. The incorrectly spelled word exactly as it appears
2. The correct spelling of that word"""
        
        self.schema = {
            "type": "object",
            "properties": {
                "incorrect": {"type": "string"},
                "correct": {"type": "string"},
            },
            "required": ["incorrect", "correct"],
        }
    
    def run(self) -> None:
        """Execute the spell check benchmark."""
        questions = self.load_questions("0015_spell_check")
        self.warm_up()
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            prompt = f"What is the incorrectly-spelled word in this sentence: {info['sentence']}"
            
            _, structured_response, perf = ollama_client.generate_chat(
                prompt=prompt,
                model=self.ollama_model,
                json_schema=self.schema,
                context=self.context
            )
            
            is_correct = (info["incorrect"] == structured_response["incorrect"] and 
                         info["correct"] == structured_response["correct"])
            
            results.append(BenchmarkResult(
                question["question_id"],
                is_correct,
                perf["total_msec"],
                json.dumps(structured_response)
            ))

        score = sum(r.score for r in results)
        self.save_results("0015_spell_check", "accuracy", score, results)
        print(f"Correct: {score}/{len(questions)}")

class DefinitionsBenchmark(BenchmarkRunner):
    """Benchmark for testing word definition abilities."""

    def run(self) -> None:
        """Execute the definitions benchmark."""
        questions = self.load_questions("0020_definitions")
        self.warm_up()
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            free_response, _, perf = ollama_client.generate_chat(
                info["question"],
                self.ollama_model,
                brief=True
            )
            
            is_correct = free_response.strip().strip(".").lower() == info["correct"]
            results.append(BenchmarkResult(
                question["question_id"],
                is_correct,
                perf["total_msec"],
                None if is_correct else free_response
            ))
            
        score = sum(r.score for r in results)
        self.save_results("0020_definitions", "accuracy", score, results)
        print(f"Correct: {score}/{len(questions)}")

class ParagraphAnalysisBenchmark(BenchmarkRunner):
    """Benchmark for testing paragraph comprehension abilities."""
    
    def __init__(self, model: str):
        super().__init__(model)
        self.context = """You are a reading comprehension assistant. For each passage:
1. Analyze the text carefully
2. Select the best answer from the choices provided
3. Explain your reasoning"""
        
        self.schema = {
            "type": "object",
            "properties": {
                "commentary": {"type": "string"},
                "answer": {"type": "string", "minLength": 1, "maxLength": 1}
            },
            "required": ["commentary", "answer"]
        }
    
    def run(self) -> None:
        """Execute the paragraph analysis benchmark."""
        questions = self.load_questions("0030_analyze_paragraph")
        self.warm_up()
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            query = info["query"].removesuffix("\nAnswer: ")
            
            _, structured_response, perf = ollama_client.generate_chat(
                prompt=query,
                model=self.ollama_model,
                json_schema=self.schema,
                context=self.context
            )
            
            try:
                correct_letter = info["choices"][info["gold"]]
                is_correct = structured_response["answer"].upper() == correct_letter
                
                debug_info = {
                    "response": structured_response,
                    "correct_answer": correct_letter,
                    "question": query
                } if not is_correct else None
                
            except (KeyError, TypeError):
                is_correct = False
                debug_info = structured_response
                
            results.append(BenchmarkResult(
                question["question_id"],
                is_correct,
                perf["total_msec"],
                json.dumps(debug_info) if debug_info else None
            ))
            
        score = sum(r.score for r in results)
        self.save_results("0030_analyze_paragraph", "accuracy", score, results)
        print(f"Correct: {score}/{len(questions)}")

class SimpleHaystackBenchmark(BenchmarkRunner):
    """Benchmark for testing information retrieval abilities."""

    def __init__(self, model: str):
        super().__init__(model)
        self.context = """You are an information retrieval assistant. For each set of sentences:
1. Find the sentence containing the specified location
2. Identify the subject (person or entity) in that sentence"""
        
        self.schema = {
            "type": "object",
            "properties": {"subject": {"type": "string"}},
            "required": ["subject"]
        }

    def run(self) -> None:
        """Execute the simple haystack benchmark."""
        questions = self.load_questions("0035_simple_haystack")
        self.warm_up()
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            sentences = [f"{i+1}. {s}" for i, s in enumerate(info["sentences"])]
            
            prompt = f"""Given these sentences:
{chr(10).join(sentences)}

What is the subject for the sentence where the location is {info["correct"]["location"]}?"""

            _, structured_response, perf = ollama_client.generate_chat(
                prompt=prompt,
                model=self.ollama_model,
                json_schema=self.schema,
                context=self.context
            )
            
            try:
                is_correct = structured_response["subject"].lower() == info["correct"]["name"].lower()
            except KeyError:
                is_correct = False
                
            results.append(BenchmarkResult(
                question["question_id"],
                is_correct,
                perf["total_msec"],
                json.dumps(structured_response)
            ))
            
        score = sum(r.score for r in results)
        self.save_results("0035_simple_haystack", "accuracy", score, results)
        print(f"Correct: {score}/{len(questions)}")

class GeneralKnowledgeBenchmark(BenchmarkRunner):
    """Benchmark for testing general knowledge abilities."""

    def __init__(self, model: str):
        super().__init__(model)
        self.context = """You are a knowledgeable assistant providing concise, factual answers.
Respond with just the answer - do not include explanations or additional context."""
    
    def run(self) -> None:
        """Execute the general knowledge benchmark."""
        questions = self.load_questions("0040_general_knowledge")
        self.warm_up()
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            free_response, _, perf = ollama_client.generate_chat(
                prompt=info["context"],
                model=self.ollama_model,
                context=self.context
            )
            
            is_correct = info["continuation"] in free_response
            debug_info = None if is_correct else {
                "response": free_response,
                "expected": info["continuation"]
            }
            
            results.append(BenchmarkResult(
                question["question_id"],
                is_correct,
                perf["total_msec"],
                json.dumps(debug_info) if debug_info else None
            ))
            
        score = sum(r.score for r in results)
        self.save_results("0040_general_knowledge", "accuracy", score, results)
        print(f"Correct: {score}/{len(questions)}")

BENCHMARK_CLASSES = {
    "0015_spell_check": SpellCheckBenchmark,
    "0020_definitions": DefinitionsBenchmark, 
    "0030_analyze_paragraph": ParagraphAnalysisBenchmark,
    "0035_simple_haystack": SimpleHaystackBenchmark,
    "0040_general_knowledge": GeneralKnowledgeBenchmark
}

def get_all_model_codenames() -> List[str]:
    """Get list of all model codenames from database."""
    session = benchmarks.datastore.create_dev_session()
    return [x["codename"] for x in benchmarks.datastore.list_all_models(session)]

def get_all_benchmarks() -> List[str]:
    """Get list of all benchmark names from database."""
    session = benchmarks.datastore.create_dev_session()
    return [x["codename"] for x in benchmarks.datastore.list_all_benchmarks(session)]

def run_benchmark(benchmark_name: str, model: str) -> None:
    """Run a specific benchmark against a model."""
    benchmark_class = BENCHMARK_CLASSES.get(benchmark_name)
    if not benchmark_class:
        raise ValueError(f"Unknown benchmark: {benchmark_name}")
        
    benchmark = benchmark_class(model)
    benchmark.run()
