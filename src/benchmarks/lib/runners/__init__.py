#!/usr/bin/python3

"""Benchmark runners for evaluating language models."""

# Import all runners to register them with the factory
from benchmarks.lib.runners.antonym_runner import AntonymRunner
from benchmarks.lib.runners.definitions_runner import DefinitionsRunner
from benchmarks.lib.runners.word_to_ipa_runner import WordToIPARunner

# Knowledge questions
from benchmarks.lib.runners.geography_runner import GeographyRunner
from benchmarks.lib.runners.lemma_runner import LemmaRunner
from benchmarks.lib.runners.letter_count_runner import LetterCountRunner
from benchmarks.lib.runners.part_of_speech_runner import PartOfSpeechRunner
from benchmarks.lib.runners.pinyin_letter_count_runner import PinyinLetterCountRunner
from benchmarks.lib.runners.spell_check_runner import SpellCheckRunner
from benchmarks.lib.runners.synonyms_runner import SynonymsRunner
from benchmarks.lib.runners.translations_runner import TranslationRunner
from benchmarks.lib.runners.unit_conversion_runner import UnitConversionRunner
from benchmarks.lib.runners.time_arithmetic_runner import TimeArithmeticRunner
from benchmarks.lib.runners.word_length_runner import WordLengthRunner

from benchmarks.lib.runners.sentence_decomposition_runner import SentenceDecompositionRunner

from benchmarks.lib.runners.verb_forms_runner import VerbFormsRunner

# Agent regression benchmark runners
from benchmarks.lib.runners.validate_lemma_form_runner import ValidateLemmaFormRunner
from benchmarks.lib.runners.validate_definition_runner import ValidateDefinitionRunner
from benchmarks.lib.runners.validate_translation_runner import ValidateTranslationRunner

# Knowledge benchmarks 0152-0155
from benchmarks.lib.runners.syllogism_validity_runner import SyllogismValidityRunner
from benchmarks.lib.runners.book_author_match_runner import BookAuthorMatchRunner
from benchmarks.lib.runners.food_category_classification_runner import (
    FoodCategoryClassificationRunner,
)
from benchmarks.lib.runners.historical_event_year_runner import HistoricalEventYearRunner

from benchmarks.lib.runners.python_coding_runner import (
    PythonCoinChangeRunner,
    PythonGCDRunner,
    PythonHelloWorldRunner,
    PythonLetterFrequencyRunner,
    PythonPrimeFactorizationRunner,
)
