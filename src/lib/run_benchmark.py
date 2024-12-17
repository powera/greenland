#!/usr/bin/python3
"""Runs benchmarks against language models."""

import json
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass

import datastore.benchmarks
from clients import unified_client
import lib.score_table

logger = logging.getLogger(__name__)

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
        if "gpt-4" in self.model:
          self.remote_model = self.model
        else:
          self.remote_model = ":".join(model.split(":")[:-1])  # Strip quantization
        self.session = datastore.benchmarks.create_dev_session()
        
    def load_questions(self, benchmark: str) -> List[Dict]:
        """Load benchmark questions from database."""
        return datastore.benchmarks.load_all_questions_for_benchmark(self.session, benchmark)
        
    def warm_up(self):
        """Warm up model before running benchmark."""
        unified_client.warm_model(self.remote_model)
        
    def save_results(self, benchmark: str, score: int, details: List[BenchmarkResult]) -> None:
        """Save benchmark results to database."""
        success, run_id = datastore.benchmarks.insert_run(
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
            
            _, structured_response, perf = unified_client.generate_chat(
                prompt=prompt,
                model=self.remote_model,
                json_schema=self.schema,
                context=self.context
            )
            
            is_correct = (info["incorrect"] == structured_response["incorrect"] and 
                         info["correct"] == structured_response["correct"])
            
            results.append(BenchmarkResult(
                question["question_id"],
                is_correct,
                int(perf.total_msec),
                json.dumps(structured_response)
            ))

        score = sum(r.score for r in results)
        self.save_results("0015_spell_check", score, results)
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
            free_response, _, perf = unified_client.generate_chat(
                info["question"],
                self.remote_model,
                brief=True
            )
            
            is_correct = free_response.strip().strip(".").lower() == info["correct"]
            results.append(BenchmarkResult(
                question["question_id"],
                is_correct,
                int(perf.total_msec),
                None if is_correct else free_response
            ))
            
        score = sum(r.score for r in results)
        self.save_results("0020_definitions", score, results)
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
            
            _, structured_response, perf = unified_client.generate_chat(
                prompt=query,
                model=self.remote_model,
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
                int(perf.total_msec),
                json.dumps(debug_info) if debug_info else None
            ))
            
        score = sum(r.score for r in results) * 10
        self.save_results("0030_analyze_paragraph", score, results)
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

            _, structured_response, perf = unified_client.generate_chat(
                prompt=prompt,
                model=self.remote_model,
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
                int(perf.total_msec),
                json.dumps(structured_response)
            ))
            
        score = 4 * sum(r.score for r in results)  # 25 questions
        self.save_results("0035_simple_haystack", score, results)
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
            free_response, _, perf = unified_client.generate_chat(
                prompt=info["context"],
                model=self.remote_model,
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
                int(perf.total_msec),
                json.dumps(debug_info) if debug_info else None
            ))
            
        score = sum(r.score for r in results)
        self.save_results("0040_general_knowledge", score, results)
        print(f"Correct: {score}/{len(questions)}")

