#!/usr/bin/python3

import os

import benchmarks.datastore.common


def create_models():
    # create_ollama_models()
    create_lmstudio_models()
    create_remote_models()


def create_ollama_models():
    dir = os.path.dirname(os.path.realpath(__file__))

    s = datastore.common.create_database_and_session(os.path.join(dir, "benchmarks.db"))

    # Use clean codenames, store actual ollama model names in model_path
    datastore.common.insert_model(
        s,
        "smollm2-1.7b",
        "SmolLM 2 1.7B",
        "2024-10-31",
        1800,
        "Apache License",
        "smollm2:1.7b:Q8_0",
        "local",
    )
    datastore.common.insert_model(
        s,
        "llama3.2-3b",
        "Llama 3.2 3B",
        "2024-09-25",
        2000,
        "Llama 3.2 License",
        "llama3.2:3b:Q4_K_M",
        "local",
    )
    datastore.common.insert_model(
        s,
        "qwen2.5-7b",
        "QWEN 2.5 7B",
        "2024-09-15",
        4700,
        "Apache License",
        "qwen2.5:7b:Q4_K_M",
        "local",
    )
    datastore.common.insert_model(
        s, "phi4-14b", "Phi 4 14B", "2025-01-08", 9100, "MIT License", "phi4:14b:Q4_K_M", "local"
    )
    datastore.common.insert_model(
        s,
        "gemma3-4b",
        "Gemma 3 4B",
        "2025-03-12",
        4300,
        "Gemma License",
        "gemma3:4b:Q4_K_M",
        "local",
    )

    # Small models
    datastore.common.insert_model(
        s,
        "gemma3-1b",
        "Gemma 3 1B",
        "2025-03-12",
        815,
        "Gemma License",
        "gemma3:1b:Q4_K_M",
        "local",
    )
    datastore.common.insert_model(
        s, "gemma2-2b", "Gemma2 2B", "2024-06-07", 1600, "Gemma License", "gemma2:2b:Q4_0", "local"
    )
    datastore.common.insert_model(
        s, "qwen3-4b", "QWEN3 4B", "2025-04-28", 2600, "Apache License", "qwen3:4b:Q4_K_M", "local"
    )


def create_remote_models():
    dir = os.path.dirname(os.path.realpath(__file__))
    s = datastore.common.create_database_and_session(os.path.join(dir, "benchmarks.db"))

    # ChatGPT - use API model names as both codename and model_path
    datastore.common.insert_model(
        s,
        "gpt-4o-mini",
        "GPT-4o-mini",
        "2024-07-18",
        33000,
        "Closed Model",
        "gpt-4o-mini-2024-07-18",
        "remote",
    )
    datastore.common.insert_model(
        s,
        "gpt-4.1-nano",
        "GPT-4.1 nano",
        "2025-04-14",
        20000,
        "Closed Model",
        "gpt-4.1-nano-2025-04-14",
        "remote",
    )
    datastore.common.insert_model(
        s,
        "gpt-4.1-mini",
        "GPT-4.1 mini",
        "2025-04-14",
        45000,
        "Closed Model",
        "gpt-4.1-mini-2025-04-14",
        "remote",
    )

    # Claude
    datastore.common.insert_model(
        s,
        "claude-3-haiku",
        "Claude 3 Haiku",
        "2024-03-07",
        18000,
        "Closed Model",
        "claude-3-haiku-20240307",
        "remote",
    )
    datastore.common.insert_model(
        s,
        "claude-3.5-haiku",
        "Claude 3.5 Haiku",
        "2024-10-22",
        25000,
        "Closed Model",
        "claude-3-5-haiku-20241022",
        "remote",
    )
    datastore.common.insert_model(
        s,
        "claude-3.7-sonnet",
        "Claude 3.7 Sonnet",
        "2025-02-19",
        60000,
        "Closed Model",
        "claude-3-7-sonnet-20250219",
        "remote",
    )

    # Gemini
    datastore.common.insert_model(
        s,
        "gemini-2.5-flash",
        "Gemini 2.5 Flash",
        "2025-04-17",
        24000,
        "Closed Model",
        "gemini-2.5-flash-preview-04-17",
        "remote",
    )
    datastore.common.insert_model(
        s,
        "gemini-2.0-flash",
        "Gemini 2.0 Flash",
        "2025-02-01",
        20000,
        "Closed Model",
        "gemini-2.0-flash-lite",
        "remote",
    )
    datastore.common.insert_model(
        s,
        "gemini-1.5-flash",
        "Gemini 1.5 Flash",
        "2024-10-01",
        16000,
        "Closed Model",
        "gemini-1.5-flash-8b",
        "remote",
    )


