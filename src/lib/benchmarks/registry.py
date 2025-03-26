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

# Register benchmark metadata
from lib.benchmarks.generators.spell_check_generator import SpellCheckGenerator
from lib.benchmarks.runners.spell_check_runner import SpellCheckRunner
@benchmark(code="0015_spell_check", name="Spell Check", description="""
           A benchmark to evaluate a model's ability to identify 
           misspelled words in a sentence and provide their correct spelling.""")
class SpellCheckBenchmark:
    """Module container for spell check benchmark."""
    pass

from lib.benchmarks.generators.antonym_generator import AntonymGenerator
from lib.benchmarks.runners.antonym_runner import AntonymRunner
@benchmark(code="0016_antonym", name="Antonym Check", description="""
           A benchmark to evaluate a model's ability to identify 
           the antonym of a word.""")
class AntonymBenchmark:
    """Module container for spell check benchmark."""
    pass

from lib.benchmarks.generators.definitions_generator import DefinitionsGenerator
from lib.benchmarks.runners.definitions_runner import DefinitionsRunner
@benchmark(code="0020_definitions", name="Definitions", description="""
           A benchmark to evaluate a model's ability to identify 
           the correct definition of words.""")
class DefinitionsBenchmark:
    """Module container for spell check benchmark."""
