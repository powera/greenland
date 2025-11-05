#!/usr/bin/python3

"""
Migration script to move language translations from individual columns
to the lemma_translations table.

This migrates:
- french_translation -> lemma_translations (language_code='fr')
- chinese_translation -> lemma_translations (language_code='zh')
- korean_translation -> lemma_translations (language_code='ko')
- swahili_translation -> lemma_translations (language_code='sw')
- vietnamese_translation -> lemma_translations (language_code='vi')
"""

import logging
from wordfreq.storage.database import create_database_session, Lemma, LemmaTranslation

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mapping of old column names to language codes
TRANSLATION_COLUMNS = {
    'french_translation': 'fr',
    'chinese_translation': 'zh',
    'korean_translation': 'ko',
    'swahili_translation': 'sw',
    'vietnamese_translation': 'vi',
    'lithuanian_translation': 'lt',
}

def migrate_translations(session, dry_run=False):
    """
    Migrate translations from individual columns to lemma_translations table.

    Args:
        session: Database session
        dry_run: If True, only report what would be migrated without making changes
    """
    total_migrated = 0
    total_skipped = 0

    logger.info("Starting migration of lemma translations...")

    # Get all lemmas
    lemmas = session.query(Lemma).all()
    logger.info(f"Found {len(lemmas)} lemmas to process")

    for lemma in lemmas:
        for column_name, language_code in TRANSLATION_COLUMNS.items():
            # Get the translation value from the old column
            translation_value = getattr(lemma, column_name, None)

            if translation_value:
                # Check if this translation already exists in the new table
                existing = session.query(LemmaTranslation).filter(
                    LemmaTranslation.lemma_id == lemma.id,
                    LemmaTranslation.language_code == language_code
                ).first()

                if existing:
                    if existing.translation != translation_value:
                        logger.warning(
                            f"Lemma {lemma.id} ({lemma.lemma_text}): "
                            f"Translation mismatch for {language_code}: "
                            f"column='{translation_value}' vs table='{existing.translation}'"
                        )
                    total_skipped += 1
                else:
                    if dry_run:
                        logger.info(
                            f"Would migrate: Lemma {lemma.id} ({lemma.lemma_text}) "
                            f"{language_code}='{translation_value}'"
                        )
                    else:
                        # Create new translation record
                        new_translation = LemmaTranslation(
                            lemma_id=lemma.id,
                            language_code=language_code,
                            translation=translation_value,
                            verified=False
                        )
                        session.add(new_translation)
                        logger.debug(
                            f"Migrated: Lemma {lemma.id} ({lemma.lemma_text}) "
                            f"{language_code}='{translation_value}'"
                        )
                    total_migrated += 1

    if not dry_run:
        session.commit()
        logger.info(f"Migration complete! Migrated {total_migrated} translations, skipped {total_skipped} existing")
    else:
        logger.info(f"Dry run complete! Would migrate {total_migrated} translations, {total_skipped} already exist")

    return {
        'migrated': total_migrated,
        'skipped': total_skipped
    }

def main():
    """Main entry point for migration script."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Migrate lemma translations from columns to lemma_translations table'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without making changes'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose debug logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    session = create_database_session()

    try:
        result = migrate_translations(session, dry_run=args.dry_run)
        logger.info(f"Results: {result}")
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == '__main__':
    main()
