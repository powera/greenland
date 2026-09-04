"""Queue-first command-line interface for translation verification."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any, Dict, List, Optional, Sequence, cast

from sqlalchemy.orm import Query, Session

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_language_args,
    add_llm_args,
    add_processing_args,
    confirm_operation,
    get_data_source_config,
)
from sentences.verification import verify_sentence_links, verify_sentence_translations
from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.models.schema import Lemma, LemmaTranslation, Sentence, SentenceTranslation
from verification.common import DEFAULT_VERIFY_LANGUAGES, filter_languages_for_model
from words.verification import verify_word_translations
from workqueue.task_queue import TaskType, enqueue_task

logger = logging.getLogger(__name__)


def get_argument_parser() -> argparse.ArgumentParser:
    """Build the standalone verification argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify stored translations. Bulk commands enqueue atomic workqueue jobs; "
            "specific records and report-only runs execute immediately."
        )
    )
    subparsers = parser.add_subparsers(dest="verify_type", required=True)

    words_parser = subparsers.add_parser("words", help="Verify word translations")
    _add_common_verification_args(words_parser)
    add_guid_arg(words_parser, help_text="Verify one word immediately by GUID")

    sentences_parser = subparsers.add_parser(
        "sentences", help="Verify sentence translations and optionally lemma links"
    )
    _add_common_verification_args(sentences_parser)
    sentences_parser.add_argument(
        "--sentence-id", type=int, help="Verify one sentence immediately by database ID"
    )
    link_group = sentences_parser.add_mutually_exclusive_group()
    link_group.add_argument(
        "--check-lemma-links",
        action="store_true",
        default=True,
        help="Also enqueue or run a separate lemma-link verification (default)",
    )
    link_group.add_argument(
        "--no-check-lemma-links",
        action="store_false",
        dest="check_lemma_links",
        help="Verify sentence translations only",
    )
    return parser


def _add_common_verification_args(parser: argparse.ArgumentParser) -> None:
    add_common_args(parser)
    add_llm_args(parser)
    add_backend_args(parser)
    add_processing_args(parser)
    add_language_args(parser)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Run immediately and report verdicts without updating stored flags",
    )
    parser.add_argument(
        "--unverified-only",
        action="store_true",
        help="Select only records with an unverified requested-language translation",
    )
    parser.add_argument("--json", action="store_true", help="Write a JSON result summary")


def _languages(args: argparse.Namespace, config: DataSourceConfig) -> List[str]:
    requested_languages = args.languages or DEFAULT_VERIFY_LANGUAGES
    model = config.model or "gpt-5.4-mini"
    supported_languages = filter_languages_for_model(requested_languages, model)
    if not supported_languages:
        raise ValueError(f"No supported verification languages for model {model}")
    return supported_languages


def _apply_limit(query: Query[Any], limit: Optional[int]) -> Query[Any]:
    return query.limit(limit) if limit else query


def _word_query(session: Session, languages: List[str], args: argparse.Namespace) -> Query[Lemma]:
    query = session.query(Lemma).filter(Lemma.guid.isnot(None)).order_by(Lemma.id)
    if args.guid:
        query = query.filter(Lemma.guid == args.guid)
    elif args.unverified_only:
        query = (
            query.join(LemmaTranslation)
            .filter(
                LemmaTranslation.verified.is_(False),
                LemmaTranslation.language_code.in_(languages),
            )
            .distinct()
        )
    return _apply_limit(query, args.limit)


def _sentence_query(
    session: Session, languages: List[str], args: argparse.Namespace
) -> Query[Sentence]:
    query = session.query(Sentence).order_by(Sentence.id)
    if args.sentence_id is not None:
        query = query.filter(Sentence.id == args.sentence_id)
    elif args.unverified_only:
        query = (
            query.join(SentenceTranslation)
            .filter(
                SentenceTranslation.verified.is_(False),
                SentenceTranslation.language_code.in_(languages),
            )
            .distinct()
        )
    return _apply_limit(query, args.limit)


def _emit(result: Dict[str, Any], output_json: bool) -> None:
    if output_json:
        print(json.dumps(result, indent=2, default=str))
        return
    if result.get("mode") == "queued":
        print(
            f"Queued {result['created']} of {result['requested']} requested "
            f"verification jobs ({result['existing']} already active)."
        )
        if result.get("dry_run"):
            print("Dry run: queued jobs were rolled back.")
        return
    print(json.dumps(result, indent=2, default=str))


def _empty_result(mode: str) -> Dict[str, Any]:
    if mode == "queued":
        return {
            "mode": "queued",
            "requested": 0,
            "created": 0,
            "existing": 0,
            "results": [],
        }
    return {"mode": "inline", "results": []}


def _confirm_bulk(args: argparse.Namespace, item_count: int, job_count: int) -> bool:
    return cast(
        bool,
        confirm_operation(
            f"Will enqueue {job_count} verification jobs for {item_count} records.",
            estimated_calls=job_count,
            skip_confirmation=args.yes,
            dry_run=args.dry_run,
        ),
    )


