#!/usr/bin/env python3
"""
Backfill: Create base DerivativeForm rows from LemmaTranslation IPA for rhyme-key languages.

For each LemmaTranslation that has IPA in a rhyme-key language (fr, es, lt) but
no corresponding base DerivativeForm, creates a base DerivativeForm so that
rhyme keys are computed and the word appears in the rhyming dictionary.
"""

import argparse
import sys
from pathlib import Path

# Add src to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from constants import WORDFREQ_DB_PATH
from langtools.rhyme_languages import RHYME_KEY_LANGUAGES
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.derivative_form import add_derivative_form
from storage.models.schema import DerivativeForm, Lemma, LemmaTranslation
from words.pronunciation_generation import _get_default_base_grammatical_form

BATCH_SIZE = 100


def build_data_source_config(db_path: str, use_postgres: bool) -> DataSourceConfig:
    """Build the storage config for this migration."""
    if use_postgres:
        return DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=DataSourceConfig.build_postgres_url(),
        )

    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=db_path,
    )


def backfill_base_forms_from_translations(
    config: DataSourceConfig, *, dry_run: bool = False
) -> None:
    """Create base DerivativeForms from LemmaTranslation IPA where missing."""
    session = create_session(config)

    try:
        translations = (
            session.query(LemmaTranslation)
            .filter(
                LemmaTranslation.language_code.in_(sorted(RHYME_KEY_LANGUAGES)),
                LemmaTranslation.ipa_pronunciation.isnot(None),
                LemmaTranslation.ipa_pronunciation != "",
            )
            .all()
        )

        # Filter to those with no base DerivativeForm
        missing = []
        for lt in translations:
            base_form = (
                session.query(DerivativeForm)
                .filter(
                    DerivativeForm.lemma_id == lt.lemma_id,
                    DerivativeForm.language_code == lt.language_code,
                    DerivativeForm.is_base_form == True,
                )
                .first()
            )
            if base_form is None:
                missing.append(lt)

        total = len(missing)
        print(
            f"Found {len(translations)} LemmaTranslations with IPA in rhyme-key languages, "
            f"{total} missing a base DerivativeForm"
        )

        created = 0
        skipped = 0

        for idx, lt in enumerate(missing):
            lemma = session.query(Lemma).filter(Lemma.id == lt.lemma_id).first()
            if not lemma or not lt.translation:
                skipped += 1
                print(
                    f"  SKIP lemma_id={lt.lemma_id} lang={lt.language_code}: "
                    f"no lemma or no translation"
                )
                continue

            grammatical_form = _get_default_base_grammatical_form(lemma.pos_type, lt.language_code)
            print(
                f"  {'DRY ' if dry_run else ''}CREATE lemma={lemma.lemma_text!r} "
                f"lang={lt.language_code} form={lt.translation!r} "
                f"grammatical_form={grammatical_form} ipa={lt.ipa_pronunciation!r}"
            )

            if not dry_run:
                add_derivative_form(
                    session=session,
                    lemma=lemma,
                    derivative_form_text=lt.translation,
                    language_code=lt.language_code,
                    grammatical_form=grammatical_form,
                    is_base_form=True,
                    ipa_pronunciation=lt.ipa_pronunciation,
                    phonetic_pronunciation=lt.phonetic_pronunciation,
                )
                created += 1

                if (idx + 1) % BATCH_SIZE == 0:
                    session.commit()
                    print(f"  Committed batch {(idx + 1) // BATCH_SIZE} ({idx + 1}/{total})")
            else:
                created += 1

        if not dry_run:
            session.commit()

        print(f"\nResults: {created} created, {skipped} skipped, {total} total")
        if dry_run:
            print("** DRY RUN - No changes were made **")
            session.rollback()

    except Exception as error:
        print(f"\nError during backfill: {error}")
        import traceback

        traceback.print_exc()
        session.rollback()
    finally:
        session.close()


def main() -> int:
    """Run the backfill."""
    parser = argparse.ArgumentParser(
        description="Backfill base DerivativeForms from LemmaTranslation IPA for rhyme-key languages"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--db-path",
        default=WORDFREQ_DB_PATH,
        help=f"Path to SQLite database (default: {WORDFREQ_DB_PATH})",
    )
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Use PostgreSQL instead of SQLite",
    )

    args = parser.parse_args()
    config = build_data_source_config(args.db_path, args.postgres)

    print(f"Database: {args.db_path if not args.postgres else 'PostgreSQL'}")
    print(f"Backend: {'postgres' if args.postgres else 'sqlite'}")
    print(f"Dry run: {args.dry_run}")
    print()

    backfill_base_forms_from_translations(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
