#!/usr/bin/python3
"""Populate the benchmark database with model definitions.

This script adds model entries to the benchmarks database for various
local and remote LLM models.
"""

import sys
from pathlib import Path

# Add src to path if not already present
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from benchmarks.benchmark_constants import BENCHMARKS_DB_PATH
from benchmarks.datastore import common as datastore_common


def create_models():
    """Create all model definitions."""
    create_remote_models()
    create_translategemma_models()


def create_remote_models():
    """Create remote API model definitions."""
    s = datastore_common.create_database_and_session(str(BENCHMARKS_DB_PATH))

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

    # Anthropic Claude
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
        "claude-sonnet-4-5",
        "Claude Sonnet 4.5",
        "2025-09-29",
        0,
        "Closed Model",
        "claude-sonnet-4-5-20250929",
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

    # Google Gemini
    datastore_common.insert_model(
        s,
        "gemini-2.5-pro",
        "Gemini 2.5 Pro",
        "2025-06-01",
        0,
        "Closed Model",
        "gemini-2.5-pro",
        "remote",
    )
    datastore_common.insert_model(
        s,
        "gemini-2.5-flash",
        "Gemini 2.5 Flash",
        "2025-06-01",
        0,
        "Closed Model",
        "gemini-2.5-flash",
        "remote",
    )
    datastore_common.insert_model(
        s,
        "gemini-2.5-flash-lite",
        "Gemini 2.5 Flash Lite",
        "2025-07-01",
        0,
        "Closed Model",
        "gemini-2.5-flash-lite",
        "remote",
    )

    # Ministral
    datastore_common.insert_model(
        s,
        "ministral-3-14b-lms",
        "Ministral 3 14B Reasoning (LMStudio)",
        "2025-10-01",
        9000,
        "Apache License",
        "lmstudio/mistralai/ministral-3-14b-reasoning",
        "local",
    )

    # Phi-4
    datastore_common.insert_model(
        s,
        "phi-4-14b-lms",
        "Phi-4 14B (LMStudio)",
        "2025-01-08",
        9100,
        "MIT License",
        "lmstudio/microsoft/phi-4",
        "local",
    )

    # Qwen3 VL
    datastore_common.insert_model(
        s,
        "qwen3-vl-8b-lms",
        "QWEN3 VL 8B (LMStudio)",
        "2025-05-20",
        5000,
        "Apache License",
        "lmstudio/qwen/qwen3-vl-8b",
        "local",
    )


def create_translategemma_models():
    """Create TranslateGemma model definitions."""
    s = datastore_common.create_database_and_session(str(BENCHMARKS_DB_PATH))

    datastore_common.insert_model(
        s,
        "translategemma-3-4b",
        "TranslateGemma 3 4B",
        "2025-03-12",
        4300,
        "Gemma License",
        "translategemma/translate-gemma-3-4b-it",
        "local",
    )


def main():
    create_models()


if __name__ == "__main__":
    create_models()
