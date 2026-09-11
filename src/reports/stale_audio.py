"""Report audio whose text no longer matches the current translation.

Every ``AudioQualityReview`` row records the ``expected_text`` that was spoken
when the file was generated.  When a translation is later corrected, the audio
keeps saying the old word, and nothing in the release round-trip notices: the
file is still present and still valid, just wrong.  This report finds those rows.

Three things count as stale, and the report names which:

``text_mismatch``
    The translation changed after the audio was made.  Regenerating fixes it.
``translation_removed``
    The translation is gone, so the audio has nothing to correspond to.
``no_matching_lemma``
    No lemma carries the GUID any more -- an orphaned audio row.

Read-only by design.  Flagging a row ``needs_replacement`` is a queue operation,
so it belongs with the regeneration workflow in the Audio Hub rather than here;
this report is what tells you there is something to flag.

Usage::

    PYTHONPATH=src python src/reports/stale_audio.py
    PYTHONPATH=src python src/reports/stale_audio.py --language es-419
    PYTHONPATH=src python src/reports/stale_audio.py --output stale_audio.json
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend import create_session
from storage.models.schema import AudioQualityReview, Lemma
from storage.translation_helpers import get_translation

REASON_LABELS = {
    "text_mismatch": "Translation changed after the audio was generated",
    "translation_removed": "Translation no longer exists",
    "no_matching_lemma": "No lemma carries this GUID",
}


def find_stale_audio(session: Any, language: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return the lemma-audio rows whose expected_text is out of date.

    Only lemma audio is checked: a sentence's audio is keyed by sentence_id and
    has no single translation to compare against.
    """
    query = session.query(AudioQualityReview).filter(
        AudioQualityReview.guid.isnot(None),
        AudioQualityReview.sentence_id.is_(None),
    )
    if language:
        query = query.filter(AudioQualityReview.language_code == language)

    stale: List[Dict[str, Any]] = []
    for audio in query.all():
        lemma = session.query(Lemma).filter_by(guid=audio.guid).first()
        row = {
            "audio_id": audio.id,
            "guid": audio.guid,
            "lemma_text": lemma.lemma_text if lemma else None,
            "language_code": audio.language_code,
            "voice_name": audio.voice_name,
            "expected_text": audio.expected_text,
            "status": audio.status,
        }

        if not lemma:
            stale.append({**row, "current_translation": None, "reason": "no_matching_lemma"})
            continue

        current = get_translation(session, lemma, audio.language_code)
        if current is None:
            stale.append({**row, "current_translation": None, "reason": "translation_removed"})
        elif audio.expected_text != current:
            stale.append({**row, "current_translation": current, "reason": "text_mismatch"})

    return stale


def print_report(stale: List[Dict[str, Any]], verbose: bool) -> None:
    """Summarize the stale rows by reason and language."""
    if not stale:
        print("\nNo stale audio found.")
        return

    print(f"\n{len(stale)} stale audio row(s) found.\n")

    by_reason = Counter(row["reason"] for row in stale)
    for reason, count in by_reason.most_common():
        print(f"  {count:>6}  {reason} -- {REASON_LABELS.get(reason, '')}")

    by_language = Counter(row["language_code"] for row in stale)
    print("\nBy language:")
    for language, count in sorted(by_language.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {count:>6}  {language}")

    already_flagged = sum(1 for row in stale if row["status"] == "needs_replacement")
    print(f"\nAlready marked needs_replacement: {already_flagged}")
    print(f"Not yet flagged: {len(stale) - already_flagged}")

    if not verbose:
        return

    print("\nDetail:")
    for row in sorted(stale, key=lambda item: (item["language_code"], item["guid"] or "")):
        print(
            f"  {row['guid']} {row['language_code']:<8} {row['reason']:<20} "
            f"expected={row['expected_text']!r} current={row['current_translation']!r}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument("--language", type=str, default=None, help="Restrict to one language code")
    parser.add_argument("--verbose", action="store_true", help="List every stale row")
    parser.add_argument("--output", type=Path, help="Also write the rows as JSON here")
    args = parser.parse_args()

    config = get_data_source_config(args)
    session = create_session(config)
    try:
        stale = find_stale_audio(session, args.language)
    finally:
        session.close()

    print_report(stale, args.verbose)
    if args.output is not None:
        args.output.write_text(json.dumps(stale, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
