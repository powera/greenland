#!/usr/bin/env python3
"""Run the main Greenland agents for a specific lemma GUID.

Usage: python scripts/activate_guid.py [-y|--assume-yes] --guid N06_001

Flags:
  -y, --assume-yes       - Run without interactive confirmation between steps.
  --guid GUID            - The lemma GUID to process.

Environment overrides:
  LANGUAGES              - Space-separated list of languages (default: "lt zh fr es")
  SENTENCE_COUNT         - Number of sentences to generate per lemma (default: 3)
  SENTENCE_TRANSLATION_LIMIT - Target count of fully translated sentences per lemma (optional)
  GRAMMAR_FACT_TYPES     - Space-separated fact types for Lape (optional; overrides grouped tasks)
  GRAMMAR_FACT_TASK      - Lape grouped task preset (default: "all")
  AUDIO_VOICES           - Optional voice names for Vieversys (space-separated, e.g., "ash alloy nova")
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class StepResult:
    """Result of running a single step."""

    title: str
    ran: bool
    stdout: str = ""
    stderr: str = ""
    cost: float = 0.0


@dataclass
class CostSummary:
    """Tracks costs across all steps."""

    steps: list[StepResult] = field(default_factory=list)

    def add(self, result: StepResult) -> None:
        self.steps.append(result)

    def total_cost(self) -> float:
        return sum(s.cost for s in self.steps)

    def print_summary(self) -> None:
        print()
        print("=" * 60)
        print("LLM COST SUMMARY")
        print("=" * 60)
        for step in self.steps:
            if not step.ran:
                print(f"  {step.title}: SKIPPED")
            elif step.cost > 0:
                print(f"  {step.title}: ${step.cost:.6f}")
            else:
                print(f"  {step.title}: $0.000000 (no LLM calls)")
        print("-" * 60)
        print(f"  TOTAL: ${self.total_cost():.6f}")
        print("=" * 60)


def get_repo_root() -> Path:
    """Get the repository root directory."""
    return Path(__file__).parent.parent.resolve()


def extract_costs_from_output(output: str) -> float:
    """Extract LLM/TTS costs from command output.

    Looks for patterns like:
    - "Cost: $0.001234"
    - "Cost: ~$0.001234"
    """
    total = 0.0
    # Match "Cost: $X.XXXXXX" or "Cost: ~$X.XXXXXX"
    pattern = r"Cost:\s*~?\$([0-9]+\.[0-9]+)"
    for match in re.finditer(pattern, output):
        total += float(match.group(1))
    return total


def run_step(
    title: str, cmd: list[str], assume_yes: bool, env: dict, cost_summary: CostSummary
) -> bool:
    """Run a single step, optionally prompting for confirmation.

    Args:
        title: Human-readable step title.
        cmd: Command to run as a list of strings.
        assume_yes: If True, skip confirmation prompt.
        env: Environment variables for the subprocess.
        cost_summary: Cost tracker to record results.

    Returns:
        True if the step was run, False if skipped.
    """
    print()
    print(f"=== {title} ===")
    print(f"Command: {' '.join(cmd)}")

    if not assume_yes:
        reply = input("Run this step? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            print(f"Skipped {title}")
            cost_summary.add(StepResult(title=title, ran=False))
            return False

    # Capture stdout and stderr while also printing them
    process = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    output_lines = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        output_lines.append(line)

    process.wait()
    combined_output = "".join(output_lines)

    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)

    cost = extract_costs_from_output(combined_output)
    cost_summary.add(StepResult(title=title, ran=True, stdout=combined_output, cost=cost))

    return True


def ensure_english_in_list(languages: list[str]) -> list[str]:
    """Return a copy of languages with 'en' added if not present."""
    if "en" not in languages:
        return languages + ["en"]
    return languages[:]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the main Greenland agents for a specific lemma GUID."
    )
    parser.add_argument(
        "-y",
        "--assume-yes",
        action="store_true",
        help="Run without interactive confirmation between steps.",
    )
    parser.add_argument("--guid", required=True, help="The lemma GUID to process.")
    args = parser.parse_args()

    guid = args.guid
    assume_yes = args.assume_yes
    repo_root = get_repo_root()
    cost_summary = CostSummary()

    # Set up environment with PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    # Read configuration from environment variables
    languages_str = os.environ.get("LANGUAGES", "lt zh fr es")
    languages = languages_str.split()

    sentence_count = os.environ.get("SENTENCE_COUNT", "3")
    sentence_translation_limit = os.environ.get("SENTENCE_TRANSLATION_LIMIT", "")
    grammar_fact_types_str = os.environ.get("GRAMMAR_FACT_TYPES", "")
    grammar_fact_task = os.environ.get("GRAMMAR_FACT_TASK", "all")
    audio_voices_str = os.environ.get("AUDIO_VOICES", "")

    grammar_fact_types = grammar_fact_types_str.split() if grammar_fact_types_str.strip() else []
    audio_voices = audio_voices_str.split() if audio_voices_str.strip() else []

    # Build language lists for different steps
    sentence_languages = ensure_english_in_list(languages)
    vilkas_languages = ensure_english_in_list(languages)
    sernas_languages = ensure_english_in_list(languages)
    lape_languages = ensure_english_in_list(languages)

    # Sentence translation args
    sentence_translation_args = []
    if sentence_translation_limit:
        sentence_translation_args = ["--translation-limit", sentence_translation_limit]

    # Change to repo root for consistent behavior
    os.chdir(repo_root)

    # Step 1: Definitions (Lokys)
    run_step(
        "Definitions",
        [
            "python",
            "-m",
            "agents.lokys.cli",
            "--guid",
            guid,
            "--check-type",
            "definitions",
        ],
        assume_yes,
        env,
        cost_summary,
    )

    # Step 2: Translations (Voras)
    run_step(
        "Translations",
        [
            "python",
            "-m",
            "agents.voras.cli",
            "--guid",
            guid,
            "--mode",
            "populate-only",
            "--languages",
        ]
        + languages
        + ["--yes"],
        assume_yes,
        env,
        cost_summary,
    )

    # Step 3: Grammatical forms (Vilkas)
    run_step(
        "Grammatical forms",
        [
            "python",
            "-m",
            "agents.vilkas.cli",
            "--guid",
            guid,
            "--task",
            "all",
            "--fix",
            "--languages",
        ]
        + vilkas_languages
        + ["--yes"],
        assume_yes,
        env,
        cost_summary,
    )

    # Step 4: Synonyms (Šernas)
    run_step(
        "Synonyms",
        [
            "python",
            "-m",
            "agents.sernas.cli",
            "--guid",
            guid,
            "--mode",
            "populate-only",
            "--languages",
        ]
        + sernas_languages
        + ["--yes"],
        assume_yes,
        env,
        cost_summary,
    )

    # Step 5: Pattern sentences (Buivolas)
    run_step(
        "Pattern sentences",
        [
            "python",
            "-m",
            "agents.buivolas",
            "--guid",
            guid,
            "--task",
            "generate-sentences",
            "--mode",
            "pattern",
        ],
        assume_yes,
        env,
        cost_summary,
    )

    # Step 6: Grammatical facts (Lape)
    if grammar_fact_types:
        for fact_type in grammar_fact_types:
            run_step(
                f"Grammatical facts (languages: {' '.join(lape_languages)} - {fact_type})",
                [
                    "python",
                    "-m",
                    "agents.lape",
                    "--guid",
                    guid,
                    "--fact-type",
                    fact_type,
                    "--languages",
                ]
                + lape_languages,
                assume_yes,
                env,
                cost_summary,
            )
    else:
        run_step(
            f"Grammatical facts (languages: {' '.join(lape_languages)} - task: {grammar_fact_task})",
            [
                "python",
                "-m",
                "agents.lape",
                "--guid",
                guid,
                "--task",
                grammar_fact_task,
                "--languages",
            ]
            + lape_languages,
            assume_yes,
            env,
            cost_summary,
        )

    # Step 7: Sentences (Buivolas LLM mode)
    run_step(
        "Sentences",
        [
            "python",
            "-m",
            "agents.buivolas",
            "--guid",
            guid,
            "--task",
            "generate-sentences",
            "--mode",
            "llm",
            "--num-sentences",
            sentence_count,
            "--language",
        ]
        + sentence_languages,
        assume_yes,
        env,
        cost_summary,
    )

    # Step 8: Sentence translations (Zvirblis)
    zvirblis_cmd = (
        ["python", "-m", "agents.zvirblis", "--guid", guid, "--languages"]
        + sentence_languages
        + sentence_translation_args
    )
    run_step("Sentence translations", zvirblis_cmd, assume_yes, env, cost_summary)

    # Step 9: Audio generation (Vieversys) - per language
    for lang in languages:
        vieversys_cmd = [
            "python",
            "-m",
            "agents.vieversys",
            "--guid",
            guid,
            "--mode",
            "populate-only",
            "--language",
            lang,
            "--upload-s3",
            "--yes",
        ]
        if audio_voices:
            vieversys_cmd.extend(["--voices"] + audio_voices)
        # TODO: Remove False to respect assume_yes for vieversys audio steps
        run_step(f"Audio (Vieversys - {lang})", vieversys_cmd, False, env, cost_summary)

    # Step 10: Sentence audio generation (Vieversys) - per language
    for lang in languages:
        vieversys_cmd = [
            "python",
            "-m",
            "agents.vieversys",
            "--guid",
            guid,
            "--mode",
            "populate-only",
            "--language",
            lang,
            "--upload-s3",
            "--yes",
            "--generate-sentences",
            "--sentence-limit",
            "10",
        ]
        if audio_voices:
            vieversys_cmd.extend(["--voices"] + audio_voices)
        # TODO: Remove False to respect assume_yes for vieversys sentence audio steps
        run_step(
            f"Sentence Audio (Vieversys - {lang})",
            vieversys_cmd,
            False,
            env,
            cost_summary,
        )

    # Print cost summary at the end
    cost_summary.print_summary()

    return 0


if __name__ == "__main__":
    sys.exit(main())
