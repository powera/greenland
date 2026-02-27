#!/usr/bin/python3
"""Populate the benchmark database with model definitions.

This script adds model entries to the benchmarks database for various
local and remote LLM models.
"""

import argparse
import sys
from pathlib import Path

# Add src to path if not already present
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from benchmarks.benchmark_constants import BENCHMARKS_DB_PATH
from benchmarks.config import BenchmarkConfig
from benchmarks.datastore import common as datastore_common


def _get_session(postgres_url=None):
    """Create a DB session, using postgres if a URL is provided."""
    if postgres_url:
        return datastore_common.create_postgres_session(postgres_url)
    return datastore_common.create_database_and_session(str(BENCHMARKS_DB_PATH))


def create_models(postgres_url=None):
    """Create all model definitions."""
    create_remote_models(postgres_url)
    create_local_models(postgres_url)


def create_remote_models(postgres_url=None):
    """Create remote API model definitions."""
    s = _get_session(postgres_url)

    # OpenAI GPT-5 family
    datastore_common.insert_model(
        s,
        "gpt-5.2",
        "GPT-5.2",
        "2025-12-11",
        0,
        "Closed Model",
        "gpt-5.2",
        "remote",
    )
    datastore_common.insert_model(
        s,
        "gpt-5-mini",
        "GPT-5 mini",
        "2025-08-07",
        0,
        "Closed Model",
        "gpt-5-mini",
        "remote",
    )
    datastore_common.insert_model(
        s,
        "gpt-5-nano",
        "GPT-5 nano",
        "2025-08-07",
        0,
        "Closed Model",
        "gpt-5-nano",
        "remote",
    )

    # Anthropic Claude 4.6
    datastore_common.insert_model(
        s,
        "claude-opus-4-6",
        "Claude Opus 4.6",
        "2026-02-05",
        0,
        "Closed Model",
        "claude-opus-4-6",
        "remote",
    )
    datastore_common.insert_model(
        s,
        "claude-sonnet-4-6",
        "Claude Sonnet 4.6",
        "2026-02-05",
        0,
        "Closed Model",
        "claude-sonnet-4-6",
        "remote",
    )
    datastore_common.insert_model(
        s,
        "claude-haiku-4-5",
        "Claude Haiku 4.5",
        "2025-10-01",
        0,
        "Closed Model",
        "claude-haiku-4-5-20251001",
        "remote",
    )


def create_local_models(postgres_url=None):
    """Create local (LMStudio) model definitions."""
    s = _get_session(postgres_url)

    # Qwen3 family (3 sizes)
    datastore_common.insert_model(
        s,
        "qwen3-1.7b-lms",
        "Qwen3 1.7B (LMStudio)",
        "2025-04-29",
        1100,
        "Apache License",
        "lmstudio/lmstudio-community/Qwen3-1.7B-GGUF",
        "local",
    )
    datastore_common.insert_model(
        s,
        "qwen3-4b-lms",
        "Qwen3 4B (LMStudio)",
        "2025-04-29",
        2800,
        "Apache License",
        "lmstudio/lmstudio-community/Qwen3-4B-GGUF",
        "local",
    )
    datastore_common.insert_model(
        s,
        "qwen3-vl-8b-lms",
        "Qwen3 VL 8B (LMStudio)",
        "2025-05-20",
        5000,
        "Apache License",
        "lmstudio/qwen/qwen3-vl-8b",
        "local",
    )

    # Meta Llama
    datastore_common.insert_model(
        s,
        "llama-3.2-1b-lms",
        "Llama 3.2 1B (LMStudio)",
        "2024-09-25",
        1300,
        "Llama License",
        "lmstudio/meta-llama/llama-3.2-1b-instruct",
        "local",
    )
    datastore_common.insert_model(
        s,
        "llama-3-8b-lms",
        "Llama 3 8B (LMStudio)",
        "2024-04-18",
        4900,
        "Llama License",
        "lmstudio/meta-llama/meta-llama-3-8b-instruct",
        "local",
    )

    # Other small models
    datastore_common.insert_model(
        s,
        "smollm2-1.7b-lms",
        "SmolLM2 1.7B (LMStudio)",
        "2024-11-01",
        1100,
        "Apache License",
        "lmstudio/HuggingFaceTB/smollm2-1.7b-instruct",
        "local",
    )
    datastore_common.insert_model(
        s,
        "gemma-2-2b-lms",
        "Gemma 2 2B (LMStudio)",
        "2024-06-27",
        1500,
        "Gemma License",
        "lmstudio/google/gemma-2-2b-it",
        "local",
    )
    datastore_common.insert_model(
        s,
        "granite-3.2-8b-lms",
        "Granite 3.2 8B (LMStudio)",
        "2025-02-26",
        4900,
        "Apache License",
        "lmstudio/ibm/granite-3.2-8b",
        "local",
    )

    # Mistral and AllenAI
    datastore_common.insert_model(
        s,
        "ministral-8b-lms",
        "Ministral 8B (LMStudio)",
        "2024-10-16",
        4900,
        "Mistral Research License",
        "lmstudio/mistralai/ministral-8b-instruct-2410",
        "local",
    )
    datastore_common.insert_model(
        s,
        "olmo-3-7b-lms",
        "OLMo 3 7B (LMStudio)",
        "2024-11-27",
        4300,
        "Apache License",
        "lmstudio/allenai/olmo-2-1124-7b-instruct",
        "local",
    )

    # 2024 flagship class (<=8B) models still available
    datastore_common.insert_model(
        s,
        "llama-3.1-8b-lms",
        "Llama 3.1 8B (LMStudio)",
        "2024-07-23",
        4900,
        "Llama License",
        "lmstudio/meta-llama/llama-3.1-8b-instruct",
        "local",
    )
    datastore_common.insert_model(
        s,
        "qwen2.5-7b-lms",
        "Qwen2.5 7B (LMStudio)",
        "2024-09-19",
        4300,
        "Apache License",
        "lmstudio/Qwen/Qwen2.5-7B-Instruct",
        "local",
    )
    datastore_common.insert_model(
        s,
        "phi-3.5-mini-lms",
        "Phi-3.5 Mini (LMStudio)",
        "2024-08-20",
        2500,
        "MIT License",
        "lmstudio/microsoft/phi-3.5-mini-instruct",
        "local",
    )


def main():
    parser = argparse.ArgumentParser(description="Populate benchmark DB with model definitions")
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Use PostgreSQL (Supabase) backend; reads keys/postgres.key",
    )
    parser.add_argument(
        "--db-url",
        help="Full PostgreSQL connection URL (overrides --postgres key-file lookup)",
    )
    args = parser.parse_args()

    postgres_url = None
    if args.db_url and args.db_url.startswith("postgresql://"):
        postgres_url = BenchmarkConfig.normalize_postgres_url(args.db_url)
    elif args.postgres:
        postgres_url = BenchmarkConfig.build_postgres_url()

    if postgres_url:
        print("Using storage backend: postgres (Supabase)")

    create_models(postgres_url)
    print("Done.")


if __name__ == "__main__":
    main()
