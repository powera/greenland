#!/usr/bin/python3

"""Reports index.

A single listing of the reports in ``src/reports/``.  These are analysis passes
over the database -- coverage cross-tabs, vocabulary distribution, term age --
that answer "what does the data look like right now?".  They are read-only; a
report that changes data carries ``writes: True`` and is marked in the listing.

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

from flask import Blueprint, g, render_template, request
from flask.typing import ResponseReturnValue

from reports.broadly_common_words import (
    DEFAULT_MIN_CORPORA,
    DEFAULT_RUNNER_UP_COUNT,
    DEFAULT_TOP_N,
    build_report,
)

bp = Blueprint("reports", __name__, url_prefix="/reports")


# Every module in src/reports/, with the command that runs it.  "arguments"
# lists the flags worth knowing, not the full argparse surface -- each report
# supports --help, plus the usual --persona/--backend database selection.
# "endpoint" names a page that renders the report per request, for the few that
# are cheap enough to run inside one.
REPORTS: List[Dict[str, Any]] = [
    {
        "name": "broadly_common_words",
        "display_name": "Broadly Common Words",
        "subtitle": "Top 150 in several corpora, and the next most common",
        "description": (
            "Lists the tokens in the top 150 of at least three corpora, by combined "
            "rank, then the 50 best combined ranks not in that list: words common "
            "everywhere without leading enough corpora to qualify."
        ),
        "icon": "bi-stars",
        "command": "PYTHONPATH=src python src/reports/broadly_common_words.py",
        "arguments": [
            "--top-n N",
            "--min-corpora N",
            "--runner-ups N",
            "--output report.json",
        ],
        "endpoint": "reports.broadly_common",
    },
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
        "name": "level_warnings",
        "display_name": "Level Warnings",
        "subtitle": "Problems in the curriculum's level assignments",
        "description": (
            "Warns about core levels outside 20-50 words (ideal 25-40), headwords "
            "with two senses in the core, scattered subtypes, words far rarer than "
            "their level-mates, and senses taught out of order. Warnings only; "
            "it moves nothing."
        ),
        "icon": "bi-exclamation-triangle",
        "command": "PYTHONPATH=src python src/reports/level_warnings.py",
        "arguments": ["--language en", "--max-level 30", "--output report.json"],
    },
    {
        "name": "level_words",
        "display_name": "Words at Each Level",
        "subtitle": "Diffable listing of the curriculum",
        "description": (
            "Writes one text file listing every level's words, grouped by subtype, "
            "for review and diffing."
        ),
        "icon": "bi-list-ol",
        "command": "PYTHONPATH=src python src/reports/level_words.py --output FILE",
        "arguments": [
            "--output FILE (required)",
            "--bands core,named,topic",
        ],
    },
]


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display the list of available reports."""
    return render_template("reports/index.html", reports=REPORTS)


def _int_arg(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


@bp.route("/broadly-common")
def broadly_common() -> ResponseReturnValue:
    """Words in the top N of several corpora, then the next most common words.

    Rendered per request: the core list reads only the annotation rows at or
    above the cutoff, so the whole report is a fraction of a second.
    """
    language_code = request.args.get("language", "en").strip() or "en"
    report = build_report(
        g.db,
        language_code=language_code,
        top_n=_int_arg("top_n", DEFAULT_TOP_N, 1, 5000),
        min_corpora=_int_arg("min_corpora", DEFAULT_MIN_CORPORA, 1, 50),
        runner_up_count=_int_arg("runner_ups", DEFAULT_RUNNER_UP_COUNT, 0, 1000),
    )
    return render_template("reports/broadly_common.html", report=report)
