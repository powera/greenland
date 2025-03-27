#!/usr/bin/python3

"""
Registry for various benchmarks.
"""

import logging
from lib.benchmarks.data_models import BenchmarkMetadata
from lib.benchmarks.factory import benchmark, register_runner

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


from lib.benchmarks.generators.unit_conversion_generator import UnitConversionGenerator
from lib.benchmarks.runners.unit_conversion_runner import UnitConversionRunner
@benchmark(code="0022_unit_conversion", name="Unit Conversion", description="""
           A benchmark to evaluate a model's ability to accurately convert 
           between different units of measurement.""")
class UnitConversionBenchmark:
    """Module container for unit conversion benchmark."""
    pass

from lib.benchmarks.generators.translations_generator import TranslationGenerator
from lib.benchmarks.runners.translations_runner import TranslationRunner
for codepair in ["en_fr", "en_zh", "sw_ko"]:
    benchmark_code = f"0050_translation_{codepair}"
    @benchmark(code=benchmark_code, name=f"Translation {codepair}", description="""
               A benchmark to evaluate a model's ability to translate 
               words from one language to another.""")
    class TranslationBenchmark:
        """Module container for spell check benchmark."""
        pass
    register_runner(benchmark_code, TranslationRunner)
