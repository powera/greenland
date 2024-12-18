#!/usr/bin/python3

"""Base classes for implementing language model benchmarks."""

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

import datastore.benchmarks
from clients import unified_client, ollama_client
from telemetry import LLMUsage
import lib.score_table

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class BenchmarkResult:
    """Stores results and metadata for a benchmark run."""
    question_id: str
    score: int
    eval_msec: int
    debug_json: Optional[str] = None

class BenchmarkGenerator:
    """Base class for generating benchmark questions."""
    
    def __init__(self, session: Optional[Session] = None):
        """Initialize generator with optional database session."""
        self.session = session or datastore.benchmarks.create_dev_session()

    def save_question(self, question_id: str, benchmark_name: str, 
                     question_info: Dict[str, Any]) -> None:
        """Save generated question to database."""
        datastore.benchmarks.insert_question(
            self.session,
            question_id,
            benchmark_name,
            json.dumps(question_info)
        )

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

    def handle_timeout(self, question_id: str, error: ollama_client.OllamaTimeoutError) -> BenchmarkResult:
        """Handle timeout error and return appropriate benchmark result."""
        return BenchmarkResult(
            question_id=question_id,
            score=0,
            eval_msec=0,
            debug_json=json.dumps({"error": "Request timeout", "details": str(error)})
        )
