#!/usr/bin/python3

"""Main interface for running benchmarks."""

import logging
import traceback
from typing import Dict, List, Set, Tuple, Optional

import datastore.benchmarks
import datastore.common
from lib.benchmarks.factory import (
    get_runner, get_generator, get_all_benchmark_codes, 
    get_benchmark_metadata
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_all_model_codenames() -> List[str]:
    """
    Get a list of all model codenames from the database.
    
    Returns:
        List of model codenames
    """
    session = datastore.common.create_dev_session()
    models = datastore.common.list_all_models(session)
    return [model["codename"] for model in models]


def get_all_benchmarks() -> List[str]:
    """
    Get a list of all registered benchmark codes.
    
    Returns:
        List of benchmark codes
    """
    return get_all_benchmark_codes()


def run_benchmark(benchmark_code: str, model: str) -> Optional[int]:
    """
    Run a specific benchmark for a model.
    
    Args:
        benchmark_code: Benchmark code to run
        model: Model codename to benchmark
        
    Returns:
        Run ID if successful, None otherwise
    """
    logger.info("Running benchmark %s for model %s", benchmark_code, model)
    
    try:
        runner = get_runner(benchmark_code, model)
        if not runner:
            logger.error("Failed to create runner for benchmark %s", benchmark_code)
            return None
            
        # Execute the benchmark
        run_id = runner.run()
        
        logger.info("Benchmark %s completed for model %s (run_id=%s)", 
                   benchmark_code, model, run_id)
        return run_id
        
    except Exception as e:
        logger.error("Error running benchmark %s for model %s: %s", 
                    benchmark_code, model, str(e))
        logger.error(traceback.format_exc())
        return None


def run_missing_benchmarks(
    blacklist_models: Optional[Set[str]] = None, 
    blacklist_benchmarks: Optional[Set[str]] = None,
    session = None
) -> List[Tuple[str, str]]:
    """
    Run all benchmarks that don't have results yet.
    
    Args:
        blacklist_models: Optional set of models to exclude
        blacklist_benchmarks: Optional set of benchmarks to exclude
        session: Optional database session
        
    Returns:
        List of (model, benchmark) pairs that were run
    """
    if not session:
        session = datastore.common.create_dev_session()
        
    blacklist_models = blacklist_models or set()
    blacklist_benchmarks = blacklist_benchmarks or set()
    
    # Get all models and benchmarks
    models = [m for m in get_all_model_codenames() if m not in blacklist_models]
    benchmarks = [b for b in get_all_benchmarks() if b not in blacklist_benchmarks]
    
    # Get existing scores
    scores = datastore.benchmarks.get_highest_benchmark_scores(session)
    
    # Find missing benchmark/model combinations
    missing = []
    for benchmark in benchmarks:
        for model in models:
            if (benchmark, model) not in scores:
                missing.append((model, benchmark))
    
    # Run missing benchmarks
    run_pairs = []
    for model, benchmark in missing:
        logger.info("Running missing benchmark: %s for %s", benchmark, model)
        try:
            run_id = run_benchmark(benchmark, model)
            if run_id:
                run_pairs.append((model, benchmark))
        except Exception as e:
            logger.error("Failed to run %s for %s: %s", benchmark, model, str(e))
            logger.error(traceback.format_exc())
    
    return run_pairs


def generate_benchmark_questions(benchmark_code: str, session=None) -> bool:
    """
    Generate questions for a benchmark and load them into the database.
    
    Args:
        benchmark_code: Benchmark code
        session: Optional database session
        
    Returns:
        True if successful, False otherwise
    """
    logger.info("Generating questions for benchmark %s", benchmark_code)
    
    try:
        generator = get_generator(benchmark_code, session)
        if not generator:
            logger.error("Failed to create generator for benchmark %s", benchmark_code)
            return False
            
        # Generate and load questions
        generator.load_to_database()
        
        logger.info("Successfully generated questions for benchmark %s", benchmark_code)
        return True
        
    except Exception as e:
        logger.error("Error generating questions for benchmark %s: %s", 
                    benchmark_code, str(e))
        logger.error(traceback.format_exc())
        return False


def get_benchmark_info() -> List[Dict]:
    """
    Get information about all registered benchmarks.
    
    Returns:
        List of benchmark metadata dictionaries
    """
    result = []
    for code in get_all_benchmark_codes():
        metadata = get_benchmark_metadata(code)
        if metadata:
            result.append({
                "code": metadata.code,
                "name": metadata.name,
                "description": metadata.description,
                "version": metadata.version
            })
    return result


# Command-line interface if script is run directly
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run benchmarks for language models")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Run benchmark command
    run_parser = subparsers.add_parser("run", help="Run a benchmark")
    run_parser.add_argument("benchmark", help="Benchmark code")
    run_parser.add_argument("model", help="Model codename")
    
    # Generate questions command
    gen_parser = subparsers.add_parser("generate", help="Generate benchmark questions")
    gen_parser.add_argument("benchmark", help="Benchmark code")
    
    # List benchmarks command
    list_parser = subparsers.add_parser("list", help="List available benchmarks")
    
    # List models command
    models_parser = subparsers.add_parser("models", help="List available models")
    
    # Run missing benchmarks command
    missing_parser = subparsers.add_parser("missing", help="Run missing benchmarks")
    missing_parser.add_argument("--blacklist-models", nargs="+", help="Models to exclude")
    missing_parser.add_argument("--blacklist-benchmarks", nargs="+", help="Benchmarks to exclude")
    
    args = parser.parse_args()
    
    if args.command == "run":
        run_id = run_benchmark(args.benchmark, args.model)
        if run_id:
            print(f"Benchmark completed successfully. Run ID: {run_id}")
        else:
            print("Benchmark failed.")
            
    elif args.command == "generate":
        success = generate_benchmark_questions(args.benchmark)
        if success:
            print(f"Successfully generated questions for {args.benchmark}")
        else:
            print(f"Failed to generate questions for {args.benchmark}")
            
    elif args.command == "list":
        benchmarks = get_benchmark_info()
        print("Available benchmarks:")
        for benchmark in benchmarks:
            print(f"  {benchmark['code']}: {benchmark['name']}")
            if benchmark['description']:
                print(f"    {benchmark['description']}")
                
    elif args.command == "models":
        models = get_all_model_codenames()
        print("Available models:")
        for model in models:
            print(f"  {model}")
            
    elif args.command == "missing":
        blacklist_models = set(args.blacklist_models) if args.blacklist_models else set()
        blacklist_benchmarks = set(args.blacklist_benchmarks) if args.blacklist_benchmarks else set()
        
        run_pairs = run_missing_benchmarks(blacklist_models, blacklist_benchmarks)
        
        if run_pairs:
            print("Successfully ran the following benchmarks:")
            for model, benchmark in run_pairs:
                print(f"  {benchmark} for {model}")
        else:
            print("No missing benchmarks found or all runs failed.")
