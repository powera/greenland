#!/usr/bin/python3

import os

import benchmarks.datastore

def create_models():
  dir = os.path.dirname(os.path.realpath(__file__))

  s = benchmarks.datastore.create_database_and_session(os.path.join(dir, "benchmarks.db"))
  benchmarks.datastore.insert_model(s, "smollm2:1.7b:Q8_0", "SmolLM 2", "2024-10-31", 1800, "Apache License")
  benchmarks.datastore.insert_model(s, "tulu3:8b:Q4_K_M", "Tulu 3", "2024-11-21", 4900, "Llama 3.1 License")
  benchmarks.datastore.insert_model(s, "gemma2:9b:Q4_0", "Gemma 2", "2024-06-27", 5400, "Gemma License")
  benchmarks.datastore.insert_model(s, "mistral-nemo:12b:Q4_0", "Mistral Nemo", "2024-07-18", 7100, "Apache License")
  benchmarks.datastore.insert_model(s, "llama3.2:3b:Q4_K_M", "Llama 3.2", "2024-09-25", 2000, "Llama 3.2 License")
  benchmarks.datastore.insert_model(s, "qwen2.5:7b:Q4_K_M", "QWEN 2.5", "2024-09-15", 4700, "Apache License")
  benchmarks.datastore.insert_model(s, "phi3.5:3.8b:Q4_0", "PHI 3.5", "2024-08-17", 2200, "MIT License")

def create_benchmarks():
  dir = os.path.dirname(os.path.realpath(__file__))
  s = benchmarks.datastore.create_database_and_session(os.path.join(dir, "benchmarks.db"))

  benchmarks.datastore.insert_benchmark(
    s, "0015_spell_check:correct_word", "Spell Check / Correct Word",
    "Given a sentence with one misspelled word, does the result contain the correct spelling for that word?  It does not have to be formatted correctly or correctly transcribe the misspelled word.", None)

  benchmarks.datastore.insert_benchmark(
    s, "0015_spell_check:format", "Spell Check / Answer Format",
    "Given a sentence with one misspelled word, and a specified output format, does the result match that format -- regardless of whether the correct word is chosen.", None)

  benchmarks.datastore.insert_benchmark(
    s, "0015_spell_check:complete", "Spell Check / Complete Response",
    "Given a sentence with one misspelled word, does the result identify the misspelled word and the correct spelling, in the requested format.", None)

