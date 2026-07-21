#!/usr/bin/python3

"""Export verified translations from the linguistics database for benchmark use.

Queries the Lemma and LemmaTranslation tables and exports entries that have
translations in at least N languages, producing a JSON file suitable for
use by the translation benchmark generator.

Usage:
    PYTHONPATH=src python src/benchmarks/scripts/export_translations.py
    PYTHONPATH=src python src/benchmarks/scripts/export_translations.py --min-languages 6
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import constants
from storage.models.schema import Lemma
from storage.translation_helpers import LANGUAGE_NAMES, get_all_translations
from storage.utils.session import create_database_session

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Default output location alongside the wordlist data
DEFAULT_OUTPUT = str(Path(__file__).parent.parent / "data" / "translations_export.json")


def export_translations(
    db_path: str,
    output_path: str,
    min_languages: int,
) -> None:
    """Export translations from database to JSON file.

    Args:
        db_path: Path to the linguistics SQLite database
        output_path: Path for the output JSON file
        min_languages: Minimum number of non-English translations required
    """
    session = create_database_session(db_path)

    try:
        lemmas = session.query(Lemma).order_by(Lemma.id).all()
        logger.info("Found %d lemmas in database", len(lemmas))

        entries: List[Dict[str, Any]] = []
        all_languages_seen: set[str] = set()

        for lemma in lemmas:
            translations = get_all_translations(session, lemma)

            # Filter out None values and English (which is always present)
            non_english = {
                lang: text
                for lang, text in translations.items()
                if lang != "en" and text is not None and text.strip()
            }

            if len(non_english) < min_languages:
                continue

            all_languages_seen.update(non_english.keys())

            entry: Dict[str, Any] = {
                "en": lemma.lemma_text,
                "definition": lemma.definition_text,
                "pos": lemma.pos_type,
                "translations": non_english,
            }
            entries.append(entry)

        logger.info(
            "Exported %d entries with >= %d translations",
            len(entries),
            min_languages,
        )

        output_data = {
            "entries": entries,
            "metadata": {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "total_entries": len(entries),
                "min_languages": min_languages,
                "languages": sorted(all_languages_seen),
            },
        }

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info("Written to %s", output_path)

    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export verified translations from linguistics database"
    )
    parser.add_argument(
        "--db-path",
        default=constants.WORDFREQ_DB_PATH,
        help="Path to linguistics SQLite database",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Output JSON file path",
    )
    parser.add_argument(
        "--min-languages",
        type=int,
        default=4,
        help="Minimum number of non-English translations required (default: 4)",
    )
    args = parser.parse_args()

    export_translations(args.db_path, args.output, args.min_languages)


if __name__ == "__main__":
    main()
