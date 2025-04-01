#!/usr/bin/python3

"""
Registry for various benchmarks.
"""

import logging
from lib.benchmarks.data_models import BenchmarkMetadata
from lib.benchmarks.factory import benchmark, register_generator, register_runner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Register benchmark metadata

from lib.benchmarks.generators.word_length_generator import WordLengthGenerator
from lib.benchmarks.runners.word_length_runner import WordLengthRunner
@benchmark(code="0011_word_length", name="Word Length", description="""
           A benchmark to evaluate a model's ability to count 
           the total number of letters in a given word.""")
class WordLengthBenchmark:
    """Module container for word length benchmark."""
    pass

from lib.benchmarks.generators.letter_count_generator import LetterCountGenerator
from lib.benchmarks.runners.letter_count_runner import LetterCountRunner
@benchmark(code="0012_letter_count", name="Letter Count", description="""
           A benchmark to evaluate a model's ability to count 
           how many times a specific letter appears in a word.""")
class LetterCountBenchmark:
    """Module container for letter count benchmark."""
    pass

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


from lib.benchmarks.generators.part_of_speech_generator import PartOfSpeechGenerator
from lib.benchmarks.runners.part_of_speech_runner import PartOfSpeechRunner
@benchmark(code="0032_part_of_speech", name="Part of Speech", description="""
           A benchmark to evaluate a model's ability to identify
           the part of speech of a specific word in a sentence.""")
class PartOfSpeechBenchmark:
    """Module container for part of speech benchmark."""
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
    register_generator(benchmark_code, TranslationGenerator)
    register_runner(benchmark_code, TranslationRunner)

from lib.benchmarks.generators.pinyin_letter_count_generator import PinyinLetterCountGenerator
from lib.benchmarks.runners.pinyin_letter_count_runner import PinyinLetterCountRunner
@benchmark(code="0051_pinyin_letters", 
           name="Pinyin Letter Count", 
           description="""A benchmark to evaluate a model's ability to count 
           how many times a specific letter appears in the Pinyin representation 
           of a Chinese sentence.""")
class PinyinLetterCountBenchmark:
    """Module container for Pinyin letter count benchmark."""
    pass


# Register the geography benchmark
from lib.benchmarks.generators.geography_generator import GeographyGenerator
from lib.benchmarks.runners.geography_runner import GeographyRunner
@benchmark(code="0120_geography", name="Geography Knowledge", description="""
           A benchmark to evaluate a model's knowledge of world geography through
           multiple-choice questions about countries, capitals, physical features,
           and other geographical information.""")
class GeographyBenchmark:
    """Module container for geography benchmark."""
    pass

register_generator("0120_geography", GeographyGenerator)
register_runner("0120_geography", GeographyRunner)