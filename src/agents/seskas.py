#!/usr/bin/env python3
"""Šeškas agent: collect consensus verb conjugations from multiple local LLMs."""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.common.common_args import add_common_args, get_data_source_config
from clients.unified_client import UnifiedLLMClient
from storage.backend.config import DataSourceConfig
from words.verb_forms import build_verb_forms_prompt

LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL_PATHS = ["qwen3-4b-lms", "phi-4-lms", "gemma-3-12b-lms"]
DEFAULT_OUTPUT_FILENAME = "generated_conjugations.py"


class SeskasAgent:
    """Generate conjugation candidates and keep only unanimous model outputs."""

    def __init__(self, config: DataSourceConfig, model_paths: list[str], timeout: int) -> None:
        self.config = config
        self.model_paths = model_paths
        self.client = UnifiedLLMClient.from_config(config, timeout=timeout)

    def _response_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "language_code": {"type": "string"},
                "lemma": {"type": "string"},
                "forms": {"type": "object", "additionalProperties": True},
                "extra_forms": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            "required": ["language_code", "lemma", "forms", "extra_forms"],
            "additionalProperties": False,
        }

    def _normalize_for_match(self, response_payload: dict[str, Any]) -> str:
        """Canonicalize payload for strict cross-model equality checks."""
        return json.dumps(response_payload, ensure_ascii=False, sort_keys=True)

    def _build_prompt(self, language_code: str, verb_lemma: str) -> tuple[str, str]:
        combined_prompt = build_verb_forms_prompt(language_code, verb_lemma, config=self.config)
        prompt_sections = combined_prompt.split("\n\n", 1)
        if len(prompt_sections) != 2:
            raise ValueError("Unexpected prompt layout from build_verb_forms_prompt")
        return prompt_sections[0], prompt_sections[1]

    def run(self, language_code: str, verb_lemmas: list[str]) -> dict[str, Any]:
        results_by_model: dict[str, dict[str, dict[str, Any]]] = {
            model_path: {} for model_path in self.model_paths
        }
        schema = self._response_schema()

        for model_path in self.model_paths:
            LOGGER.info("Running model %s across %d verbs", model_path, len(verb_lemmas))
            for verb_lemma in verb_lemmas:
                context, prompt_text = self._build_prompt(language_code, verb_lemma)
                response = self.client.generate_chat(
                    prompt=prompt_text,
                    model=model_path,
                    json_schema=schema,
                    context=context,
                )
                payload = (
                    response.structured_data if isinstance(response.structured_data, dict) else {}
                )
                results_by_model[model_path][verb_lemma] = payload

        consensus: dict[str, dict[str, Any]] = {}
        disagreements: dict[str, dict[str, Any]] = {}

        for verb_lemma in verb_lemmas:
            per_model_payloads = {
                model_path: results_by_model[model_path].get(verb_lemma, {})
                for model_path in self.model_paths
            }
            normalized_payloads = {
                model_path: self._normalize_for_match(payload)
                for model_path, payload in per_model_payloads.items()
            }
            unique_payloads = set(normalized_payloads.values())
            if len(unique_payloads) == 1:
                consensus[verb_lemma] = next(iter(per_model_payloads.values()))
            else:
                disagreements[verb_lemma] = per_model_payloads

        return {
            "language_code": language_code,
            "models": list(self.model_paths),
            "consensus": consensus,
            "disagreements": disagreements,
        }


def _load_verbs_from_text_file(input_path: Path) -> list[str]:
    raw_lines = input_path.read_text(encoding="utf-8").splitlines()
    cleaned_verbs = [
        line.strip() for line in raw_lines if line.strip() and not line.strip().startswith("#")
    ]
    deduplicated_verbs = list(dict.fromkeys(cleaned_verbs))
    return deduplicated_verbs


