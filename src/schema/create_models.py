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
  benchmarks.datastore.insert_model(s, "granite3-dense:8b:Q4_K_M", "Granite 3", "2024-10-21", 4900, "Apache License")
  benchmarks.datastore.insert_model(s, "hermes3:8b:Q4_0", "Hermes 3", "2024-07-28", 4700, "Llama 3 License")
  benchmarks.datastore.insert_model(s, "exaone3.5:7.8b:Q4_K_M", "ExaONE 3.5", "2024-12-10", 4800, "Exaone License")


  # Small models
  benchmarks.datastore.insert_model(session, "gemma2:2b:Q4_0", "Gemma2 Small", "2024-06-07", 1600, "Gemma License")

  # Remote models
  benchmarks.datastore.insert_model(session, "gpt-4o-mini-2024-07-18", "GPT-4o-mini", "2024-07-18", 2047, "Closed Model")

def create_benchmarks():
  dir = os.path.dirname(os.path.realpath(__file__))
  s = benchmarks.datastore.create_database_and_session(os.path.join(dir, "benchmarks.db"))

  benchmarks.datastore.insert_benchmark(
    s, "0015_spell_check", "Spell Check / Complete Response",
    "Given a sentence with one misspelled word, does the result identify the misspelled word and the correct spelling, in the requested format.", None)

  benchmarks.datastore.insert_benchmark(
    s, "0020_definitions", "Definitions",
    "Given a one-sentence definition and ten possible words, does the model choose the correct word.", None)

  benchmarks.datastore.insert_benchmark(
    s, "0030_analyze_paragraph", "Analyze Paragraph",
    "Given a paragraph and 4 possible answers for a question about that paragraph, does the model choose the correct answer.", None)

  benchmarks.datastore.insert_benchmark(
    s, "0035_simple_haystack", "Haystack Search",
    "Given six sentences and a question about one sentence, does the model chooset he correct answer.", None)

if __name__ == "__main__":
  create_models()
  create_benchmarks()
