#!/usr/bin/env python3
"""CLI script to export the atacama lookup JSON file.

Usage:
    PYTHONPATH=src python src/scripts/export_atacama.py \
        --output /path/to/atacama_lookup.json \
        --languages zh,lt,fr,es
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure src is on the path
if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from atacama.export_atacama import AtacamaExporter
from storage.backend.config import DataSourceConfig


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export atacama lookup JSON for English word annotations"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for the output JSON file",
    )
    parser.add_argument(
        "--languages",
        default="zh,lt,fr,es",
        help="Comma-separated language codes to include (default: zh,lt,fr,es)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    languages = tuple(lang.strip() for lang in args.languages.split(","))
    config = DataSourceConfig.from_env()
    exporter = AtacamaExporter(config=config, languages=languages)
    result = exporter.export(args.output)

    print(f"Exported {len(result) - 2} word entries")  # subtract _meta and _stopwords
    print(f"Stopwords: {len(result.get('_stopwords', {}))}")
    print(f"Languages: {result['_meta']['languages']}")


if __name__ == "__main__":
    main()
