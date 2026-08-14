"""Reporting orchestration for storage-owned integrity checks."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from storage.integrity.checker import IntegrityChecker


def run_integrity_report(
    checker: IntegrityChecker, *, output_file: Optional[Path] = None
) -> Dict[str, Any]:
    """Run every non-audio integrity check and optionally write JSON.

    Audio and pronunciation checks deliberately remain in the Bebras
    compatibility layer until that subsystem is addressed separately.
    """
    started_at = datetime.now()
    results: Dict[str, Any] = {
        "timestamp": started_at.isoformat(),
        "database_path": checker.config.sqlite_path or checker.config.postgres_url or "configured",
        "checks": {
            "orphaned_derivative_forms": checker.check_orphaned_derivative_forms(),
            "derivative_form_word_tokens": checker.check_derivative_form_word_tokens(),
            "missing_required_fields": checker.check_missing_required_fields(),
            "lemmas_without_derivatives": checker.check_lemmas_without_derivatives(),
            "duplicate_guids": checker.check_duplicate_guids(),
            "duplicate_words": checker.check_duplicate_words(),
            "invalid_difficulty_levels": checker.check_invalid_difficulty_levels(),
            "sentences_missing_punctuation": checker.check_sentences_missing_punctuation(),
            "sentence_levels": checker.check_sentence_levels(),
        },
    }
    results["duration_seconds"] = (datetime.now() - started_at).total_seconds()
    if output_file is not None:
        output_file.write_text(
            json.dumps(results, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return results
