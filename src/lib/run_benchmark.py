#!/usr/bin/python3
"""Runs benchmarks against language models."""

import logging
from typing import Dict, List, Set, Tuple, Optional
import datastore.benchmarks

from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.spell_check import SpellCheckBenchmark
from lib.benchmarks.definitions import DefinitionsBenchmark
from lib.benchmarks.paragraph_analysis import ParagraphAnalysisBenchmark
from lib.benchmarks.haystack import SimpleHaystackBenchmark
from lib.benchmarks.general_knowledge import GeneralKnowledgeBenchmark
from lib.benchmarks.translation import TranslationBenchmark

logger = logging.getLogger(__name__)

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
