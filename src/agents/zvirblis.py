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

from agents.bebras.translation import ensure_translations
from clients.batch_queue import (
    BatchQueueManager,
    BatchRequestMetadata,
    create_batch_database_session,
)
from clients.openai_batch_client import OpenAIBatchClient
from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_language_args,
    add_llm_args,
    get_data_source_config,
)
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.models.schema import Lemma, Sentence, SentenceTranslation, SentenceWord
from wordfreq.translation.sentence import build_response_schema, build_translation_prompt

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

        self.batch_client = OpenAIBatchClient(debug=self.debug)
        self.batch_session = create_batch_database_session()
        self.batch_manager = BatchQueueManager(
            self.batch_session, self.batch_client, debug=self.debug
        )

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
                    logger.error("Failed to translate sentence %s: %s", sentence.id, error_msg)
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
            logger.error("Error translating sentences for %s: %s", lemma.guid, e, exc_info=True)
            return {"success": False, "translated": 0, "errors": [str(e)]}
        finally:
            session.close()

    def submit_batch_translation(
        self, target_languages: List[str], limit: Optional[int] = None, pattern_id: str = None
    ) -> tuple[Optional[str], int]:
        session = self.get_session()
        try:
            from sqlalchemy import func as sql_func

            sentences_with_only_en = (
                session.query(Sentence.id, sql_func.count(SentenceTranslation.id))
                .join(SentenceTranslation)
                .group_by(Sentence.id)
                .having(sql_func.count(SentenceTranslation.id) == 1)
                .subquery()
            )

            query = (
                session.query(Sentence)
                .join(SentenceTranslation)
                .filter(SentenceTranslation.language_code == "en")
                .filter(Sentence.id.in_(session.query(sentences_with_only_en.c.id)))
                .order_by(Sentence.id)
            )

            if pattern_id:
                query = query.filter(Sentence.source_filename == f"pattern:{pattern_id}")

            if limit:
                query = query.limit(limit)

            sentences = query.all()

            if not sentences:
                logger.warning("No untranslated sentences found")
                return None, 0

            requests_queued = 0
            for sentence in sentences:
                sentence_words = (
                    session.query(SentenceWord)
                    .filter_by(sentence_id=sentence.id, language_code="en")
                    .all()
                )

                # Determine if we should include English in this translation
                # If English word breakdown doesn't exist yet, include it (tier 1 pass)
                # If English word breakdown already exists, skip it (tier 2 pass)
                include_english = len(sentence_words) == 0

                try:
                    context, prompt = build_translation_prompt(
                        sentence, sentence_words, target_languages, session, include_english
                    )
                except ValueError:
                    continue

                custom_id = f"sentence_{sentence.id}"
                full_prompt = f"{context}\n\n{prompt}"
                inner_schema = build_response_schema(target_languages, include_english)

                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "SentenceTranslations",
                        "strict": True,
                        "schema": inner_schema,
                    },
                }

                request_body = {
                    "model": self.config.model,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "response_format": response_format,
                }

                metadata = BatchRequestMetadata(
                    custom_id=custom_id,
                    agent_name="zvirblis",
                    operation_type="translate_sentence",
                    entity_id=sentence.id,
                    entity_type="sentence",
                )

                try:
                    self.batch_manager.queue_request(
                        custom_id=custom_id,
                        request_body=request_body,
                        metadata=metadata,
                        endpoint="/v1/chat/completions",
                    )
                    requests_queued += 1
                except ValueError as e:
                    logger.debug("Skipping sentence %s: %s", sentence.id, e)

            logger.info("Queued %s translation requests", requests_queued)

            if requests_queued > 0:
                pending_requests = self.batch_manager.get_pending_requests(
                    agent_name="zvirblis", operation_type="translate_sentence"
                )
                batch_id, _ = self.batch_manager.submit_batch(
                    pending_requests,
                    batch_metadata={
                        "agent": "zvirblis",
                        "operation": "translate_sentences",
                    },
                )
                logger.info(
                    "Submitted batch %s with %s requests",
                    batch_id,
                    len(pending_requests),
                )
                return batch_id, len(pending_requests)

            return None, 0

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

    subparsers = parser.add_subparsers(dest="command", help="Batch translation commands")

    submit_parser = subparsers.add_parser(
        "submit-batch",
        help="Submit batch translation job for untranslated sentences",
    )
    submit_parser.add_argument(
        "--languages",
        nargs="+",
        required=True,
        choices=["lt", "zh", "ko", "fr", "de", "es", "pt", "sw", "vi", "gd", "it", "nl", "sv"],
        help="Target languages to translate to",
    )
    submit_parser.add_argument("--limit", type=int, help="Max sentences to translate")
    submit_parser.add_argument("--pattern-id", help="Only translate sentences from this pattern")

    parser.set_defaults(languages=["lt", "zh", "fr", "es"])

    return parser


def main():
    parser = get_argument_parser()
    args = parser.parse_args()

    config = get_data_source_config(args)
    agent = ZvirblisAgent(config=config)

    if args.command == "submit-batch":
        target_languages = [lang for lang in args.languages if lang != "en"]
        if not target_languages:
            logger.error("Provide at least one non-English language for batch translation")
            return 1

        batch_id, count = agent.submit_batch_translation(
            target_languages=target_languages,
            limit=args.limit,
            pattern_id=args.pattern_id,
        )

        if batch_id:
            logger.info("=" * 80)
            logger.info("ZVIRBLIS - BATCH SUBMISSION REPORT")
            logger.info("=" * 80)
            logger.info("Batch ID: %s", batch_id)
            logger.info("Requests submitted: %s", count)
            logger.info("Target languages: %s", ", ".join(target_languages))
            logger.info("=" * 80)
            logger.info(
                "Check status with: python -m agents.common.batch status --batch-id %s",
                batch_id,
            )
            logger.info(
                "Complete batch with: python -m agents.common.batch complete --batch-id %s",
                batch_id,
            )
            return 0

        logger.warning("No batch submitted (no untranslated sentences found)")
        return 0

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
