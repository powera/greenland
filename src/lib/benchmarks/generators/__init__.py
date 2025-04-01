#!/usr/bin/python3

"""Benchmark question generators."""

# Import all generators to register them with the factory
from lib.benchmarks.generators.antonym_generator import AntonymGenerator
from lib.benchmarks.generators.definitions_generator import DefinitionsGenerator
from lib.benchmarks.generators.letter_count_generator import LetterCountGenerator
from lib.benchmarks.generators.part_of_speech_generator import PartOfSpeechGenerator
from lib.benchmarks.generators.pinyin_letter_count_generator import PinyinLetterCountGenerator
from lib.benchmarks.generators.spell_check_generator import SpellCheckGenerator
from lib.benchmarks.generators.translations_generator import TranslationGenerator
from lib.benchmarks.generators.unit_conversion_generator import UnitConversionGenerator
from lib.benchmarks.generators.word_length_generator import WordLengthGenerator