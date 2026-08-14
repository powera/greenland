#!/usr/bin/env python3
"""Compatibility CLI for :mod:`concepts.generate.entry`."""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add src directory to path (this file lives at src/agents/vovere/).
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.common.common_args import add_backend_args, get_data_source_config
from concepts.generate.entry import (
    ConceptEntryGenerator,
    VovereAgent,
    html_to_text,
    is_allowed_generation_source_url,
)
from storage.models.concept import MAX_CONCEPT_SOURCES

__all__ = [
    "ConceptEntryGenerator",
    "VovereAgent",
    "html_to_text",
    "is_allowed_generation_source_url",
]


def main() -> int:
    """Generate one concept body from manually supplied inputs."""
    parser = argparse.ArgumentParser(description="Vovere - generate a concept entry body")
    parser.add_argument("--title", required=True, help="Concept title, e.g. 'Art Deco'")
    parser.add_argument("--summary", default="", help="One-sentence description of the topic")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        dest="sources",
        help="Source URL (repeatable, up to %d)" % MAX_CONCEPT_SOURCES,
    )
    parser.add_argument("--model", required=True, help="LLM model, e.g. gpt-5.4-mini")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    add_backend_args(parser)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = get_data_source_config(args)
    generator = ConceptEntryGenerator(config)
    sources: List[Dict[str, Any]] = [{"url": url} for url in args.sources]
    print(generator.generate_body(args.title, args.summary, sources))
    return 0


if __name__ == "__main__":
    sys.exit(main())
