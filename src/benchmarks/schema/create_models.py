#!/usr/bin/python3
"""Populate the benchmark database with model definitions.

This script adds model entries to the benchmarks database for various
local and remote LLM models.

Terminology for insert_model parameters:
  codename     — short unique identifier used on CLI and in benchmark results
                 (e.g. "qwen3-4b-lms", "claude-opus-4-6")
  displayname  — human-readable label shown in dashboards / reports
  launch_date  — model release date (YYYY-MM-DD)
  filesize_mb  — approximate GGUF/on-disk size in MB (0 for remote API models)
  license_name — SPDX-style or short license name
  model_path   — identifier passed to the unified client to load/query the model.
                 For remote models this is the API model ID (e.g. "gpt-5.2").
                 For LMStudio local models it is "lmstudio/<org>/<model-name>";
                 the "lmstudio/" prefix selects the LMStudio backend and the
                 remainder (e.g. "meta-llama/llama-3.2-1b-instruct") is passed
                 directly to LMStudio's load/chat API.
  lmstudio_model_name — short model ID returned by LM Studio responses for local
                 models (e.g. "llama-2-7b").
  model_type   — "remote" (API) or "local" (LMStudio)
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

# Add src to path if not already present
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from benchmarks.benchmark_constants import BENCHMARKS_DB_PATH
from benchmarks.config import BenchmarkConfig
from benchmarks.datastore import common as datastore_common
from clients.lmstudio_client import LMStudioClient

# When True, _insert_lmstudio_model and insert_model calls use upsert semantics.
_UPDATE_MODE = False


def _model_write(session, **kwargs) -> None:
    """Insert or upsert a model depending on _UPDATE_MODE.

    Prints the result message from the datastore helper.
    """
    if _UPDATE_MODE:
        _ok, msg = datastore_common.upsert_model(session, **kwargs)
    else:
        _ok, msg = datastore_common.insert_model(session, **kwargs)
    print(msg)


LMSTUDIO_PREFIX = "lmstudio/"


def _get_session(postgres_url=None):
    """Create a DB session, using postgres if a URL is provided."""
    if postgres_url:
        return datastore_common.create_postgres_session(postgres_url)
    return datastore_common.create_database_and_session(str(BENCHMARKS_DB_PATH))


def _insert_lmstudio_model(
    session,
    *,
    codename: str,
    displayname: str,
    launch_date: str,
    filesize_mb: int,
    license_name: str,
    lmstudio_model: str,
    lmstudio_model_name: Optional[str] = None,
    max_benchmark_tier: int = 2,
) -> None:
    """Insert a local model that is served via LMStudio.

    Args:
        codename: Short unique ID for CLI / benchmark results (e.g. "qwen3-4b-lms").
        displayname: Human-readable name for dashboards (e.g. "Qwen3 4B (LMStudio)").
        launch_date: Model release date, YYYY-MM-DD.
        filesize_mb: Approximate on-disk size in MB.
        license_name: Short license identifier.
        lmstudio_model: The identifier LMStudio uses to load this model,
            e.g. "meta-llama/llama-3.2-1b-instruct". Stored in the DB as
            "lmstudio/<lmstudio_model>" so the unified client routes it to
            the LMStudio backend.
        lmstudio_model_name: Short identifier returned by LM Studio responses.
            If omitted, defaults to codename with a trailing "-lms" removed.
    """
    local_model_name = lmstudio_model_name or codename.removesuffix("-lms")

    _model_write(
        session,
        codename=codename,
        displayname=displayname,
        launch_date=launch_date,
        filesize_mb=filesize_mb,
        license_name=license_name,
        model_path=LMSTUDIO_PREFIX + lmstudio_model,
        lmstudio_model_name=local_model_name,
        model_type="local",
        max_benchmark_tier=max_benchmark_tier,
    )


def create_models(postgres_url=None):
    """Create all model definitions."""
    create_remote_models(postgres_url)
    create_local_models(postgres_url)


def create_remote_models(postgres_url=None):
    """Create remote API model definitions."""
    s = _get_session(postgres_url)

    # OpenAI GPT-5 family
    _model_write(
        s,
        codename="gpt-5.2",
        displayname="GPT-5.2",
        launch_date="2025-12-11",
        filesize_mb=0,
        license_name="Closed Model",
        model_path="gpt-5.2",
        model_type="remote",
    )
    _model_write(
        s,
        codename="gpt-5-mini",
        displayname="GPT-5 mini",
        launch_date="2025-08-07",
        filesize_mb=0,
        license_name="Closed Model",
        model_path="gpt-5-mini",
        model_type="remote",
    )
    _model_write(
        s,
        codename="gpt-5-nano",
        displayname="GPT-5 nano",
        launch_date="2025-08-07",
        filesize_mb=0,
        license_name="Closed Model",
        model_path="gpt-5-nano",
        model_type="remote",
    )

    # Anthropic Claude 4.6
    _model_write(
        s,
        codename="claude-opus-4-6",
        displayname="Claude Opus 4.6",
        launch_date="2026-02-05",
        filesize_mb=0,
        license_name="Closed Model",
        model_path="claude-opus-4-6",
        model_type="remote",
    )
    _model_write(
        s,
        codename="claude-sonnet-4-6",
        displayname="Claude Sonnet 4.6",
        launch_date="2026-02-05",
        filesize_mb=0,
        license_name="Closed Model",
        model_path="claude-sonnet-4-6",
        model_type="remote",
    )
    _model_write(
        s,
        codename="claude-haiku-4-5",
        displayname="Claude Haiku 4.5",
        launch_date="2025-10-01",
        filesize_mb=0,
        license_name="Closed Model",
        model_path="claude-haiku-4-5-20251001",
        model_type="remote",
    )


def create_local_models(postgres_url=None):
    """Create local (LMStudio) model definitions."""
    s = _get_session(postgres_url)

    # --- Qwen3 family (3 sizes) ---

    _insert_lmstudio_model(
        s,
        codename="qwen3-1.7b-lms",
        displayname="Qwen3 1.7B (LMStudio)",
        launch_date="2025-04-29",
        filesize_mb=1100,
        license_name="Apache License",
        lmstudio_model="lmstudio-community/Qwen3-1.7B-GGUF/Qwen3-1.7B-Q6_K.gguf",
    )
    _insert_lmstudio_model(
        s,
        codename="qwen3-4b-lms",
        displayname="Qwen3 4B (LMStudio)",
        launch_date="2025-04-29",
        filesize_mb=2800,
        license_name="Apache License",
        lmstudio_model="lmstudio-community/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf",
    )
    _insert_lmstudio_model(
        s,
        codename="qwen3-vl-8b-lms",
        displayname="Qwen3 VL 8B (LMStudio)",
        launch_date="2025-05-20",
        filesize_mb=5000,
        license_name="Apache License",
        lmstudio_model="qwen/qwen3-vl-8b",
    )

    # --- Meta Llama ---

    _insert_lmstudio_model(
        s,
        codename="llama-2-7b-lms",
        displayname="Llama 2 7B (LMStudio)",
        launch_date="2023-07-18",
        filesize_mb=4900,
        license_name="Llama License",
        lmstudio_model="TheBloke/Llama-2-7B-GGUF/llama-2-7b.Q4_K_S.gguf",
        lmstudio_model_name="llama-2-7b",
        max_benchmark_tier=1,
    )
    _insert_lmstudio_model(
        s,
        codename="llama-3.2-1b-lms",
        displayname="Llama 3.2 1B (LMStudio)",
        launch_date="2024-09-25",
        filesize_mb=1300,
        license_name="Llama License",
        lmstudio_model="bartowski/Llama-3.2-1B-Instruct-GGUF/Llama-3.2-1B-Instruct-Q8_0.gguf",
        max_benchmark_tier=1,
    )
    _insert_lmstudio_model(
        s,
        codename="llama-3-8b-lms",
        displayname="Llama 3 8B (LMStudio)",
        launch_date="2024-04-18",
        filesize_mb=4900,
        license_name="Llama License",
        lmstudio_model="lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF/Meta-Llama-3-8B-Instruct-Q4_K_M.gguf",
    )

    # --- Other small models ---

    _insert_lmstudio_model(
        s,
        codename="smollm2-1.7b-lms",
        displayname="SmolLM2 1.7B (LMStudio)",
        launch_date="2024-11-01",
        filesize_mb=1100,
        license_name="Apache License",
        lmstudio_model="HuggingFaceTB/SmolLM2-1.7B-Instruct-GGUF/smollm2-1.7b-instruct-q4_k_m.gguf",
        max_benchmark_tier=1,
    )
    _insert_lmstudio_model(
        s,
        codename="gemma-2b-lms",
        displayname="Gemma 2B (LMStudio)",
        launch_date="2024-02-21",
        filesize_mb=1500,
        license_name="Gemma License",
        lmstudio_model="codegood/gemma-2b-it-Q4_K_M-GGUF/gemma-2b-it.Q4_K_M.gguf",
        max_benchmark_tier=1,
    )
    _insert_lmstudio_model(
        s,
        codename="gemma-2-2b-lms",
        displayname="Gemma 2 2B (LMStudio)",
        launch_date="2024-06-27",
        filesize_mb=1500,
        license_name="Gemma License",
        lmstudio_model="mlx-community/gemma-2-2b-it-4bit",
    )
    _insert_lmstudio_model(
        s,
        codename="granite-3.2-8b-lms",
        displayname="Granite 3.2 8B (LMStudio)",
        launch_date="2025-02-26",
        filesize_mb=4900,
        license_name="Apache License",
        lmstudio_model="ibm/granite-3.2-8b",
    )

    # --- Mistral and AllenAI ---

    _insert_lmstudio_model(
        s,
        codename="ministral-8b-lms",
        displayname="Ministral 8B (LMStudio)",
        launch_date="2024-10-16",
        filesize_mb=4900,
        license_name="Mistral Research License",
        lmstudio_model="bartowski/Ministral-8B-Instruct-2410-GGUF/Ministral-8B-Instruct-2410-Q4_K_S.gguf",
    )
    _insert_lmstudio_model(
        s,
        codename="olmo-3-7b-lms",
        displayname="OLMo 3 7B (LMStudio)",
        launch_date="2024-11-27",
        filesize_mb=4300,
        license_name="Apache License",
        lmstudio_model="lmstudio-community/Olmo-3-7B-Instruct-GGUF/Olmo-3-7B-Instruct-Q4_K_M.gguf",
    )

    # --- 2024 flagship class (<=8B) models ---

    _insert_lmstudio_model(
        s,
        codename="llama-3.1-8b-lms",
        displayname="Llama 3.1 8B (LMStudio)",
        launch_date="2024-07-23",
        filesize_mb=4900,
        license_name="Llama License",
        lmstudio_model="lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    )
    _insert_lmstudio_model(
        s,
        codename="qwen2.5-7b-lms",
        displayname="Qwen2.5 7B (LMStudio)",
        launch_date="2024-09-19",
        filesize_mb=4300,
        license_name="Apache License",
        lmstudio_model="Qwen/Qwen2.5-7B-Instruct",
    )
    _insert_lmstudio_model(
        s,
        codename="phi-3.5-mini-lms",
        displayname="Phi-3.5 Mini (LMStudio)",
        launch_date="2024-08-20",
        filesize_mb=2500,
        license_name="MIT License",
        lmstudio_model="mlx-community/Phi-3.5-mini-instruct-4bit",
        max_benchmark_tier=1,
    )

    # --- Larger models (>8B) ---

    _insert_lmstudio_model(
        s,
        codename="phi-4-lms",
        displayname="Phi-4 (LMStudio)",
        launch_date="2024-12-12",
        filesize_mb=9100,
        license_name="MIT License",
        lmstudio_model="microsoft/phi-4",
        lmstudio_model_name="microsoft/phi-4",
    )
    _insert_lmstudio_model(
        s,
        codename="gemma-2-9b-lms",
        displayname="Gemma 2 9B (LMStudio)",
        launch_date="2024-06-27",
        filesize_mb=5800,
        license_name="Gemma License",
        lmstudio_model="google/gemma-2-9b",
        lmstudio_model_name="google/gemma-2-9b",
    )
    _insert_lmstudio_model(
        s,
        codename="gemma-3-12b-lms",
        displayname="Gemma 3 12B (LMStudio)",
        launch_date="2025-03-12",
        filesize_mb=8100,
        license_name="Gemma License",
        lmstudio_model="google/gemma-3-12b",
        lmstudio_model_name="google/gemma-3-12b",
    )


def request_lmstudio_install_for_local_models(postgres_url=None):
    """Request LMStudio to install local models from the benchmark model table.

    Installs models serially to avoid LMStudio timeouts from parallel downloads.
    """
    s = _get_session(postgres_url)
    lmstudio_client = LMStudioClient(debug=False)

    local_models = [
        model
        for model in datastore_common.list_all_models(s)
        if model.get("model_type") == "local"
        and isinstance(model.get("model_path"), str)
        and model["model_path"].startswith(LMSTUDIO_PREFIX)
    ]

    if not local_models:
        print("No LMStudio local models found in benchmark model table.")
        return

    print(f"Requesting LMStudio install for {len(local_models)} model(s), serially...")

    installed_count = 0
    failed_models = []

    for index, model in enumerate(local_models, start=1):
        model_path = model["model_path"]
        # Strip the "lmstudio/" routing prefix to get the identifier
        # that LMStudio's load API expects.
        lmstudio_identifier = model_path[len(LMSTUDIO_PREFIX) :]
        codename = model["codename"]

        print(f"[{index}/{len(local_models)}] Installing {codename}: {lmstudio_identifier}")
        was_loaded = lmstudio_client.warm_model(lmstudio_identifier)

        if was_loaded:
            installed_count += 1
            lmstudio_client.unload_model(lmstudio_identifier)
        else:
            failed_models.append(codename)

    print(f"LMStudio install requests complete: {installed_count}/{len(local_models)} succeeded")
    if failed_models:
        print(f"Failed installs: {', '.join(failed_models)}")


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
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update existing model entries instead of skipping them (upsert mode)",
    )
    parser.add_argument(
        "--install-local-lmstudio",
        action="store_true",
        help="Request LMStudio to install all local models in the benchmark DB (serially)",
    )
    args = parser.parse_args()

    global _UPDATE_MODE
    _UPDATE_MODE = args.update

    postgres_url = None
    if args.db_url and args.db_url.startswith("postgresql://"):
        postgres_url = BenchmarkConfig.normalize_postgres_url(args.db_url)
    elif args.postgres:
        postgres_url = BenchmarkConfig.build_postgres_url()

    if postgres_url:
        print("Using storage backend: postgres (Supabase)")
    if _UPDATE_MODE:
        print("Update mode enabled: existing models will be updated")

    create_models(postgres_url)

    if args.install_local_lmstudio:
        request_lmstudio_install_for_local_models(postgres_url)

    print("Done.")


if __name__ == "__main__":
    main()
