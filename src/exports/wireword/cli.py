#!/usr/bin/env python3
"""Command-line interface for WireWord exports."""

from __future__ import annotations

import argparse

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from exports.wireword.service import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES,
    WirewordExportService,
    logger,
)
from storage.backend.factory import create_session
from workqueue.task_queue import TaskType, enqueue_task


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(description="Export database content to WireWord format")

    # Common arguments
    add_common_args(parser)
    add_backend_args(parser)

    # Language options
    language_help = f'Language code (default: lt). Supported: {", ".join(f"{k}={v}" for k, v in SUPPORTED_LANGUAGES.items())}, zh-Hant=Chinese (Traditional)'
    language_choices = sorted(SUPPORTED_LANGUAGES.keys()) + ["zh-Hant"]
    parser.add_argument(
        "--language",
        choices=language_choices,
        default="lt",
        help=language_help,
    )
    parser.add_argument(
        "--traditional",
        action="store_true",
        help="For Chinese (zh): export Traditional characters instead of Simplified (exports to lang_zh_Hant/)",
    )

    # Export mode
    parser.add_argument(
        "--mode",
        choices=["single", "directory", "both"],
        default="directory",
        help="Export mode (default: directory). 'single' and 'both' are "
        "DEPRECATED — they produce legacy noun/verb-split files.",
    )

    # Output paths
    parser.add_argument(
        "--output",
        help="[DEPRECATED] Output path for single-file (noun-only) export.",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for directory export (default: data/trakaido_wordlists/lang_{language}/generated/)",
    )

    # Filtering options
    parser.add_argument("--level", type=int, help="Filter by specific difficulty level")
    parser.add_argument("--pos-type", help="Filter by specific POS type")
    parser.add_argument("--pos-subtype", help="Filter by specific POS subtype")
    parser.add_argument("--limit", type=int, help="Limit number of results")

    # Include options
    parser.add_argument(
        "--include-without-guid",
        action="store_true",
        help="Include lemmas without GUIDs (default: False)",
    )
    parser.add_argument(
        "--include-unverified",
        action="store_true",
        default=True,
        help="Include unverified entries (default: True)",
    )
    parser.add_argument(
        "--include-unreviewed-audio",
        action="store_true",
        help="Include audio from staging that has not yet been reviewed. Changes audio path in manifest.",
    )
    parser.add_argument(
        "--skip-country-overrides",
        action="store_true",
        help="Skip applying country-specific difficulty overrides before export.",
    )
    parser.add_argument(
        "--skip-family-relation-overrides",
        action="store_true",
        help="Skip applying family relation difficulty overrides before export.",
    )
    parser.add_argument(
        "--source-language",
        default="en",
        help="Source language code (default: en). The language the learner already knows. "
        "Use 'all' to export all source-language variants in one run. "
        "Supported non-English sources: "
        f"{', '.join(SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES)}.",
    )
    parser.add_argument(
        "--use-workqueue",
        action="store_true",
        default=False,
        help="Enqueue directory exports for background processing by workqueue worker.",
    )
    parser.add_argument(
        "--no-cdn-upload",
        action="store_true",
        default=False,
        help="Skip uploading wireword files to the CDN. By default, directory "
        "exports upload to the trakaido-wireword bucket and generate the v2 "
        "manifest with MD5-hash filenames (if DO Spaces credentials are available).",
    )

    return parser


def _cdn_credentials_available() -> bool:
    """Return True if Digital Ocean Spaces credentials are configured.

    Reports no credentials under GREENLAND_TEST_MODE, so an export skips the
    CDN step rather than failing partway through it.
    """
    import os
    from pathlib import Path

    import constants
    from clients.keys import test_mode_enabled

    if test_mode_enabled():
        return False
    if os.getenv("DO_SPACES_KEY") and os.getenv("DO_SPACES_SECRET"):
        return True
    key_file = Path(constants.KEY_DIR) / "digitalocean.key"
    return key_file.exists()