def create_lmstudio_models():
    dir = os.path.dirname(os.path.realpath(__file__))
    s = datastore.common.create_database_and_session(os.path.join(dir, "benchmarks.db"))

    # Use clean codenames, store full LMStudio paths in model_path
    datastore.common.insert_model(
        s,
        "yi-1.5-6b",
        "Yi-1.5 6B",
        "2024-05-13",
        3670,
        "Apache License",
        "lmstudio/lmstudio-community/yi-1.5-6b-chat-gguf/yi-1.5-6b-chat-q4_k_m.gguf",
        "local",
    )
    datastore.common.insert_model(
        s,
        "granite-3.3-8b",
        "Granite 3.3 8B",
        "2025-04-17",
        4940,
        "Apache License",
        "lmstudio/granite-3.3-8b-instruct",
        "local",
    )

    # QWEN2 models
    datastore.common.insert_model(
        s,
        "qwen2-7b-lms",
        "QWEN2 7B (LMStudio)",
        "2024-06-07",
        4300,
        "Apache License",
        "lmstudio/qwen2-7b-instruct",
        "local",
    )
    datastore.common.insert_model(
        s,
        "qwen2.5-7b-lms",
        "QWEN2.5 7B (LMStudio)",
        "2024-09-19",
        4680,
        "Apache License",
        "lmstudio/lmstudio-community/qwen2.5-7b-instruct-1m-gguf/qwen2.5-7b-instruct-1m-q4_k_m.gguf",
        "local",
    )

    # QWEN3 Models
    datastore.common.insert_model(
        s,
        "qwen3-1.7b-lms",
        "QWEN3 1.7B (LMStudio)",
        "2025-04-28",
        1670,
        "Apache License",
        "lmstudio/lmstudio-community/qwen3-1.7b-gguf/qwen3-1.7b-q6_k.gguf",
        "local",
    )
    datastore.common.insert_model(
        s,
        "qwen3-4b-lms",
        "QWEN3 4B (LMStudio)",
        "2025-04-28",
        2500,
        "Apache License",
        "lmstudio/lmstudio-community/qwen3-4b-gguf/qwen3-4b-q4_k_m.gguf",
        "local",
    )
    datastore.common.insert_model(
        s,
        "qwen3-8b-lms",
        "QWEN3 8B (LMStudio)",
        "2025-04-28",
        5030,
        "Apache License",
        "lmstudio/lmstudio-community/qwen3-8b-gguf/qwen3-8b-q4_k_m.gguf",
        "local",
    )

    # Llama 3 Models
    datastore.common.insert_model(
        s,
        "llama3.2-1b-lms",
        "Llama 3.2 1B (LMStudio)",
        "2024-09-25",
        710,
        "Llama 3.2 License",
        "lmstudio/mlx-community/llama-3.2-1b-instruct",
        "local",
    )
    datastore.common.insert_model(
        s,
        "llama3.2-3b-lms",
        "Llama 3.2 3B (LMStudio)",
        "2024-09-25",
        1820,
        "Llama 3.2 License",
        "lmstudio/llama-3.2-3b-instruct",
        "local",
    )

    # Gemma2 Models
    datastore.common.insert_model(
        s,
        "gemma2-2b-lms",
        "Gemma2 2B (LMStudio)",
        "2024-06-27",
        2780,
        "Apache License",
        "lmstudio/lmstudio-community/gemma-2-2b-it-gguf/gemma-2-2b-it-q8_0.gguf",
        "local",
    )
    datastore.common.insert_model(
        s,
        "gemma2-9b-lms",
        "Gemma2 9B (LMStudio)",
        "2024-06-27",
        5760,
        "Apache License",
        "lmstudio/lmstudio-community/gemma-2-9b-it-gguf/gemma-2-9b-it-q4_k_m.gguf",
        "local",
    )

    # Gemma3 Models
    datastore.common.insert_model(
        s,
        "gemma3-4b-lms",
        "Gemma3 4B (LMStudio)",
        "2025-03-10",
        3340,
        "Apache License",
        "lmstudio/lmstudio-community/gemma-3-4b-it-gguf/gemma-3-4b-it-q4_k_m.gguf",
        "local",
    )
    datastore.common.insert_model(
        s,
        "gemma3-12b-lms",
        "Gemma3 12B QAT (LMStudio)",
        "2025-04-18",
        7740,
        "Apache License",
        "lmstudio/lmstudio-community/gemma-3-12b-it-qat-gguf/gemma-3-12b-it-qat-q4_0.gguf",
        "local",
    )

    datastore.common.insert_model(
        s,
        "smollm2-1.7b-lms",
        "SmolLM2 1.7B (LMStudio)",
        "2024-10-31",
        1060,
        "Apache License",
        "lmstudio/lmstudio-community/SmolLM2-1.7B-Instruct-GGUF",
        "local",
    )


def main():
    create_models()


if __name__ == "__main__":
    create_models()
