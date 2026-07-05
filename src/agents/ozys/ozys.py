#!/usr/bin/env python3
"""
Ožys - text generator for authored works in the story library.

"Ožys" means "billy goat" in Lithuanian: a nod to The Three Billy Goats Gruff,
the story that motivated the text-works library (docs/fables_design.md).

Given an authored-type :class:`~storage.models.text_work.TextWork` (fable,
folk tale, fairy tale, myth, legend, or conversation), Ožys asks an LLM to
write the text itself -- a *telling* of the story, or an original dialogue --
and stores it as a :class:`~storage.models.text_work.TextVersion`. It is a
storyteller, not an encyclopedist: encyclopedic framing, analytic morals, and
``[[wiki links]]`` are explicitly out (analysis belongs to the concept entry).

Canonical-type works (poems, songs, speeches, ...) are refused outright:
their texts are transcribed, never generated.

Usage:
    PYTHONPATH=src python src/agents/ozys/ozys.py \\
        --slug The_Three_Billy_Goats_Gruff --model gpt-5.4-mini
    PYTHONPATH=src python src/agents/ozys/ozys.py \\
        --slug At_the_Doctors_Office --difficulty 2 --dry-run
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, cast

# Add src directory to path (this file lives at src/agents/ozys/)
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_llm_args,
    get_data_source_config,
)
from clients.lib import ChatMessage
from clients.unified_client import UnifiedLLMClient
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.crud.text_work import (
    create_text_version,
    get_text_version_for_slot,
    get_text_work_by_slug,
    update_text_version,
)
from storage.models.concept import concept_slug_to_title
from storage.models.text_work import TextWork, is_authored_text_type
from util.prompt_loader import get_context, get_prompt

logger = logging.getLogger(__name__)

# Category used to load prompts/fables/{retelling,conversation}/{context,prompt}.txt.
PROMPT_CATEGORY: str = "fables"
RETELLING_PROMPT_TYPE: str = "retelling"
CONVERSATION_PROMPT_TYPE: str = "conversation"

# All Ožys output is English for now (SUPPORTED_TEXT_VERSION_LANGS policy).
OUTPUT_LANG: str = "en"


def prompt_type_for_text_type(text_type: str) -> str:
    """Return the prompt family for an authored text type.

    Args:
        text_type: An entry from AUTHORED_TEXT_TYPES.

    Returns:
        "conversation" for constructed dialogues, "retelling" for the
        traditional-story types.

    Raises:
        ValueError: If the type is not an authored type (canonical texts are
            transcribed, never generated).
    """
    if not is_authored_text_type(text_type):
        raise ValueError(f"Ožys only generates authored types, not {text_type!r}")
    if text_type == "conversation":
        return CONVERSATION_PROMPT_TYPE
    return RETELLING_PROMPT_TYPE


def difficulty_instruction(difficulty_level: Optional[int]) -> str:
    """Return the difficulty line for the prompt template ("" when untargeted)."""
    if difficulty_level is None:
        return ""
    return (
        f"\nTarget difficulty: level {difficulty_level} on the project's lemma "
        "difficulty scale -- prefer common vocabulary and short, simple sentence "
        "structures appropriate to that level.\n"
    )


class OzysAgent:
    """Generates the texts of authored works (tellings and conversations)."""

    def __init__(self, config: DataSourceConfig, model: Optional[str] = None) -> None:
        """Initialize the agent.

        Args:
            config: Data source configuration (carries model, debug, API keys).
            model: Optional model override; falls back to ``config.model``.
        """
        self.config = config.with_model(model) if model else config
        self.model = self.config.model
        self.client = UnifiedLLMClient.from_config(self.config)

    def generate_text(
        self,
        title: str,
        summary: str,
        text_type: str,
        difficulty_level: Optional[int] = None,
    ) -> str:
        """Generate the text of an authored work.

        Args:
            title: The work's title (display form, e.g. "The Gingerbread Man").
            summary: One-sentence summary pinning which story is meant (for
                conversations: the scenario brief).
            text_type: An entry from AUTHORED_TEXT_TYPES; selects the prompt
                family (retelling vs conversation).
            difficulty_level: Optional target difficulty (lemma scale).

        Returns:
            The generated Markdown text.

        Raises:
            ValueError: If no model is configured, or the type is canonical.
        """
        if not self.model:
            raise ValueError("OzysAgent requires a model (set config.model or pass model=)")
        prompt_type = prompt_type_for_text_type(text_type)

        display_title = concept_slug_to_title(title)
        instruction = get_prompt(PROMPT_CATEGORY, prompt_type).format(
            title=display_title,
            summary=summary,
            difficulty_instruction=difficulty_instruction(difficulty_level),
        )
        system_context = get_context(PROMPT_CATEGORY, prompt_type)
        messages: list[ChatMessage] = [{"role": "user", "content": instruction}]
        response = self.client.generate_chat(
            "", model=self.model, context=system_context, messages=messages
        )
        return cast(str, response.response_text.strip())

    def generate_for_work(self, work: TextWork, difficulty_level: Optional[int] = None) -> str:
        """Generate the text for a TextWork row (see :meth:`generate_text`)."""
        return self.generate_text(work.title, work.summary or "", work.text_type, difficulty_level)


def main() -> int:
    """CLI entry point: generate and store one version of an authored work."""
    parser = argparse.ArgumentParser(
        description="Ožys - generate the text of an authored work (telling/conversation)"
    )
    parser.add_argument(
        "--slug",
        required=True,
        help="Slug (or title) of an existing text work, e.g. The_Three_Billy_Goats_Gruff",
    )
    parser.add_argument(
        "--difficulty",
        type=int,
        default=None,
        help="Target difficulty level (lemma scale); omit for the plain reference telling",
    )
    add_common_args(parser)
    add_llm_args(parser)
    add_backend_args(parser)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = get_data_source_config(args)
    session = create_backend_session(config)
    try:
        work = get_text_work_by_slug(session, args.slug)
        if work is None:
            logger.error("No text work found for slug %r", args.slug)
            return 1
        if not is_authored_text_type(work.text_type):
            logger.error(
                "%r is a canonical-type work [%s]; its text is transcribed, not generated",
                work.slug,
                work.text_type,
            )
            return 1

        existing = get_text_version_for_slot(session, work, OUTPUT_LANG, args.difficulty)
        if existing is not None and existing.verified:
            logger.error(
                "The (%s, %s) version of %r is verified; refusing to overwrite",
                OUTPUT_LANG,
                args.difficulty,
                work.slug,
            )
            return 1
        if existing is not None and not args.dry_run and not args.yes:
            answer = input(
                f"Overwrite the existing unverified {existing.variant_label} version "
                f"of {work.title!r}? [y/N] "
            )
            if answer.strip().lower() not in ("y", "yes"):
                print("Aborted.")
                return 1

        agent = OzysAgent(config, model=args.model)
        body = agent.generate_for_work(work, difficulty_level=args.difficulty)
        if not body:
            logger.error("Generation returned an empty text for %r", work.slug)
            return 1

        if args.dry_run:
            print(body)
            return 0

        if existing is not None:
            version = update_text_version(
                session, existing, body=body, source_model=args.model, verified=False
            )
        else:
            version = create_text_version(
                session,
                work,
                lang=OUTPUT_LANG,
                body=body,
                difficulty_level=args.difficulty,
                source_model=args.model,
            )
        if version is None:
            logger.error("Failed to store the generated version for %r", work.slug)
            return 1
        print(f"Stored {version.variant_label} version of {work.title!r} ({len(body)} chars).")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