def main() -> None:
    """Run a WireWord export or enqueue directory exports."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Create configuration from args (always returns a valid config with defaults)
    config = get_data_source_config(args)

    selected_source_languages = (
        ["en", *SUPPORTED_NON_ENGLISH_SOURCE_LANGUAGES]
        if args.source_language == "all"
        else [args.source_language]
    )

    # Handle Traditional Chinese flag
    language = args.language
    if args.traditional and args.language == "zh":
        language = "zh-Hant"

    # Deprecation warnings for legacy export modes
    if args.mode in ("single", "both"):
        logger.warning(
            "⚠️  --mode %s is DEPRECATED. The directory export now produces "
            "level-range files containing both nouns and verbs.",
            args.mode,
        )

    # Resolve CDN upload: enabled by default when credentials exist,
    # unless --no-cdn-upload is passed.
    cdn_upload = not args.no_cdn_upload and _cdn_credentials_available()
    if not args.no_cdn_upload and not cdn_upload:
        logger.info(
            "CDN upload skipped — no DO Spaces credentials found. "
            "Set DO_SPACES_KEY/DO_SPACES_SECRET or create keys/digitalocean.key."
        )

    if args.use_workqueue:
        if args.mode != "directory":
            raise ValueError("--use-workqueue currently supports only --mode directory")

        with create_session(config) as session:
            queued_total = 0
            for selected_source_language in selected_source_languages:
                dedup_key = (
                    f"{TaskType.WIREWORD_EXPORT_DIRECTORY}:{language}:"
                    f"{selected_source_language}:{args.include_unreviewed_audio}"
                )
                result = enqueue_task(
                    session,
                    task_type=TaskType.WIREWORD_EXPORT_DIRECTORY,
                    target_type="wireword_export",
                    target_id=None,
                    payload={
                        "language": language,
                        "source_language": selected_source_language,
                        "include_unreviewed_audio": args.include_unreviewed_audio,
                        "apply_level_overrides": not args.skip_country_overrides
                        or not args.skip_family_relation_overrides,
                    },
                    dedup_key=dedup_key,
                )
                action = "Enqueued" if result.created else "Already queued"
                logger.info(
                    "%s WireWord directory export task %s for %s from %s",
                    action,
                    result.task.id,
                    language,
                    selected_source_language,
                )
                if result.created:
                    queued_total += 1
            session.commit()
        logger.info("Queued %s source language export task(s)", queued_total)
        return

    if args.source_language == "all" and args.mode != "directory":
        raise ValueError("--source-language all currently supports only --mode directory")

    # Create an exporter with config
    exporter = WirewordExportService(
        config=config,
        language=language,
        include_unreviewed_audio=args.include_unreviewed_audio,
        source_language=selected_source_languages[0],
    )

    # Set default paths if not specified
    if args.mode in ["single", "both"] and not args.output:
        args.output = exporter.get_default_single_file_path()
        logger.info(f"Using default output path: {args.output}")

    # If output_dir not specified for directory mode, it will use language-specific default
    if args.mode in ["directory", "both"] and not args.output_dir:
        args.output_dir = (
            None  # Will trigger use of get_language_output_dir() in export_wireword_directory
        )

    # Run export
    for selected_source_language in selected_source_languages:
        source_exporter = WirewordExportService(
            config=config,
            language=language,
            include_unreviewed_audio=args.include_unreviewed_audio,
            source_language=selected_source_language,
        )
        source_exporter.run_export(
            output_path=args.output,
            output_dir=args.output_dir,
            difficulty_level=args.level,
            pos_type=args.pos_type,
            pos_subtype=args.pos_subtype,
            limit=args.limit,
            include_without_guid=args.include_without_guid,
            include_unverified=args.include_unverified,
            export_mode=args.mode,
            skip_country_overrides=args.skip_country_overrides,
            skip_family_relation_overrides=args.skip_family_relation_overrides,
            cdn_upload=cdn_upload,
        )
