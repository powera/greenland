#!/usr/bin/python3

import os

import datastore.common

def create_models():
  dir = os.path.dirname(os.path.realpath(__file__))

  s = datastore.common.create_database_and_session(os.path.join(dir, "benchmarks.db"))
  datastore.common.insert_model(s, "smollm2:1.7b:Q8_0", "SmolLM 2", "2024-10-31", 1800, "Apache License")
  #datastore.common.insert_model(s, "tulu3:8b:Q4_K_M", "Tulu 3", "2024-11-21", 4900, "Llama 3.1 License")
  datastore.common.insert_model(s, "gemma2:9b:Q4_0", "Gemma 2", "2024-06-27", 5400, "Gemma License")
  #datastore.common.insert_model(s, "mistral-nemo:12b:Q4_0", "Mistral Nemo", "2024-07-18", 7100, "Apache License")
  datastore.common.insert_model(s, "llama3.2:3b:Q4_K_M", "Llama 3.2", "2024-09-25", 2000, "Llama 3.2 License")
  datastore.common.insert_model(s, "qwen2.5:7b:Q4_K_M", "QWEN 2.5", "2024-09-15", 4700, "Apache License")
  #datastore.common.insert_model(s, "phi3.5:3.8b:Q4_0", "PHI 3.5", "2024-08-17", 2200, "MIT License")
  #datastore.common.insert_model(s, "granite3-dense:8b:Q4_K_M", "Granite 3", "2024-10-21", 4900, "Apache License")
  #datastore.common.insert_model(s, "hermes3:8b:Q4_0", "Hermes 3", "2024-07-28", 4700, "Llama 3 License")
  #datastore.common.insert_model(s, "exaone3.5:7.8b:Q4_K_M", "ExaONE 3.5", "2024-12-10", 4800, "Exaone License")
  datastore.common.insert_model(s, "phi4:14b:Q4_K_M", "Phi 4", "2025-01-08", 9100, "MIT License")
  datastore.common.insert_model(s, "gemma3:4b:Q4_K_M", "Gemma 3", "2025-03-12", 4300, "Gemma License")

  # Small models
  datastore.common.insert_model(s, "gemma3:1b:Q4_K_M", "Gemma 3 Small", "2025-03-12", 815, "Gemma License")
  datastore.common.insert_model(s, "gemma2:2b:Q4_0", "Gemma2 Small", "2024-06-07", 1600, "Gemma License")
  datastore.common.insert_model(s, "qwen2.5:1.5b:Q4_K_M", "QWEN25 Small", "2024-09-15", 986, "Apache License")

  # Remote models
  datastore.common.insert_model(s, "gpt-4o-mini-2024-07-18", "GPT-4o-mini", "2024-07-18", 2047, "Closed Model")

def create_benchmarks():
  dir = os.path.dirname(os.path.realpath(__file__))
  s = datastore.common.create_database_and_session(os.path.join(dir, "benchmarks.db"))

  datastore.common.insert_benchmark(
    s, "0015_spell_check", "Spell Check / Complete Response",
    "Given a sentence with one misspelled word, does the result identify the misspelled word and the correct spelling, in the requested format.", None)

  datastore.common.insert_benchmark(
    s, "0020_definitions", "Definitions",
    "Given a one-sentence definition and ten possible words, does the model choose the correct word.", None)

  datastore.common.insert_benchmark(
    s, "0030_analyze_paragraph", "Analyze Paragraph",
    "Given a paragraph and 4 possible answers for a question about that paragraph, does the model choose the correct answer.", None)

if __name__ == "__main__":
  create_models()