def _queue_words(
    session: Session,
    lemmas: Sequence[Lemma],
    languages: List[str],
    config: DataSourceConfig,
    dry_run: bool,
) -> Dict[str, Any]:
    created = 0
    model = config.model or "gpt-5.4-mini"
    for lemma in lemmas:
        enqueue_result = enqueue_task(
            session,
            task_type=TaskType.WORDS_TRANSLATIONS_VERIFY,
            target_type="lemma",
            target_id=lemma.id,
            payload={"lemma_id": lemma.id, "languages": languages, "model": model},
            dedup_key=(
                f"{TaskType.WORDS_TRANSLATIONS_VERIFY}:{lemma.id}:{model}:"
                f"{':'.join(sorted(languages))}"
            ),
        )
        created += int(enqueue_result.created)
    if dry_run:
        session.rollback()
    else:
        session.commit()
    return {
        "mode": "queued",
        "requested": len(lemmas),
        "created": created,
        "existing": len(lemmas) - created,
        "dry_run": dry_run,
    }


def _queue_sentences(
    session: Session,
    sentences: Sequence[Sentence],
    languages: List[str],
    config: DataSourceConfig,
    check_lemma_links: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    created = 0
    requested = 0
    model = config.model or "gpt-5.4-mini"
    task_types = [TaskType.SENTENCES_TRANSLATIONS_VERIFY]
    if check_lemma_links:
        task_types.append(TaskType.SENTENCES_LINKS_VERIFY)
    for sentence in sentences:
        for task_type in task_types:
            requested += 1
            enqueue_result = enqueue_task(
                session,
                task_type=task_type,
                target_type="sentence",
                target_id=sentence.id,
                payload={
                    "sentence_id": sentence.id,
                    "languages": languages,
                    "model": model,
                },
                dedup_key=f"{task_type}:{sentence.id}:{model}:{':'.join(sorted(languages))}",
            )
            created += int(enqueue_result.created)
    if dry_run:
        session.rollback()
    else:
        session.commit()
    return {
        "mode": "queued",
        "records": len(sentences),
        "requested": requested,
        "created": created,
        "existing": requested - created,
        "dry_run": dry_run,
    }


def verify_words(args: argparse.Namespace) -> int:
    """Run one/report-only word verification inline, or enqueue a bulk run."""
    config = get_data_source_config(args)
    session = create_session(config)
    try:
        languages = _languages(args, config)
        lemmas = _word_query(session, languages, args).all()
        if not lemmas:
            mode = "inline" if args.guid or args.report_only else "queued"
            _emit(_empty_result(mode), args.json)
            return 0

        inline = bool(args.guid or args.report_only)
        if not inline:
            if not _confirm_bulk(args, len(lemmas), len(lemmas)):
                return 0
            _emit(_queue_words(session, lemmas, languages, config, args.dry_run), args.json)
            return 0

        if args.report_only and not args.guid:
            if not _confirm_bulk(args, len(lemmas), len(lemmas)):
                return 0

        results = [
            verify_word_translations(
                session=session,
                lemma_id=lemma.id,
                config=config,
                languages=languages,
                persist=not (args.report_only or args.dry_run),
            )
            for lemma in lemmas
        ]
        if args.report_only or args.dry_run:
            session.rollback()
        else:
            session.commit()
        _emit({"mode": "inline", "results": results}, args.json)
        return 0
    except Exception as error:
        session.rollback()
        logger.error("Word verification failed: %s", error, exc_info=args.debug)
        return 1
    finally:
        session.close()


def verify_sentences(args: argparse.Namespace) -> int:
    """Run one/report-only sentence verification inline, or enqueue a bulk run."""
    config = get_data_source_config(args)
    session = create_session(config)
    try:
        languages = _languages(args, config)
        sentences = _sentence_query(session, languages, args).all()
        if not sentences:
            mode = "inline" if args.sentence_id is not None or args.report_only else "queued"
            _emit(_empty_result(mode), args.json)
            return 0

        inline = bool(args.sentence_id is not None or args.report_only)
        if not inline:
            jobs_per_sentence = 2 if args.check_lemma_links else 1
            if not _confirm_bulk(args, len(sentences), len(sentences) * jobs_per_sentence):
                return 0
            result = _queue_sentences(
                session,
                sentences,
                languages,
                config,
                args.check_lemma_links,
                args.dry_run,
            )
            _emit(result, args.json)
            return 0

        if args.report_only and args.sentence_id is None:
            calls_per_sentence = 2 if args.check_lemma_links else 1
            if not _confirm_bulk(
                args,
                len(sentences),
                len(sentences) * calls_per_sentence,
            ):
                return 0

        results: List[Dict[str, Any]] = []
        for sentence in sentences:
            sentence_result: Dict[str, Any] = {
                "translations": verify_sentence_translations(
                    session=session,
                    sentence_id=sentence.id,
                    config=config,
                    languages=languages,
                    persist=not (args.report_only or args.dry_run),
                )
            }
            if args.check_lemma_links:
                sentence_result["links"] = verify_sentence_links(
                    session=session,
                    sentence_id=sentence.id,
                    config=config,
                    languages=languages,
                )
            results.append(sentence_result)
        if args.report_only or args.dry_run:
            session.rollback()
        else:
            session.commit()
        _emit({"mode": "inline", "results": results}, args.json)
        return 0
    except Exception as error:
        session.rollback()
        logger.error("Sentence verification failed: %s", error, exc_info=args.debug)
        return 1
    finally:
        session.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse arguments and dispatch a verification command."""
    parser = get_argument_parser()
    args = parser.parse_args(argv)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    if args.verify_type == "words":
        return verify_words(args)
    if args.verify_type == "sentences":
        return verify_sentences(args)
    parser.error("a verification type is required")
    return 2
