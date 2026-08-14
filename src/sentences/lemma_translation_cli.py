#!/usr/bin/env python3
"""CLI and application service for translating sentences linked to a lemma."""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from sentences.translation_coverage import ensure_translations
from clients.batch_queue import (
    BatchQueueManager,
    BatchRequestMetadata,
    create_batch_database_session,
)
from clients.lib import schema_from_dict, to_openai_schema
from clients.openai.batch_client import OpenAIBatchClient
from clients.openai.client import is_gpt5_nano_or_mini_model, reasoning_effort_for_model
from clients.translategemma_client import TranslateGemmaClient
from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_language_args,
    add_llm_args,
    get_data_source_config,
)
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.models.imports import SentencePendingImport
from storage.models.schema import (
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
    SentenceWordHint,
)
from sentences.analysis import discover_and_store_lemmas
from sentences.translation_coverage import find_sentences_needing_translations
from sentences.translation import build_response_schema, build_translation_prompt
from workqueue.task_queue import TaskType, enqueue_task

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LemmaSentenceTranslationService:
    """Translate sentences linked to vocabulary words."""

    def __init__(
        self,
        config: DataSourceConfig,
        pivot_languages: Optional[Sequence[str]] = None,
    ):
        self.config = config
        self.debug = config.debug
        self.pivot_languages: Optional[List[str]] = (
            list(pivot_languages) if pivot_languages else None
        )

        if self.debug:
            logger.setLevel(logging.DEBUG)

        self.batch_client = OpenAIBatchClient(debug=self.debug)
        self.batch_session = create_batch_database_session()
        self.batch_manager = BatchQueueManager(
            self.batch_session, self.batch_client, debug=self.debug
        )

    def get_session(self) -> Any:
        return create_backend_session(self.config)

    def _get_sentence_languages(self, session: Any, sentence_id: int) -> set[str]:
        rows = (
            session.query(SentenceTranslation.language_code)
            .filter(SentenceTranslation.sentence_id == sentence_id)
            .all()
        )
        return {row[0] for row in rows}

    def translate_sentences_for_lemma(
        self, lemma: Lemma, target_languages: List[str], limit: Optional[int] = None
    ) -> Dict[str, Any]:
        session = self.get_session()
        try:
            required_languages = set(target_languages)
            if "en" not in required_languages:
                required_languages.add("en")

            # Find sentences linked via SentenceWord OR SentenceWordHint
            sentence_word_ids = (
                session.query(SentenceWord.sentence_id)
                .filter(SentenceWord.lemma_id == lemma.id)
                .distinct()
            )
            word_hint_ids = (
                session.query(SentenceWordHint.sentence_id)
                .filter(SentenceWordHint.lemma_id == lemma.id)
                .distinct()
            )

            sentence_query = (
                session.query(Sentence)
                .filter((Sentence.id.in_(sentence_word_ids)) | (Sentence.id.in_(word_hint_ids)))
                .order_by(Sentence.id)
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
                    model=self.config.model or "gpt-5.4-mini",
                    verified=False,
                    pivot_languages=self.pivot_languages,
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

                # After committing translations, discover and link lemmas
                # This runs after commit so it doesn't slow down the translation
                for sentence in sentences:
                    try:
                        result = discover_and_store_lemmas(session, sentence.id)
                        if result["added"] > 0:
                            logger.debug(
                                "Discovered %s lemmas for sentence %s",
                                result["added"],
                                sentence.id,
                            )
                    except Exception as e:
                        logger.warning(
                            "Failed to discover lemmas for sentence %s: %s",
                            sentence.id,
                            e,
                        )

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

    def translate_sentences_simple(
        self,
        lemma: Lemma,
        target_languages: List[str],
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Translate sentences using TranslateGemma (simple text-only translations).

        This method provides fast, simple translations without word-by-word breakdown.
        It's suitable for basic sentence translation when detailed linguistic analysis
        isn't needed.

        Args:
            lemma: Lemma to find sentences for
            target_languages: Languages to translate to (e.g., ["fr", "de", "es"])
            limit: Maximum number of sentences to translate

        Returns:
            Dictionary with translation results
        """
        session = self.get_session()
        try:
            required_languages = set(target_languages)
            if "en" not in required_languages:
                required_languages.add("en")

            # Find sentences linked via SentenceWord OR SentenceWordHint
            sentence_word_ids = (
                session.query(SentenceWord.sentence_id)
                .filter(SentenceWord.lemma_id == lemma.id)
                .distinct()
            )
            word_hint_ids = (
                session.query(SentenceWordHint.sentence_id)
                .filter(SentenceWordHint.lemma_id == lemma.id)
                .distinct()
            )

            sentence_query = (
                session.query(Sentence)
                .filter((Sentence.id.in_(sentence_word_ids)) | (Sentence.id.in_(word_hint_ids)))
                .order_by(Sentence.id)
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

            # Create TranslateGemma client (uses default Ollama backend)
            translategemma = TranslateGemmaClient(debug=self.debug)

            for sentence in sentences:
                if needed is not None and translated_sentences >= needed:
                    break

                existing_languages = self._get_sentence_languages(session, sentence.id)
                if required_languages.issubset(existing_languages):
                    continue

                # Get English source text
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

                # Translate to each target language
                for lang in target_languages:
                    if lang in existing_languages or lang == "en":
                        continue

                    try:
                        response = translategemma.generate_translation(
                            text=en_translation,
                            source_lang="en",
                            target_lang=lang,
                        )

                        if not response.response_text:
                            logger.error(
                                "Empty translation for sentence %s to %s",
                                sentence.id,
                                lang,
                            )
                            errors.append(f"Empty translation for sentence {sentence.id} to {lang}")
                            continue

                        # Store translation
                        new_translation = SentenceTranslation(
                            sentence_id=sentence.id,
                            language_code=lang,
                            translation_text=response.response_text,
                            verified=False,
                        )
                        session.add(new_translation)
                        translations_added += 1

                        logger.info(
                            "Translated sentence %s to %s: %s",
                            sentence.id,
                            lang,
                            response.response_text,
                        )

                    except Exception as e:
                        logger.error(
                            "Failed to translate sentence %s to %s: %s",
                            sentence.id,
                            lang,
                            e,
                        )
                        errors.append(f"Failed to translate sentence {sentence.id} to {lang}: {e}")

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
        self,
        target_languages: List[str],
        limit: Optional[int] = None,
        pattern_id: Optional[str] = None,
        exclude_pending_imports: bool = False,
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

            if exclude_pending_imports:
                # Exclude sentences waiting on a staged word. Legacy hint rows
                # count too, for databases staged before the link table existed.
                sentences_with_pending = (
                    session.query(SentencePendingImport.sentence_id).distinct().subquery()
                )
                sentences_with_legacy_hints = (
                    session.query(SentenceWordHint.sentence_id)
                    .filter(SentenceWordHint.pending_import_id.isnot(None))
                    .distinct()
                    .subquery()
                )
                query = query.filter(
                    ~Sentence.id.in_(session.query(sentences_with_pending.c.sentence_id)),
                    ~Sentence.id.in_(session.query(sentences_with_legacy_hints.c.sentence_id)),
                )

            if limit:
                query = query.limit(limit)

            sentences = query.all()

            if not sentences:
                logger.warning("No untranslated sentences found")
                return None, 0

            requests_queued = 0
            for sentence in sentences:
                # Check if English word breakdown already exists
                # If not, include English in the translation request
                english_words = (
                    session.query(SentenceWord)
                    .filter_by(sentence_id=sentence.id, language_code="en")
                    .all()
                )
                include_english = len(english_words) == 0

                try:
                    context, prompt = build_translation_prompt(
                        sentence, target_languages, session, include_english
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
                        "schema": to_openai_schema(schema_from_dict(inner_schema)),
                    },
                }

                request_body = {
                    "model": self.config.model,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "response_format": response_format,
                }

                # Minimize reasoning tokens for gpt-5 nano/mini variants (translation doesn't need deep reasoning)
                if self.config.model and is_gpt5_nano_or_mini_model(self.config.model):
                    effort = reasoning_effort_for_model(self.config.model, "minimal")
                    if effort is not None:
                        request_body["reasoning_effort"] = effort

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


# Compatibility name retained for callers of the former agent module.
ZvirblisAgent = LemmaSentenceTranslationService


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(description="Translate sentences for a lemma GUID")

    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5.4-mini")
    add_guid_arg(parser, help_text="Translate sentences for this specific lemma GUID")
    add_language_args(parser)
    add_backend_args(parser)

    parser.add_argument(
        "--translation-limit",
        type=int,
        help=(
            "Translate until at least this many sentences for the lemma have all target "
            "languages. (Counts existing translated sentences toward the limit.)"
        ),
    )

    parser.add_argument(
        "--use-translategemma",
        action="store_true",
        help=(
            "Use TranslateGemma for simple text-only translations (faster, cheaper, "
            "but no word-by-word breakdown). Default uses GPT-5 with full linguistic analysis."
        ),
    )
    parser.add_argument(
        "--execute-inline",
        action="store_true",
        help="Execute immediately instead of enqueueing work (debugging only)",
    )

    parser.add_argument(
        "--level",
        type=int,
        help="Translate sentences for all lemmas at this difficulty level (instead of single GUID)",
    )

    parser.add_argument(
        "--pivot-languages",
        default="bn,uk,kn",
        help=(
            "Comma-separated pivot languages used to disambiguate candidate lemmas "
            "for sentences without SentenceWordHint lemma links (default: bn,uk,kn). "
            "Pivot translations must already exist as SentenceTranslation rows. "
            "Pass an empty string to disable pivot disambiguation."
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
        choices=[
            "lt",
            "zh",
            "ko",
            "fr",
            "de",
            "es",
            "pt",
            "sw",
            "vi",
            "ja",
            "it",
            "nl",
            "sv",
            "ro",
            "pl",
            "th",
            "ta",
            "kn",
            "uk",
            "bn",
            "hi",
        ],
        help="Target languages to translate to (primary + secondary languages)",
    )
    submit_parser.add_argument("--limit", type=int, help="Max sentences to translate")
    submit_parser.add_argument("--pattern-id", help="Only translate sentences from this pattern")
    submit_parser.add_argument(
        "--exclude-pending-imports",
        action="store_true",
        help="Exclude sentences that have words with pending imports (missing lemmas)",
    )

    parser.set_defaults(languages=["lt", "zh", "fr", "es"])

    return parser


def enqueue_translation_work(
    service: LemmaSentenceTranslationService, args: argparse.Namespace
) -> int:
    """Discover linked sentences and enqueue translation tasks."""
    session = service.get_session()
    try:
        if args.level:
            lemmas = (
                session.query(Lemma)
                .filter(Lemma.difficulty_level == args.level)
                .order_by(Lemma.guid)
                .all()
            )
        else:
            lemmas = session.query(Lemma).filter(Lemma.guid == args.guid).all()
        if not lemmas:
            logger.error("No matching lemmas found")
            return 1

        task_type = (
            TaskType.SENTENCES_TRANSLATE_SIMPLE
            if args.use_translategemma
            else TaskType.SENTENCES_TRANSLATE
        )
        language_key = ":".join(sorted(args.languages))
        enqueued_count = 0
        for lemma in lemmas:
            sentence_ids = find_sentences_needing_translations(
                session,
                lemma_id=lemma.id,
                target_languages=args.languages,
                limit=args.translation_limit,
                require_english_source=args.use_translategemma,
            )
            for sentence_id in sentence_ids:
                if args.dry_run:
                    logger.info("Would queue %s for sentence %s", task_type, sentence_id)
                    enqueued_count += 1
                    continue
                result = enqueue_task(
                    session,
                    task_type=task_type,
                    target_type="sentence",
                    target_id=sentence_id,
                    payload={
                        "schema_version": 1,
                        "sentence_id": sentence_id,
                        "selected_languages": args.languages,
                        "model": service.config.model or constants.DEFAULT_MODEL,
                        "source_component": "agents.zvirblis",
                    },
                    dedup_key=f"{task_type}:{sentence_id}:{language_key}",
                )
                if result.created:
                    enqueued_count += 1
        if not args.dry_run:
            session.commit()
        logger.info("Queued %s sentence translation task(s)", enqueued_count)
        return 0
    finally:
        session.close()


def main() -> int:
    parser = get_argument_parser()
    args = parser.parse_args()

    config = get_data_source_config(args)
    pivot_languages_arg = getattr(args, "pivot_languages", "") or ""
    pivot_languages = [lang.strip() for lang in pivot_languages_arg.split(",") if lang.strip()]
    service = LemmaSentenceTranslationService(
        config=config, pivot_languages=pivot_languages or None
    )

    if args.command == "submit-batch":
        target_languages = [lang for lang in args.languages if lang != "en"]
        if not target_languages:
            logger.error("Provide at least one non-English language for batch translation")
            return 1

        if not args.execute_inline:
            session = service.get_session()
            try:
                if args.dry_run:
                    logger.info("Would queue sentence batch translation submission")
                    return 0
                result = enqueue_task(
                    session,
                    task_type=TaskType.SENTENCES_TRANSLATE_BATCH_SUBMIT,
                    target_type="sentence_batch",
                    target_id=None,
                    payload={
                        "schema_version": 1,
                        "selected_languages": target_languages,
                        "model": service.config.model or constants.DEFAULT_MODEL,
                        "limit": args.limit,
                        "pattern_id": args.pattern_id,
                        "exclude_pending_imports": args.exclude_pending_imports,
                        "source_component": "agents.zvirblis",
                    },
                    dedup_key=(
                        f"{TaskType.SENTENCES_TRANSLATE_BATCH_SUBMIT}:"
                        f"{':'.join(sorted(target_languages))}:{args.pattern_id or 'all'}"
                    ),
                )
                session.commit()
                logger.info(
                    "%s batch-submission task %s",
                    "Queued" if result.created else "Reused",
                    result.task.id,
                )
                return 0
            finally:
                session.close()

        batch_id, count = service.submit_batch_translation(
            target_languages=target_languages,
            limit=args.limit,
            pattern_id=args.pattern_id,
            exclude_pending_imports=getattr(args, "exclude_pending_imports", False),
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

    # Either --guid or --level must be provided
    if not args.guid and not args.level:
        logger.error("Either --guid or --level is required to translate sentences")
        return 1

    if args.guid and args.level:
        logger.error("Cannot specify both --guid and --level (use one or the other)")
        return 1

    if not args.execute_inline:
        return enqueue_translation_work(service, args)

    session = service.get_session()

    # Get lemmas to process
    if args.level:
        # Get all lemmas at this difficulty level
        lemmas = (
            session.query(Lemma)
            .filter(Lemma.difficulty_level == args.level)
            .order_by(Lemma.guid)
            .all()
        )
        session.close()

        if not lemmas:
            logger.error("No lemmas found at difficulty level %s", args.level)
            return 1

        logger.info("Found %s lemmas at level %s", len(lemmas), args.level)

        total_translated = 0
        total_added = 0
        total_errors = []

        for i, lemma in enumerate(lemmas, 1):
            logger.info("Processing lemma %s/%s: %s", i, len(lemmas), lemma.guid)

            # Choose translation method based on --use-translategemma flag
            if args.use_translategemma:
                result = service.translate_sentences_simple(
                    lemma=lemma,
                    target_languages=args.languages,
                    limit=args.translation_limit,
                )
            else:
                result = service.translate_sentences_for_lemma(
                    lemma=lemma,
                    target_languages=args.languages,
                    limit=args.translation_limit,
                )

            if result.get("success"):
                total_translated += result.get("translated", 0)
                total_added += result.get("translations_added", 0)
            else:
                total_errors.extend(result.get("errors", []))

        logger.info("=" * 80)
        logger.info("LEVEL %s TRANSLATION COMPLETE", args.level)
        logger.info("Processed %s lemmas", len(lemmas))
        logger.info("Newly completed sentences: %s", total_translated)
        logger.info("Total translations added: %s", total_added)
        if total_errors:
            logger.warning("Errors encountered: %s", len(total_errors))
        logger.info("=" * 80)
        return 0

    else:
        # Single GUID mode
        try:
            lemma = session.query(Lemma).filter(Lemma.guid == args.guid).first()
        finally:
            session.close()

        if not lemma:
            logger.error("Lemma %s not found", args.guid)
            return 1

        # Choose translation method based on --use-translategemma flag
        if args.use_translategemma:
            logger.info("Using TranslateGemma for simple text-only translations")
            result = service.translate_sentences_simple(
                lemma=lemma,
                target_languages=args.languages,
                limit=args.translation_limit,
            )
        else:
            logger.info("Using GPT-5 for translations with word-by-word breakdown")
            result = service.translate_sentences_for_lemma(
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
