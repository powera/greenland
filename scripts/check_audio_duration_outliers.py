#!/usr/bin/env python3
"""Report suspicious local word audio without changing reviews or calling APIs.

Example:
    GREENLAND_TEST_MODE=1 PYTHONPATH=src python scripts/check_audio_duration_outliers.py \
        --audio-root data/audio_runs --audio-root /path/to/vieversys_run \
        --output /tmp/audio-duration-outliers.csv

Only files matching the database's current content hash are considered. Dialect
ratios require the same GUID, voice, grammatical form, and normalized spoken text.
Flags are review candidates, not automatic rejection verdicts.
"""

import argparse
import csv
import hashlib
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

if str(Path(__file__).resolve().parent.parent / "src") not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.models.schema import AudioQualityReview


@dataclass(frozen=True)
class Recording:
    review_id: int
    guid: str
    language: str
    voice: str
    form: str
    text: str
    path: Path
    seconds: float


def normalized_text(text: str) -> str:
    """Ignore case and whitespace, but preserve lexical and accent differences."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return float(result.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-root", type=Path, action="append", required=True)
    parser.add_argument("--db-path", help="SQLite database; defaults to project configuration")
    parser.add_argument("--language", default="es")
    parser.add_argument("--reference-language", default="es-419")
    parser.add_argument("--ratio", type=float, default=2.0)
    parser.add_argument("--minimum-excess", type=float, default=1.0)
    parser.add_argument("--long-word-seconds", type=float, default=3.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.ratio <= 1 or args.minimum_excess < 0 or args.long_word_seconds <= 0:
        parser.error("ratio must exceed 1 and duration thresholds must be nonnegative")

    # Index by relative language/voice/filename; verify hashes below so old runs
    # cannot silently stand in for the audio currently linked in the review UI.
    local_files: dict[tuple[str, str, str], list[Path]] = {}
    for root in args.audio_root:
        if not root.is_dir():
            parser.error(f"Audio root does not exist: {root}")
        for audio_path in root.rglob("*.mp3"):
            file_key = (audio_path.parent.parent.name, audio_path.parent.name, audio_path.name)
            local_files.setdefault(file_key, []).append(audio_path.resolve())

    session = create_session(DataSourceConfig(sqlite_path=args.db_path))
    matched: list[tuple[AudioQualityReview, Path]] = []
    missing = 0
    try:
        reviews = (
            session.query(AudioQualityReview)
            .filter(
                AudioQualityReview.language_code.in_([args.language, args.reference_language]),
                AudioQualityReview.guid.isnot(None),
                AudioQualityReview.sentence_id.is_(None),
            )
            .all()
        )
        for review in reviews:
            candidates = local_files.get(
                (review.language_code, review.voice_name, review.filename), []
            )
            current_file = next(
                (
                    candidate
                    for candidate in candidates
                    if hashlib.md5(candidate.read_bytes()).hexdigest() == review.manifest_md5
                ),
                None,
            )
            if current_file is None:
                missing += 1
            else:
                matched.append((review, current_file))
        with ThreadPoolExecutor(max_workers=8) as executor:
            lengths = list(executor.map(duration, [item[1] for item in matched]))
        recordings = [
            Recording(
                review.id,
                review.guid or "",
                review.language_code,
                review.voice_name,
                review.grammatical_form or "",
                review.expected_text,
                audio_file,
                seconds,
            )
            for (review, audio_file), seconds in zip(matched, lengths)
        ]
    finally:
        session.close()

    references = {
        (item.guid, item.voice, item.form, normalized_text(item.text)): item
        for item in recordings
        if item.language == args.reference_language
    }
    findings: list[dict[str, str | int | float]] = []
    compared = 0
    for recording in recordings:
        if recording.language != args.language:
            continue
        reference = references.get(
            (recording.guid, recording.voice, recording.form, normalized_text(recording.text))
        )
        reasons: list[str] = []
        ratio = 0.0
        if reference is not None and reference.seconds > 0:
            compared += 1
            ratio = recording.seconds / reference.seconds
            if ratio >= args.ratio and recording.seconds - reference.seconds >= args.minimum_excess:
                reasons.append("longer_than_identical_reference")
        if len(recording.text.split()) == 1 and recording.seconds >= args.long_word_seconds:
            reasons.append("long_single_word")
        if reasons:
            findings.append(
                {
                    "review_id": recording.review_id,
                    "guid": recording.guid,
                    "language": recording.language,
                    "voice": recording.voice,
                    "text": recording.text,
                    "seconds": round(recording.seconds, 3),
                    "reference_seconds": round(reference.seconds, 3) if reference else "",
                    "ratio": round(ratio, 2) if reference else "",
                    "flags": ";".join(reasons),
                    "path": str(recording.path),
                }
            )
    findings.sort(key=lambda item: float(item["seconds"]), reverse=True)
    fields = [
        "review_id",
        "guid",
        "language",
        "voice",
        "text",
        "seconds",
        "reference_seconds",
        "ratio",
        "flags",
        "path",
    ]
    with args.output.open("w", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(findings)
    print(
        f"Measured {len(recordings)} current files; {missing} reviews lack a matching local file."
    )
    print(
        f"Compared {compared} identical-text pairs; flagged {len(findings)} candidates: {args.output}"
    )


if __name__ == "__main__":
    main()
