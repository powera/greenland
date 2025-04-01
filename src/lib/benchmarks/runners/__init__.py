#!/usr/bin/python3

"""Benchmark runners for evaluating language models."""

# Import all runners to register them with the factory
from lib.benchmarks.runners.antonym_runner import AntonymRunner
from lib.benchmarks.runners.definitions_runner import DefinitionsRunner 
from lib.benchmarks.runners.letter_count_runner import LetterCountRunner
from lib.benchmarks.runners.part_of_speech_runner import PartOfSpeechRunner
from lib.benchmarks.runners.pinyin_letter_count_runner import PinyinLetterCountRunner
from lib.benchmarks.runners.spell_check_runner import SpellCheckRunner
from lib.benchmarks.runners.translations_runner import TranslationRunner
from lib.benchmarks.runners.unit_conversion_runner import UnitConversionRunner
from lib.benchmarks.runners.word_length_runner import WordLengthRunner

# Knowledge questions
from lib.benchmarks.runners.geography_runner import GeographyRunner