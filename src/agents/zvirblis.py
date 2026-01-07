#!/usr/bin/env python3
"""
Žvirblis - Sentence Translation Agent

⚠️  IMPORTANT: This agent is used by Barsukas in src/barsukas/routes/agents.py.
    If you modify the public interface, keep the API contract in sync to prevent runtime errors.

This agent focuses on translating existing sentences linked to a specific lemma.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.common.common_args import (
    add_common_args,
    add_llm_args,
    add_guid_arg,
    add_language_args,
    add_backend_args,
    get_data_source_config,
)
from agents.bebras.translation import ensure_translations
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.models.schema import Lemma, Sentence, SentenceTranslation, SentenceWord

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ZvirblisAgent:
    """Agent for translating sentences linked to vocabulary words."""

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.debug = config.debug

        if self.debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        return create_backend_session(self.config)

    def _get_sentence_languages(self, session, sentence_id: int) -> set[str]:
        rows = (
            session.query(SentenceTranslation.language_code)
            .filter(SentenceTranslation.sentence_id == sentence_id)
            .all()
        )
        return {row[0] for row in rows}

    def translate_sentences_for_lemma(
        self, lemma: Lemma, target_languages: List[str], limit: Optional[int] = None
    ) -> Dict[str, any]:
        session = self.get_session()
        try:
            required_languages = set(target_languages)
            if "en" not in required_languages:
                required_languages.add("en")

            sentence_query = (
                session.query(Sentence)
                .join(SentenceWord)
                .filter(SentenceWord.lemma_id == lemma.id)
                .order_by(Sentence.id)
                .distinct()
            )

            sentences = sentence_query.all()
            if not sentences:
                logger.warning("No sentences found linked to lemma %s", lemma.guid)
                return {"success": False, "translated": 0, "errors": ["No sentences found"]}

            already_complete = 0
            for sentence in sentences:
                existing_languages = self._get_sentence_languages(session, sentence.id)
                if required_languages.issubset(existing_languages):
                    already_complete += 1

            if limit is not None and already_complete >= limit:
                logger.info(
                    "Already have %s sentences translated for %s; limit is %s",
                    already_complete,
                    lemma.guid,
                    limit,
                )
                return {
                    "success": True,
                    "translated": 0,
                    "already_translated": already_complete,
                    "errors": [],
                }

            needed = None if limit is None else max(0, limit - already_complete)
            translated_sentences = 0
            translations_added = 0
            errors = []

            for sentence in sentences:
                if needed is not None and translated_sentences >= needed:
                    break

                existing_languages = self._get_sentence_languages(session, sentence.id)
                if required_languages.issubset(existing_languages):
                    continue

                en_translation = (
                    session.query(SentenceTranslation.translation_text)
                    .filter(
                        SentenceTranslation.sentence_id == sentence.id,
                        SentenceTranslation.language_code == "en",
                    )
                    .scalar()
                )

                if not en_translation:
                    logger.warning(
                        "Sentence %s has no English source; skipping translation",
                        sentence.id,
                    )
                    continue

                result = ensure_translations(
                    session=session,
                    sentence=sentence,
                    source_text=en_translation,
                    source_language="en",
                    target_languages=target_languages,
                    model=self.config.model,
                    verified=False,
                )

                if result.get("success"):
                    translations_added += result.get("added", 0)
                else:
                    error_msg = result.get("error", "Unknown translation error")
                    logger.error(
                        "Failed to translate sentence %s: %s", sentence.id, error_msg
                    )
                    errors.append(error_msg)

                session.flush()

                updated_languages = self._get_sentence_languages(session, sentence.id)
                if required_languages.issubset(updated_languages):
                    translated_sentences += 1

            if translations_added:
                session.commit()

            return {
                "success": True,
                "translated": translated_sentences,
                "translations_added": translations_added,
                "already_translated": already_complete,
                "errors": errors,
            }

        except Exception as e:
            logger.error(
                "Error translating sentences for %s: %s", lemma.guid, e, exc_info=True
            )
            return {"success": False, "translated": 0, "errors": [str(e)]}
        finally:
            session.close()


def get_argument_parser():
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(description="Translate sentences for a lemma GUID")

    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_guid_arg(parser, help_text="Translate sentences for this specific lemma GUID")
    add_language_args(parser, multiple=True)
    add_backend_args(parser)

    parser.add_argument(
        "--translation-limit",
        type=int,
        help=(
            "Translate until at least this many sentences for the lemma have all target "
            "languages. (Counts existing translated sentences toward the limit.)"
        ),
    )

    parser.set_defaults(languages=["en", "lt", "zh", "ko", "fr", "es", "de", "pt", "sw", "vi"])

    return parser


def main():
    parser = get_argument_parser()
    args = parser.parse_args()

    config = get_data_source_config(args)
    agent = ZvirblisAgent(config=config)

    if not args.guid:
        logger.error("--guid is required to translate sentences")
        return 1

    session = agent.get_session()
    try:
        lemma = session.query(Lemma).filter(Lemma.guid == args.guid).first()
    finally:
        session.close()

    if not lemma:
        logger.error("Lemma %s not found", args.guid)
        return 1

    result = agent.translate_sentences_for_lemma(
        lemma=lemma,
        target_languages=args.languages,
        limit=args.translation_limit,
    )

    if result.get("success"):
        logger.info(
            "Added translations for %s sentence(s); newly completed=%s, already complete=%s",
            result.get("translations_added", 0),
            result.get("translated", 0),
            result.get("already_translated", 0),
        )
        return 0

    logger.error("Translation failed: %s", result.get("errors"))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