def _safe_python_identifier(prefix: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", prefix)
    if not sanitized or sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    return sanitized.upper()


def _write_generated_module(output_path: Path, result_bundle: dict[str, Any]) -> None:
    language_code = result_bundle["language_code"]
    constant_name = _safe_python_identifier(f"{language_code}_VERB_CONJUGATION_CONSENSUS")
    module_text = (
        '"""Auto-generated verb conjugation consensus data from Šeškas agent."""\n\n'
        f"{constant_name} = "
        + json.dumps(result_bundle["consensus"], ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(module_text, encoding="utf-8")


def _load_existing_consensus(output_path: Path, language_code: str) -> dict[str, Any]:
    constant_name = _safe_python_identifier(f"{language_code}_VERB_CONJUGATION_CONSENSUS")
    namespace: dict[str, Any] = {}
    try:
        existing_text = output_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}

    exec(existing_text, {}, namespace)
    existing_payload = namespace.get(constant_name)
    if not isinstance(existing_payload, dict):
        raise ValueError(
            f"Existing file {output_path} does not define {constant_name} as a dictionary"
        )
    return existing_payload


def _resolve_output_payload(
    output_path: Path,
    language_code: str,
    consensus_payload: dict[str, Any],
    on_existing: str,
) -> dict[str, Any]:
    if not output_path.exists():
        return consensus_payload

    if on_existing == "error":
        raise FileExistsError(
            f"Output file already exists: {output_path}. "
            "Use --on-existing overwrite or --on-existing merge."
        )

    if on_existing == "overwrite":
        return consensus_payload

    existing_payload = _load_existing_consensus(output_path, language_code)
    merged_payload: dict[str, Any] = dict(existing_payload)
    merged_payload.update(consensus_payload)
    LOGGER.info(
        "Merged %d new consensus entries into existing file with %d entries",
        len(consensus_payload),
        len(existing_payload),
    )
    return merged_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate language verb conjugation data from multiple local LLMs and "
            "write only unanimous entries to a generated_conjugations.py module."
        )
    )
    parser.add_argument("--language", required=True, help="Target language code (e.g. lt, es, pl)")
    parser.add_argument(
        "--verbs-file",
        required=True,
        help="Path to newline-delimited verb lemmas for the target language",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output module path (default: " "src/langtools/<language>/generated_conjugations.py)"
        ),
    )
    parser.add_argument(
        "--on-existing",
        choices=["error", "overwrite", "merge"],
        default="merge",
        help=(
            "How to handle existing output files: error (fail), overwrite "
            "(replace file), merge (preserve existing entries and update with new consensus)."
        ),
    )
    parser.add_argument(
        "--model-paths",
        nargs="+",
        default=DEFAULT_MODEL_PATHS,
        help=(
            "Model codenames to query in sequence (default: qwen3-4b-lms phi-4-lms "
            "gemma-3-12b-lms). These should match benchmarks/schema/create_models.py "
            "entries so UnifiedLLMClient can resolve LMStudio model_path values."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=240,
        help="Per-request timeout in seconds for local model calls",
    )
    add_common_args(parser)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = get_data_source_config(args, default_model=args.model_paths[0])
    agent = SeskasAgent(config=config, model_paths=args.model_paths, timeout=args.timeout)

    verb_file_path = Path(args.verbs_file)
    output_file_path = (
        Path(args.output)
        if args.output
        else Path("src") / "langtools" / args.language.lower() / DEFAULT_OUTPUT_FILENAME
    )

    verb_lemmas = _load_verbs_from_text_file(verb_file_path)
    if not verb_lemmas:
        raise ValueError("No verb lemmas found in --verbs-file")

    result_bundle = agent.run(language_code=args.language.lower(), verb_lemmas=verb_lemmas)
    final_consensus = _resolve_output_payload(
        output_path=output_file_path,
        language_code=args.language.lower(),
        consensus_payload=result_bundle["consensus"],
        on_existing=args.on_existing,
    )
    final_bundle: dict[str, Any] = dict(result_bundle)
    final_bundle["consensus"] = final_consensus
    _write_generated_module(output_file_path, final_bundle)

    LOGGER.info(
        "Wrote %d consensus conjugations to %s (%d disagreements)",
        len(result_bundle["consensus"]),
        output_file_path,
        len(result_bundle["disagreements"]),
    )


if __name__ == "__main__":
    main()
