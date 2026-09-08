#!/usr/bin/python3

"""Move element types between a database and ``data/release``.

Usage is a direction and one or more element types::

    PYTHONPATH=src python -m storage.release.cli export lemmas sentences
    PYTHONPATH=src python -m storage.release.cli export all
    PYTHONPATH=src python -m storage.release.cli import idioms names
    PYTHONPATH=src python -m storage.release.cli import lemma-audio --prune
    PYTHONPATH=src python -m storage.release.cli export database

The two axes are separate on purpose. This replaces a single positional with
twelve values (``sqlite-to-idiom-release``, ``idiom-release-to-sqlite``, ...)
that encoded direction and element type together, so neither could be varied
without naming the other and ``export all`` could not be said at all. The six
per-element ``--*-release-dir`` flags collapse into one ``--release-root``,
since the subdirectory is a property of the element type and lives in the
registry.

``database`` is a pseudo-entity for the whole-database dump through the JSONL
backend -- the old ``sqlite-to-jsonl``/``postgres-to-jsonl`` pair, plus the
import that had no direction at all and so was unreachable from the command
line. It is the path that carries the parts no element module owns
(verifications, operation logs, audio reviews).
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import constants
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import create_session
from storage.release import lemma_audio
from storage.release.registry import ENTITY_SPECS, ReleaseEntitySpec, specs_for

#: The whole-database dump, which is not one element type and so is not in the
#: registry.
DATABASE_ENTITY = "database"


def build_parser() -> argparse.ArgumentParser:
    """Build the release CLI's argument parser."""
    entity_names = ", ".join(list(ENTITY_SPECS) + [DATABASE_ENTITY, "all"])
    parser = argparse.ArgumentParser(
        description="Move element types between a database and data/release",
    )
    parser.add_argument(
        "direction",
        choices=["export", "import"],
        help="export writes data/release from the database; import reads it back",
    )
    parser.add_argument(
        "entities",
        nargs="+",
        metavar="ENTITY",
        help=f"Element types to move, or 'all'. One of: {entity_names}",
    )
    parser.add_argument(
        "--release-root",
        default=constants.RELEASE_DIR,
        help=f"Release tree root (default: {constants.RELEASE_DIR})",
    )
    parser.add_argument(
        "--sqlite-path",
        default=constants.WORDFREQ_DB_PATH,
        help=f"Path to SQLite database (default: {constants.WORDFREQ_DB_PATH})",
    )
    parser.add_argument(
        "--backend",
        choices=["sqlite", "postgres"],
        default="sqlite",
        help=(
            "Which database to read or write (default: sqlite). Naming postgres "
            "without --postgres-url reads the URL from the environment/key file"
        ),
    )
    parser.add_argument(
        "--postgres-url",
        default=None,
        help="PostgreSQL connection URL (reads from env/key file if not provided)",
    )
    parser.add_argument(
        "--jsonl-dir",
        default="data/working",
        help="Destination for 'export database' (default: data/working)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="For 'import database': overwrite a SQLite file that already holds data",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="On import, delete rows the release files no longer list (lemma-audio only)",
    )
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        metavar="POS_DIR/SUBTYPE",
        help=(
            "Limit to one category, e.g. nouns/food. Repeatable; "
            "lemma-audio only. Omit to process every category"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would run without touching the database or the files",
    )
    return parser


def parse_categories(
    parser: argparse.ArgumentParser, raw: Optional[List[str]]
) -> Optional[List[lemma_audio.Category]]:
    """Parse ``--category`` slugs, rejecting any that do not name a category."""
    if not raw:
        return None
    categories: List[lemma_audio.Category] = []
    for slug in raw:
        parsed = lemma_audio.parse_category_slug(slug)
        if parsed is None:
            parser.error(f"invalid --category {slug!r}; expected POS_DIR/SUBTYPE, e.g. nouns/food")
        categories.append(parsed)
    return categories


