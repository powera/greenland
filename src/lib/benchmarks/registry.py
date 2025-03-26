#!/usr/bin/python3

"""
Registry for various benchmarks.
"""

import logging
from lib.benchmarks.data_models import BenchmarkMetadata
from lib.benchmarks.factory import benchmark

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import generator and runner to ensure they're registered
from lib.benchmarks.generators.spell_check_generator import SpellCheckGenerator
from lib.benchmarks.runners.spell_check_runner import SpellCheckRunner
# Register benchmark metadata
@benchmark(code="0015_spell_check", name="Spell Check", description="""
           A benchmark to evaluate a model's ability to identify 
           misspelled words in a sentence and provide their correct spelling.""")
class SpellCheckBenchmark:
    """Module container for spell check benchmark."""
    pass
