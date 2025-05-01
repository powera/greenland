#!/usr/bin/python3

import os

import datastore.common

def create_models():
  # create_ollama_models()
  create_lmstudio_models()
  create_remote_models()

def create_ollama_models():
  dir = os.path.dirname(os.path.realpath(__file__))

  s = datastore.common.create_database_and_session(os.path.join(dir, "benchmarks.db"))
  datastore.common.insert_model(s, "smollm2:1.7b:Q8_0", "SmolLM 2", "2024-10-31", 1800, "Apache License")
  #datastore.common.insert_model(s, "tulu3:8b:Q4_K_M", "Tulu 3", "2024-11-21", 4900, "Llama 3.1 License")
  #datastore.common.insert_model(s, "gemma2:9b:Q4_0", "Gemma 2", "2024-06-27", 5400, "Gemma License")
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
  #datastore.common.insert_model(s, "qwen2.5:1.5b:Q4_K_M", "QWEN25 Small", "2024-09-15", 986, "Apache License")
  datastore.common.insert_model(s, "qwen3:4b:Q4_K_M", "QWEN3 4B", "2025-04-28", 2600, "Apache License")

  # Remote models; the "size" parameter is synthetic
def create_remote_models():
  dir = os.path.dirname(os.path.realpath(__file__))
  s = datastore.common.create_database_and_session(os.path.join(dir, "benchmarks.db"))
  # ChatGPT
  datastore.common.insert_model(s, "gpt-4o-mini-2024-07-18", "GPT-4o-mini", "2024-07-18", 33000, "Closed Model")
  datastore.common.insert_model(s, "gpt-4.1-nano-2025-04-14", "GPT-4.1 nano", "2025-04-14", 20000, "Closed Model")
  datastore.common.insert_model(s, "gpt-4.1-mini-2025-04-14", "GPT-4.1 mini", "2025-04-14", 45000, "Closed Model")
  # Claude
  datastore.common.insert_model(s, "claude-3-haiku-20240307", "Claude 3 Haiku", "2024-03-07", 18000, "Closed Model")
  datastore.common.insert_model(s, "claude-3-5-haiku-20241022", "Claude 3.5 Haiku", "2024-10-22", 25000, "Closed Model")
  datastore.common.insert_model(s, "claude-3-7-sonnet-20250219", "Claude 3.7 Sonnet", "2025-02-19", 60000, "Closed Model")

  # Gemini
  datastore.common.insert_model(s, "gemini-2.5-flash-preview-04-17", "Gemini 2.5 Flash", "2025-04-17", 24000, "Closed Model")
  datastore.common.insert_model(s, "gemini-2.0-flash-lite", "Gemini 2.0 Flash", "2025-02-01", 20000, "Closed Model")
  datastore.common.insert_model(s, "gemini-1.5-flash-8b", "Gemini 1.5 Flash", "2024-10-01", 16000, "Closed Model")


def create_lmstudio_models():
  dir = os.path.dirname(os.path.realpath(__file__))
  s = datastore.common.create_database_and_session(os.path.join(dir, "benchmarks.db"))
  datastore.common.insert_model(s, "lmstudio/lmstudio-community/yi-1.5-6b-chat-gguf/yi-1.5-6b-chat-q4_k_m.gguf",
                                "Yi-1.5 6B", "2024-05-13", 3670, "Apache License")
  datastore.common.insert_model(s, "lmstudio/qwen2-7b-instruct",
                                "QWEN2 7B", "2024-06-07", 4300, "Apache License")
  datastore.common.insert_model(s, "lmstudio/lmstudio-community/qwen3-1.7b-gguf/qwen3-1.7b-q6_k.gguf",
                                "QWEN3 1.7B", "2025-04-28", 1670, "Apache License")
  datastore.common.insert_model(s, "lmstudio/lmstudio-community/qwen3-4b-gguf/qwen3-4b-q4_k_m.gguf",
                                "QWEN3 4B", "2025-04-28", 2500, "Apache License")
  datastore.common.insert_model(s, "lmstudio/lmstudio-community/qwen3-8b-gguf/qwen3-8b-q4_k_m.gguf",
                                "QWEN3 8B", "2025-04-28", 5030, "Apache License")
  datastore.common.insert_model(s, "lmstudio/llama-3.2-3b-instruct",
                                "Llama 3.2 3B", "2024-09-25", 1820, "Llama 3.2 License")
  datastore.common.insert_model(s, "lmstudio/granite-3.3-8b-instruct",
                                "Granite 3.3 8B", "2025-04-17", 4940, "Apache License")
  datastore.common.insert_model(s, "lmstudio/lmstudio-community/mistral-7b-instruct-v0.3-gguf/mistral-7b-instruct-v0.3-q4_k_m.gguf",
                                "Mistral 7B", "2023-09-27", 4370, "Apache License")
  datastore.common.insert_model(s, "lmstudio/lmstudio-community/gemma-3-4b-it-gguf/gemma-3-4b-it-q4_k_m.gguf",
                                "Gemma3 4B", "2025-03-10", 3340, "Apache License")
  datastore.common.insert_model(s, "lmstudio/lmstudio-community/SmolLM2-1.7B-Instruct-GGUF",
                                "SmolLM2 1.7B", "2024-10-31", 1060, "Apache License")

def main():
  create_models()

if __name__ == "__main__":
  create_models()
