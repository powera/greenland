"""Load ancient-language translations from the release tree into the database.

The ``la``/``sa``/``grc``/``ar-classical``/``non`` translations and their
``translation_status`` judgements live only in
``data/release/lemmas/*/*/ancient.jsonl``; nothing had ever read them back into
a SQL backend. This is the mechanical, no-LLM import that fixes that.

    PYTHONPATH=src python src/wordfreq/tools/import_ancient_translations.py --dry-run
    PYTHONPATH=src python src/wordfreq/tools/import_ancient_translations.py

It is read-only against ``data/release`` - the release files are never written.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend import create_session
from storage.release.ancient_import import import_ancient_translations
from storage.translation_helpers import ANCIENT_LANGUAGE_GROUP

logger = logging.getLogger(__name__)

DEFAULT_RELEASE_ROOT = Path("data/release")


def print_summary(summary: Dict[str, Any], *, dry_run: bool) -> None:
    """Print a short human-readable summary of the import."""
    heading = "Ancient translation import (dry run)" if dry_run else "Ancient translation import"
    print(f"\n{heading}")
    print("=" * len(heading))
    print(f"  files read:            {summary['files_read']}")
    print(f"  records read:          {summary['records_read']}")
    print(f"  lemmas matched:        {summary['lemmas_matched']}")
    print(f"  translations written:  {summary['translations_written']}")
    print(f"  skipped (existing):    {summary['translations_skipped_existing']}")
    print(f"  statuses written:      {summary['statuses_written']}")

    missing = summary["missing_guids"]
    if missing:
        shown = ", ".join(missing[:10])
        suffix = f" (+{len(missing) - 10} more)" if len(missing) > 10 else ""
        print(f"  GUIDs not in database: {len(missing)} -> {shown}{suffix}")

    unexpected = summary["unexpected_languages"]
    if unexpected:
        print(f"  unexpected languages:  {', '.join(unexpected)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument(
        "--release-root",
        type=Path,
        default=DEFAULT_RELEASE_ROOT,
        help=f"Release tree to read (default: {DEFAULT_RELEASE_ROOT})",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=list(ANCIENT_LANGUAGE_GROUP),
        help="Language codes to accept (default: the ancient group)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace translations that already exist (default: leave them alone)",
    )
    parser.add_argument("--output", type=Path, help="Write the summary as JSON")
    args = parser.parse_args()

    if not args.release_root.is_dir():
        parser.error(f"release root not found: {args.release_root}")

    config = get_data_source_config(args)
    session = create_session(config)
    try:
        result = import_ancient_translations(
            session,
            args.release_root,
            languages=args.languages,
            overwrite=args.overwrite,
        )
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    finally:
        session.close()

    summary = result.as_dict()
    print_summary(summary, dry_run=bool(args.dry_run))
    if args.output is not None:
        args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
