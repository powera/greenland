#!/usr/bin/python3

"""Reports index.

A single listing of the reports in ``src/reports/``.  These are analysis passes
over the database -- coverage cross-tabs, vocabulary distribution, term age --
that answer "what does the data look like right now?".  Nearly all are
read-only; the exceptions carry ``writes: True`` and are marked in the listing,
since ``curriculum_sense_fixes --apply`` does change data.

Before this page the reports were findable only by listing the directory, and
the Data Quality (bebras) page mixes a couple of them in among its LLM-backed
verification tools.

The registry below is the listing; each entry names the module a report lives in
and the command to run it.  Reports are CLI-run rather than launched from here:
several take minutes over the full lemma table, and their output is a table meant
to be read in a terminal or redirected to a file.  Adding a report means adding
its module to ``src/reports/`` and one entry here.
"""

from typing import Any, Dict, List

from flask import Blueprint, render_template
from flask.typing import ResponseReturnValue

bp = Blueprint("reports", __name__, url_prefix="/reports")


# Every module in src/reports/, with the command that runs it.  "arguments"
# lists the flags worth knowing, not the full argparse surface -- each report
# supports --help, plus the usual --persona/--backend database selection.
REPORTS: List[Dict[str, Any]] = [
    {
        "name": "integrity",
        "display_name": "Database Integrity",
        "subtitle": "Orphans, duplicates, missing fields, bad levels",
        "description": (
            "Runs the structural checks in storage.integrity: orphaned derivative "
            "forms and form-token links, lemmas missing required fields or "
            "inflections, duplicate GUIDs and words, out-of-range difficulty "
            "levels, unpunctuated sentence translations, and sentence levels that "
            "disagree with their linked words. Read-only; the checks' fix paths are "
            "deliberately not exposed here."
        ),
        "icon": "bi-shield-check",
        "command": "PYTHONPATH=src python src/reports/integrity.py",
        "arguments": ["--check NAME (repeatable)", "--verbose", "--output report.json"],
    },
    {
        "name": "stale_audio",
        "display_name": "Stale Audio",
        "subtitle": "Audio whose text no longer matches the translation",
        "description": (
            "Finds audio whose expected_text has drifted from the current "
            "translation, so the file still says the old word. The release "
            "round-trip does not catch this -- the file is present and valid, just "
            "wrong. Flagging rows for regeneration is done from the Audio Hub."
        ),
        "icon": "bi-volume-up",
        "command": "PYTHONPATH=src python src/reports/stale_audio.py",
        "arguments": ["--language CODE", "--verbose", "--output report.json"],
    },
    {
        "name": "translation_coverage_by_level",
        "display_name": "Translation Coverage by Level",
        "subtitle": "Which languages owe words, per difficulty level",
        "description": (
            "Cross-tabs curated lemmas by difficulty level against every language, "
            "showing how many words each language still owes. Used to choose the "
            "language set for a batched Voras run, and to confirm a level range is "
            "complete before a release."
        ),
        "icon": "bi-translate",
        "command": "PYTHONPATH=src python src/reports/translation_coverage_by_level.py",
        "arguments": [
            "--max-level N / --min-level N",
            "--languages es-419 zh-tw de ...",
            "--per-level",
            "--missing-for LANG",
            "--output report.json",
        ],
    },
    {
        "name": "vocabulary_distribution",
        "display_name": "Vocabulary Distribution",
        "subtitle": "Word counts across levels and parts of speech",
        "description": (
            "Reports how curated vocabulary is spread over difficulty levels and "
            "POS types, which shows whether a level is over- or under-filled."
        ),
        "icon": "bi-bar-chart",
        "command": "PYTHONPATH=src python src/reports/vocabulary_distribution.py",
        "arguments": ["--min-subtype-count N", "--output report.json"],
    },
    {
        "name": "missing_words",
        "display_name": "Missing Words",
        "subtitle": "Expected words absent from the dictionary",
        "description": "Lists words that should exist in the dictionary but do not.",
        "icon": "bi-question-circle",
        "command": "PYTHONPATH=src python src/reports/missing_words.py",
        "arguments": ["--top-n N", "--min-rank N", "--output report.json"],
    },
    {
        "name": "wordlist_coverage",
        "display_name": "Wordlist Coverage",
        "subtitle": "Dictionary coverage of an external word list",
        "description": (
            "Parses a wikitext-format English word list and reports which of its "
            "content words the dictionary already covers, ignoring grammatical words."
        ),
        "icon": "bi-list-check",
        "command": "PYTHONPATH=src python src/reports/wordlist_coverage.py WORDLIST",
        "arguments": ["WORDLIST (positional)", "--output report.json"],
    },
    {
        "name": "term_age",
        "display_name": "Term Age",
        "subtitle": "How long terms have been in the database",
        "description": "Reports the age distribution of terms, from their added-at timestamps.",
        "icon": "bi-clock-history",
        "command": "PYTHONPATH=src python src/reports/term_age.py",
        "arguments": ["--level N / --level 3-8", "--pos-type noun", "--output report.json"],
    },
    {
        "name": "curriculum_relevel",
        "display_name": "Curriculum Relevel",
        "subtitle": "Analysis behind the level reassignment",
        "description": (
            "Analysis supporting the curriculum relevel that split the old 30 levels "
            "into 65 smaller ones, so no level imposes 100+ new words at once."
        ),
        "icon": "bi-sort-numeric-down",
        "command": "PYTHONPATH=src python src/reports/curriculum_relevel.py --output-dir DIR",
        "arguments": ["--output-dir DIR (required)", "--mode auto|rebuild|incremental"],
    },
    {
        "name": "curriculum_sense_fixes",
        "display_name": "Curriculum Sense Fixes",
        "subtitle": "Word senses needing disambiguation review",
        "description": (
            "Orders the senses of a shared English headword by stored prominence. "
            "Previews the corrections by default; --apply writes them, so this one "
            "is not read-only."
        ),
        "icon": "bi-signpost-split",
        "command": "PYTHONPATH=src python src/reports/curriculum_sense_fixes.py",
        "arguments": ["--apply (writes changes)"],
        "writes": True,
    },
]


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display the list of available reports."""
    return render_template("reports/index.html", reports=REPORTS)