class TranslationBenchmark(BenchmarkRunner):
    """Benchmark for testing language translation abilities."""
    
    def __init__(self, model: str, origin_lang: str, target_lang: str):
        """
        Initialize benchmark runner with model and language pair.
        
        Args:
            model: Name of the model to test
            origin_lang: Source language code (fr, de, ind, sw, ko, kn, zh)
            target_lang: Target language code (en, fr, de, ind, sw, ko, kn, zh)
        """
        super().__init__(model)
        self.origin_lang = origin_lang
        self.target_lang = target_lang
        
        # Validate language codes
        valid_langs = {'en', 'fr', 'de', 'ind', 'sw', 'ko', 'kn', 'zh'}
        if origin_lang not in valid_langs or target_lang not in valid_langs:
            raise ValueError(f"Language codes must be one of: {', '.join(valid_langs)}")
        if origin_lang == target_lang:
            raise ValueError("Origin and target languages must be different")
            
    @property
    def benchmark_codename(self) -> str:
        """Get unique benchmark codename for this language pair."""
        return f"0050_translation_{self.origin_lang}_{self.target_lang}"
    
    def run(self) -> None:
        """Execute the translation benchmark."""
        questions = self.load_questions(self.benchmark_codename)
        self.warm_up()
        
        schema = {
            "type": "object",
            "properties": {
                "translation": {"type": "string"}
            },
            "required": ["translation"]
        }
        
        # Set task context
        context = f"""You are helping with a language translation task.
When translating a word from {self.origin_lang.upper()} to {self.target_lang.upper()}:
- Provide the most direct and common translation
- Give only the base form of the word
- Do not include articles unless they are part of the standard translation
- Do not provide explanations or alternative translations"""
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            
            prompt = f"""Translate this word: "{info['word']}" """
            if info.get("choices"):
                prompt += f"\nPossible translations: {', '.join(info['choices'])}"

            _, structured_response, perf = unified_client.generate_chat(
                prompt,
                self.remote_model,
                json_schema=schema,
                context=context
            )
            
            try:
                translated = structured_response["translation"].lower().strip()
                
                # Get correct answer based on target language
                correct = info[self.target_lang].lower()
                
                # If choices are provided, validate against them
                if info.get("choices"):
                    is_correct = translated in [c.lower() for c in info["choices"]] and translated == correct
                else:
                    is_correct = translated == correct
                    
                debug_info = None if is_correct else {
                    "response": structured_response["translation"],
                    "expected": info[self.target_lang]
                }
                
                # Include any relevant usage details in debug info
                if debug_info and info.get("origin_details"):
                    debug_info["origin_word_details"] = info["origin_details"]
                if debug_info and info.get("target_details"):
                    debug_info["target_word_details"] = info["target_details"]
                    
            except (json.JSONDecodeError, KeyError):
                is_correct = False
                debug_info = structured_response
                
            results.append(BenchmarkResult(
                question["question_id"],
                is_correct,
                int(perf.total_msec),
                json.dumps(debug_info) if debug_info else None
            ))
            
        score = sum(r.score for r in results) * 2
        if score > 100: score=100  # 51 questions
        self.save_results(self.benchmark_codename, score, results)
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
    session = datastore.benchmarks.create_dev_session()
    return [x["codename"] for x in datastore.benchmarks.list_all_models(session)]

def get_all_benchmarks() -> List[str]:
    """Get list of all benchmark names from database."""
    session = datastore.benchmarks.create_dev_session()
    return [x["codename"] for x in datastore.benchmarks.list_all_benchmarks(session)]

def run_benchmark(benchmark_name: str, model: str) -> None:
    """Run a specific benchmark against a model."""
    
    # Handle translation benchmarks
    if benchmark_name.startswith("0050_translation_"):
        # Extract language codes from benchmark name
        origin_lang, target_lang = benchmark_name.split("_")[2:]
        benchmark = TranslationBenchmark(model, origin_lang, target_lang)
        benchmark.run()
        return
        
    # Handle other benchmark types
    benchmark_class = BENCHMARK_CLASSES.get(benchmark_name)
    if not benchmark_class:
        raise ValueError(f"Unknown benchmark: {benchmark_name}")
        
    benchmark = benchmark_class(model)
    benchmark.run()

def run_missing_benchmarks(
    blacklist_models: Optional[Set[str]] = None,
    blacklist_benchmarks: Optional[Set[str]] = None,
    session = None
) -> List[Tuple[str, str]]:
    """
    Run all benchmark/model combinations that aren't in the database.
    
    Args:
        blacklist_models: Set of model codenames to never run
        blacklist_benchmarks: Set of benchmark codenames to never run
        session: Optional database session (will create if None)
        
    Returns:
        List of (model, benchmark) pairs that were run
    
    Example:
        >>> run_missing_benchmarks(
        ...     blacklist_models={'unstable-model'},
        ...     blacklist_benchmarks={'expensive-benchmark'}
        ... )
    """
    if session is None:
        session = datastore.benchmarks.create_dev_session()
        
    # Initialize blacklists if not provided
    blacklist_models = blacklist_models or set()
    blacklist_benchmarks = blacklist_benchmarks or set()
    
    # Get all available models and benchmarks
    all_models = {
        model['codename'] for model in datastore.benchmarks.list_all_models(session)
        if model['codename'] not in blacklist_models
    }
    all_benchmarks = {
        bench['codename'] for bench in datastore.benchmarks.list_all_benchmarks(session)
        if bench['codename'] not in blacklist_benchmarks
    }
    
    # Get existing scores
    highest_scores = datastore.benchmarks.get_highest_benchmark_scores(session)
    
    # Track what we run
    combinations_run = []
    
    # Try each combination
    for model in sorted(all_models):
        for benchmark in sorted(all_benchmarks):
            # Skip if already has a score or is blacklisted
            if (benchmark, model) in highest_scores:
                continue
                
            logger.info(f"Running benchmark {benchmark} for model {model}")
            
            try:
                # Use the existing run_benchmark function
                run_benchmark(benchmark, model)
                combinations_run.append((model, benchmark))
                
            except Exception as e:
                logger.error(f"Error running {benchmark} for {model}: {str(e)}")
                continue
                
    return combinations_run
