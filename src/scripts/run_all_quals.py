#!/usr/bin/python3

"""Run all qualification tests against all models in database."""

import logging
import argparse
from typing import List, Set, Optional
import benchmarks.datastore.quals
import benchmarks.datastore.common
import lib.run_quals

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_all_model_codenames(session) -> List[str]:
    """Get list of all model codenames from database."""
    return [x["codename"] for x in datastore.common.list_all_models(session)]


def get_completed_quals(session) -> Set[str]:
    """Get set of already completed model/test pairs."""
    results = datastore.quals.get_highest_qual_scores(session)
    return {f"{test}:{model}" for test, model in results.keys()}


def run_missing_quals(
    blacklist_models: Set[str] = None, target_model: Optional[str] = None
) -> None:
    """
    Run qualification tests for all model/test combinations not in database.

    Args:
        blacklist_models: Set of model codenames to never run
        target_model: Optional specific model to run tests for
    """
    session = datastore.quals.create_dev_session()

    # Initialize blacklist if not provided
    blacklist_models = blacklist_models or set()

    # Get all available models
    all_models = {
        model for model in get_all_model_codenames(session) if model not in blacklist_models
    }

    # Filter for target model if specified
    if target_model:
        if target_model not in all_models:
            logger.error(f"Model {target_model} not found in database")
            return
        all_models = {target_model}

    # Get already completed quals
    completed = get_completed_quals(session)

    # Try each combination
    for model in sorted(all_models):
        for test_type in lib.run_quals.QUAL_TEST_CLASSES:
            # Skip if already has a score
            if f"{test_type}:{model}" in completed:
                continue

            logger.info(f"Running {test_type} qualification test for model {model}")

            try:
                lib.run_quals.run_qual_test(test_type, model, save_to_db=True, session=session)
            except Exception as e:
                logger.error(f"Error running {test_type} for {model}: {str(e)}")
                continue


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run qualification tests for models")
    parser.add_argument("--model", help="Run tests for specific model only")
    args = parser.parse_args()

    logger.info("Starting qualification test runs")
    run_missing_quals(target_model=args.model)
    logger.info("Completed all qualification tests")


if __name__ == "__main__":
    main()
