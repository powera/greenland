#!/usr/bin/python3

"""
Registry for various benchmarks.
"""

import logging

from benchmarks.lib.benchmarks.data_models import BenchmarkMetadata
from benchmarks.lib.benchmarks.factory import benchmark, register_generator, register_runner

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Register benchmark metadata

from benchmarks.lib.generators.word_length_generator import WordLengthGenerator
from benchmarks.lib.runners.word_length_runner import WordLengthRunner


@benchmark(
    code="0011_word_length",
    name="Word Length",
    description="""
           A benchmark to evaluate a model's ability to count 
           the total number of letters in a given word.""",
)
class WordLengthBenchmark:
    """Module container for word length benchmark."""

    pass


from benchmarks.lib.generators.letter_count_generator import LetterCountGenerator
from benchmarks.lib.runners.letter_count_runner import LetterCountRunner


@benchmark(
    code="0012_letter_count",
    name="Letter Count",
    description="""
           A benchmark to evaluate a model's ability to count 
           how many times a specific letter appears in a word.""",
)
class LetterCountBenchmark:
    """Module container for letter count benchmark."""

    pass


from benchmarks.lib.generators.spell_check_generator import SpellCheckGenerator
from benchmarks.lib.runners.spell_check_runner import SpellCheckRunner


@benchmark(
    code="0015_spell_check",
    name="Spell Check",
    description="""
           A benchmark to evaluate a model's ability to identify 
           misspelled words in a sentence and provide their correct spelling.""",
)
class SpellCheckBenchmark:
    """Module container for spell check benchmark."""

    pass


from benchmarks.lib.generators.antonym_generator import AntonymGenerator
from benchmarks.lib.runners.antonym_runner import AntonymRunner


@benchmark(
    code="0016_antonym",
    name="Antonym Check",
    description="""
           A benchmark to evaluate a model's ability to identify 
           the antonym of a word.""",
)
class AntonymBenchmark:
    """Module container for spell check benchmark."""

    pass


from benchmarks.lib.generators.definitions_generator import DefinitionsGenerator
from benchmarks.lib.runners.definitions_runner import DefinitionsRunner


@benchmark(
    code="0020_definitions",
    name="Definitions",
    description="""
           A benchmark to evaluate a model's ability to identify 
           the correct definition of words.""",
)
class DefinitionsBenchmark:
    """Module container for spell check benchmark."""


from benchmarks.lib.generators.unit_conversion_generator import UnitConversionGenerator
from benchmarks.lib.runners.unit_conversion_runner import UnitConversionRunner


@benchmark(
    code="0022_unit_conversion",
    name="Unit Conversion",
    description="""
           A benchmark to evaluate a model's ability to accurately convert 
           between different units of measurement.""",
)
class UnitConversionBenchmark:
    """Module container for unit conversion benchmark."""

    pass


from benchmarks.lib.generators.part_of_speech_generator import PartOfSpeechGenerator
from benchmarks.lib.runners.part_of_speech_runner import PartOfSpeechRunner


@benchmark(
    code="0032_part_of_speech",
    name="Part of Speech",
    description="""
           A benchmark to evaluate a model's ability to identify
           the part of speech of a specific word in a sentence.""",
)
class PartOfSpeechBenchmark:
    """Module container for part of speech benchmark."""

    pass


from benchmarks.lib.generators.lemma_generator import LemmaGenerator
from benchmarks.lib.runners.lemma_runner import LemmaRunner


@benchmark(
    code="0033_lemma",
    name="Lemma Identification",
    description="""
         A benchmark to evaluate a model's ability to identify the lemma (base form) 
         of a given word. The lemma is the dictionary form:
         - For nouns: the singular form (e.g., "cats" → "cat")
         - For verbs: the infinitive form without "to" (e.g., "running" → "run")
         - For adjectives: the positive form (e.g., "better" → "good")
         """,
)
class LemmaBenchmark:
    """Module container for lemma identification benchmark."""

    pass


# Register generator and runner
register_generator("0033_lemma", LemmaGenerator)
register_runner("0033_lemma", LemmaRunner)

from benchmarks.lib.generators.translations_generator import TranslationGenerator
from benchmarks.lib.runners.translations_runner import TranslationRunner

for codepair in ["en_fr", "en_zh", "sw_ko"]:
    benchmark_code = f"0050_translation_{codepair}"

    @benchmark(
        code=benchmark_code,
        name=f"Translation {codepair}",
        description="""
               A benchmark to evaluate a model's ability to translate 
               words from one language to another.""",
    )
    class TranslationBenchmark:
        """Module container for spell check benchmark."""

        pass

    register_generator(benchmark_code, TranslationGenerator)
    register_runner(benchmark_code, TranslationRunner)

from benchmarks.lib.generators.pinyin_letter_count_generator import (
    PinyinLetterCountGenerator,
)
from benchmarks.lib.runners.pinyin_letter_count_runner import PinyinLetterCountRunner


@benchmark(
    code="0051_pinyin_letters",
    name="Pinyin Letter Count",
    description="""A benchmark to evaluate a model's ability to count 
           how many times a specific letter appears in the Pinyin representation 
           of a Chinese sentence.""",
)
class PinyinLetterCountBenchmark:
    """Module container for Pinyin letter count benchmark."""

    pass


from benchmarks.lib.generators.english_to_ipa_generator import EnglishToIPAGenerator
from benchmarks.lib.runners.english_to_ipa_runner import EnglishToIPARunner


@benchmark(
    code="0061_english_to_ipa",
    name="English to IPA",
    description="""
           A benchmark to evaluate a model's ability to convert English words 
           to their IPA (International Phonetic Alphabet) pronunciation.""",
)
class EnglishToIPABenchmark:
    """Module container for English to IPA benchmark."""

    pass


# Register the generator and runner classes
register_generator("0061_english_to_ipa", EnglishToIPAGenerator)
register_runner("0061_english_to_ipa", EnglishToIPARunner)

# Register the geography benchmark
from benchmarks.lib.generators.geography_generator import GeographyGenerator
from benchmarks.lib.runners.geography_runner import GeographyRunner


@benchmark(
    code="0120_geography",
    name="Geography Knowledge",
    description="""
           A benchmark to evaluate a model's knowledge of world geography through
           multiple-choice questions about countries, capitals, physical features,
           and other geographical information.""",
)
class GeographyBenchmark:
    """Module container for geography benchmark."""

    pass


register_generator("0120_geography", GeographyGenerator)
register_runner("0120_geography", GeographyRunner)