def run_database(args: argparse.Namespace) -> None:
    """Run the whole-database dump or load.

    The source backend comes from ``--backend``, not from whether a URL was
    typed: a Barsukas PostgreSQL deployment invokes this without
    ``--postgres-url`` and expects the URL to be resolved from the environment
    or key file, the way the old ``postgres-to-jsonl`` direction did.
    """
    from storage.migrate import (
        export_postgres_to_jsonl,
        export_sqlite_to_jsonl,
        import_jsonl_to_sqlite,
    )

    if args.direction == "export":
        if args.backend == "postgres":
            postgres_url = args.postgres_url or DataSourceConfig.build_postgres_url()
            export_postgres_to_jsonl(postgres_url, args.jsonl_dir)
        else:
            export_sqlite_to_jsonl(args.sqlite_path, args.jsonl_dir)
    else:
        # Note the parameter order: (release_dir, sqlite_path).
        import_jsonl_to_sqlite(args.release_root, args.sqlite_path, force=args.force)


def options_for(spec: ReleaseEntitySpec, args: argparse.Namespace) -> dict:
    """The keyword options ``spec`` accepts from the parsed arguments."""
    options: dict = {}
    if spec.accepts_categories and args.categories:
        options["categories"] = args.categories
    if spec.accepts_prune and args.direction == "import" and args.prune:
        options["prune"] = True
    return options


def main(argv: Optional[List[str]] = None) -> int:
    """Move the requested element types in the requested direction."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args.categories = parse_categories(parser, args.categories)

    wants_database = DATABASE_ENTITY in args.entities or "all" in args.entities
    wants_every_element = "all" in args.entities
    element_tokens = [token for token in args.entities if token != DATABASE_ENTITY]
    # "database" on its own means the whole-database dump and nothing else.
    # Passing an empty token list through as None would have meant "all", so
    # `export database` -- what both settings.py routes run -- would have
    # rewritten the entire data/release tree as a side effect.
    try:
        if wants_every_element or element_tokens:
            specs = specs_for(args.direction, element_tokens or None)
        else:
            specs = []
    except (KeyError, ValueError) as error:
        parser.error(str(error))

    # Reject options the chosen element types cannot honor, rather than
    # ignoring them: the old CLI accepted --category on all twelve directions
    # and quietly read it on two.
    for flag, attribute in (("--category", "accepts_categories"), ("--prune", "accepts_prune")):
        given = args.categories if flag == "--category" else args.prune
        if given and not any(getattr(spec, attribute) for spec in specs):
            parser.error(f"{flag} does not apply to {', '.join(s.name for s in specs) or 'these'}")

    release_root = Path(args.release_root)
    # On import the whole-database load rebuilds the SQLite file from scratch,
    # so it has to run before the per-element importers that supplement it --
    # otherwise it discards the sentence and lemma audio they just wrote, since
    # that path deliberately does not read the inline release audio. On export
    # the two write to different places and the order does not matter.
    database_first = wants_database and args.direction == "import"

    if args.dry_run:
        if database_first:
            print(f"would {args.direction} database")
        for spec in specs:
            print(f"would {args.direction} {spec.name} <-> {spec.release_dir(release_root)}")
        if wants_database and not database_first:
            print(f"would {args.direction} database")
        return 0

    if database_first:
        print(f"== {args.direction} database")
        run_database(args)

    if specs:
        config = DataSourceConfig(
            backend_type=BackendType.POSTGRES if args.postgres_url else BackendType.SQLITE,
            sqlite_path=args.sqlite_path,
            postgres_url=args.postgres_url,
        )
        # One session for the whole run: exporting three element types used to
        # open and close three connections.
        session = create_session(config)
        try:
            for spec in specs:
                print(f"== {args.direction} {spec.name}")
                spec.callable_for(args.direction)(
                    session, spec.release_dir(release_root), **options_for(spec, args)
                )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    if wants_database and not database_first:
        print(f"== {args.direction} database")
        run_database(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
