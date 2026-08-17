#!/usr/bin/python3

"""Routes for syncing data between data/release and SQLite database."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from barsukas.routes.sync import release_io
from barsukas.routes.sync.actions import (
    SKIP,
    USE_DB,
    USE_RELEASE,
    SyncOutcome,
    bulk_actions_for,
    is_readonly,
    parse_bulk_request,
    parse_language_actions,
    parse_row_actions,
)
from barsukas.routes.sync.paging import PER_PAGE_CHOICES, page_args, paginate
from storage.config.grammar_facts import (
    get_release_grammar_fact_languages,
    is_release_grammar_fact_type,
)
from sqlalchemy.orm import object_session

from storage.crud.concept import (
    get_qid_for_lemma,
    link_lemma_to_concept,
    unlink_lemma_from_concept,
)
from storage.wikidata import normalize_qid
from storage.crud.operation_log import log_operation, log_translation_change
from storage.models.grammar_fact import GrammarFact
from storage.models.schema import Lemma, LemmaTranslation
from storage.translation_helpers import (
    EXTRA_RELEASE_LANGUAGE_GROUPS,
    LANGUAGE_NAMES,
    RELEASE_LANGUAGES,
    SECONDARY_RELEASE_LANGUAGES,
    compute_sort_key,
    invalidate_audio_for_translation_change,
)

logger = logging.getLogger(__name__)

bp = Blueprint("sync_release", __name__, url_prefix="/sync/lemmas")

# Default path to data/release/lemmas
# __file__ is src/barsukas/routes/sync/sync_release.py
# .parent = sync/, .parent.parent = routes/, .parent.parent.parent = barsukas/,
# .parent.parent.parent.parent = src/, .parent.parent.parent.parent.parent = repo root
DEFAULT_RELEASE_DIR = (
    Path(__file__).parent.parent.parent.parent.parent / "data" / "release" / "lemmas"
)


# Marks a per-language *disambiguation* inside a translation-update dict, so the
# translations mode can queue a translation and its disambiguation together and
# have release_io route each to the right key.
_DISAMBIG_PREFIX = "_disambig_"


def _get_release_dir() -> Path:
    """Get the path to the data/release/lemmas directory."""
    return DEFAULT_RELEASE_DIR


def _load_release_lemmas(release_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Load all lemmas from data/release base.jsonl files, keyed by GUID."""
    return release_io.load_release_records(release_dir)


def _load_release_grammar_facts(
    release_dir: Path,
) -> Dict[str, List[Dict[str, str]]]:
    """Load grammar facts from per-language JSONL files in data/release/lemmas.

    Only loads fact types allowed by the shared grammar fact registry.

    Returns:
        Dictionary mapping GUID to list of {fact_type, fact_value, language_code}.
    """
    grammar_facts: Dict[str, List[Dict[str, str]]] = {}

    if not release_dir.exists():
        return grammar_facts

    for lang_code in get_release_grammar_fact_languages():
        lang_filename = f"{lang_code}.jsonl"
        for lang_file in release_dir.rglob(lang_filename):
            try:
                with open(lang_file, "r", encoding="utf-8") as f:
                    for line_num, raw_line in enumerate(f, 1):
                        raw_line = raw_line.strip()
                        if not raw_line:
                            continue
                        try:
                            data = json.loads(raw_line)
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON parse error in {lang_file}:{line_num}: {e}")
                            continue

                        guid = data.get("guid")
                        if not guid:
                            continue

                        facts_list = data.get("grammar_facts", [])
                        for fact in facts_list:
                            fact_type = fact.get("fact_type", "")
                            fact_value = fact.get("fact_value", "")
                            if is_release_grammar_fact_type(lang_code, fact_type) and fact_value:
                                if guid not in grammar_facts:
                                    grammar_facts[guid] = []
                                grammar_facts[guid].append(
                                    {
                                        "fact_type": fact_type,
                                        "fact_value": fact_value,
                                        "language_code": lang_code,
                                    }
                                )
            except Exception as e:
                logger.error(f"Error reading {lang_file}: {e}")

    return grammar_facts


def _parse_concept_label(concept_label: str) -> Tuple[str, Optional[str]]:
    """Parse concept_label into (word, disambiguation).

    E.g. "sharp (pointed)" -> ("sharp", "pointed"),
         "dog" -> ("dog", None).
    """
    match = re.match(r"^(.+?)\s+\(([^)]+)\)$", concept_label)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return concept_label, None


def _get_release_disambiguation(release_data: Dict[str, Any]) -> Optional[str]:
    """Extract disambiguation from release data's concept_label."""
    concept_label = release_data.get("concept_label", "")
    if not concept_label:
        return None
    _, disambiguation = _parse_concept_label(concept_label)
    return disambiguation


def _normalize_emoji_entry(item: Any) -> Optional[Dict[str, str]]:
    """Coerce one emoji-list item into a {type, value} dict, or None if invalid.

    Accepts either the canonical dict form or a bare Unicode string (legacy).
    """
    if isinstance(item, dict):
        entry_type = str(item.get("type", "")).strip()
        value = str(item.get("value", "")).strip()
        if entry_type in ("unicode", "image") and value:
            return {"type": entry_type, "value": value}
        return None
    if isinstance(item, str) and item.strip():
        return {"type": "unicode", "value": item.strip()}
    return None


def _normalize_emoji_list(raw: Any) -> List[Dict[str, str]]:
    """Normalize any emoji-list shape into a list of {type, value} dicts."""
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for item in raw:
        entry = _normalize_emoji_entry(item)
        if entry is not None:
            out.append(entry)
    return out


def _decode_db_emoji(raw: Optional[str]) -> List[Dict[str, str]]:
    """Decode the JSON-encoded emoji list stored on Lemma.emoji.

    Returns [] for null/empty/unparseable values so equality comparisons with
    a missing release-side list ("emoji" key absent) treat both as "no emoji".
    """
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return _normalize_emoji_list(value)


def _get_release_emoji(release_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract the emoji list from release base.jsonl data (missing -> [])."""
    return _normalize_emoji_list(release_data.get("emoji"))


def _format_emoji_for_display(entries: List[Dict[str, str]]) -> str:
    """Render an emoji list as a short human-readable string for diff rows.

    Unicode entries render as the glyph; image entries render as
    "[img:filename]" so reviewers can tell them apart on the sync page.
    """
    parts: List[str] = []
    for entry in entries:
        if entry.get("type") == "image":
            parts.append(f"[img:{entry.get('value', '')}]")
        else:
            parts.append(entry.get("value", ""))
    return " ".join(parts)


def _get_release_lemma_text(release_data: Dict[str, Any]) -> str:
    """Extract lemma_text from release data."""
    translations = release_data.get("translations", {})
    en_text = translations.get("en")
    if en_text:
        return str(en_text)
    concept_label = release_data.get("concept_label", "")
    return str(concept_label) if concept_label else ""


# =============================================================================
# Hub / Index
# =============================================================================


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display sync hub with links to all sync modes."""
    release_dir = _get_release_dir()

    # Check if release directory exists
    if not release_dir.exists():
        return render_template(
            "sync_release/index.html",
            release_dir=str(release_dir),
            error="Release directory not found",
            counts=None,
        )

    # Load release lemmas
    release_lemmas = _load_release_lemmas(release_dir)
    if not release_lemmas:
        return render_template(
            "sync_release/index.html",
            release_dir=str(release_dir),
            release_count=0,
            counts=None,
        )

    # Get all DB GUIDs
    db_guids = set(guid for (guid,) in g.db.query(Lemma.guid).all() if guid)
    release_guids = set(release_lemmas.keys())

    # Calculate counts for each category
    additions = release_guids - db_guids
    removals = db_guids - release_guids
    common_guids = release_guids & db_guids

    # Count difficulty differences (among common GUIDs with matching lemma_text).
    # Base-info changes (lemma_text, disambiguation, concept_definition, notes,
    # emoji) are counted together via _find_lemma_text_changes — any base-field
    # diff bumps the same "changes" counter shown on the hub.
    difficulty_diffs = 0
    lemma_text_changes = len(_find_lemma_text_changes(release_lemmas, g.db))

    # Query common GUIDs in batches for difficulty-only diffs (skip rows that
    # already have a base-info change so we don't double-count).
    batch_size = 500
    common_list = list(common_guids)
    for i in range(0, len(common_list), batch_size):
        batch = common_list[i : i + batch_size]
        db_lemmas = g.db.query(Lemma).filter(Lemma.guid.in_(batch)).all()

        for db_lemma in db_lemmas:
            release_data = release_lemmas.get(db_lemma.guid)
            if not release_data:
                continue

            release_text = _get_release_lemma_text(release_data)
            if db_lemma.lemma_text != release_text:
                continue
            if release_data.get("difficulty_level") != db_lemma.difficulty_level:
                difficulty_diffs += 1

    # Count translation differences (only for matching lemmas)
    translation_diffs = _count_translation_differences(release_lemmas, g.db)

    # Count secondary translation differences
    sec_translations = _load_secondary_translations(release_dir)
    secondary_translation_diffs = _count_secondary_translation_differences(
        release_lemmas, sec_translations, g.db
    )

    # Count grammar fact differences for existing GUIDs
    release_grammar = _load_release_grammar_facts(release_dir)
    grammar_fact_diffs = len(_find_grammar_fact_differences(release_grammar, g.db))

    counts = {
        "release_total": len(release_lemmas),
        "db_total": len(db_guids),
        "additions": len(additions),
        "removals": len(removals),
        "difficulty": difficulty_diffs,
        "changes": lemma_text_changes,
        "translations": translation_diffs,
        "secondary_translations": secondary_translation_diffs,
        "grammar_facts": grammar_fact_diffs,
    }

    return render_template(
        "sync_release/index.html",
        release_dir=str(release_dir),
        counts=counts,
    )


# =============================================================================
# Difficulty Sync
# =============================================================================


def _find_difficulty_differences(
    release_lemmas: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find lemmas where difficulty_level differs between release and SQLite."""
    differences: List[Dict[str, Any]] = []
    release_guids = set(release_lemmas.keys())

    if not release_guids:
        return differences

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch_guids)).all()

        for db_lemma in db_lemmas:
            release_data = release_lemmas.get(db_lemma.guid)
            if not release_data:
                continue

            release_lemma_text = _get_release_lemma_text(release_data)

            # Skip if lemma_text differs
            if db_lemma.lemma_text != release_lemma_text:
                continue

            release_level = release_data.get("difficulty_level")
            db_level = db_lemma.difficulty_level

            if release_level == db_level:
                continue

            differences.append(
                {
                    "guid": db_lemma.guid,
                    "lemma_id": db_lemma.id,
                    "lemma_text": db_lemma.lemma_text,
                    "definition": db_lemma.definition_text[:80] if db_lemma.definition_text else "",
                    "pos_type": db_lemma.pos_type,
                    "pos_subtype": db_lemma.pos_subtype,
                    "release_level": release_level,
                    "db_level": db_level,
                }
            )

    differences.sort(key=lambda x: x["guid"])
    return differences


@bp.route("/difficulty")
def difficulty() -> ResponseReturnValue:
    """Display difficulty level differences."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_release.index"))

    release_lemmas = _load_release_lemmas(release_dir)
    if not release_lemmas:
        flash("No lemmas found in release directory", "warning")
        return redirect(url_for("sync_release.index"))

    differences = _find_difficulty_differences(release_lemmas, g.db)

    return render_template(
        "sync_release/difficulty.html",
        page=paginate(differences),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
        release_count=len(release_lemmas),
    )


@bp.route("/difficulty/apply", methods=["POST"])
def apply_difficulty() -> ResponseReturnValue:
    """Apply selected difficulty level changes."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_release.difficulty"))

    release_dir = _get_release_dir()
    release_lemmas = _load_release_lemmas(release_dir)

    bulk = parse_bulk_request()
    if bulk is not None:
        differences = _find_difficulty_differences(release_lemmas, g.db)
        expanded = bulk_actions_for(
            bulk, (diff["lemma_id"] for diff in differences), total=len(differences)
        )
        if expanded is None:
            return redirect(url_for("sync_release.difficulty"))
        actions = expanded
    else:
        actions = parse_row_actions()

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_release.difficulty"))

    outcome = SyncOutcome(noun="lemma")
    guid_files = release_io.build_guid_file_index(release_dir)
    release_updates: Dict[Path, Dict[str, Dict[str, Any]]] = {}

    for lemma_id_str, action in actions.items():
        if action == SKIP:
            outcome.skipped += 1
            continue
        if action not in (USE_RELEASE, USE_DB):
            continue

        try:
            lemma = g.db.query(Lemma).filter(Lemma.id == int(lemma_id_str)).first()
            if not lemma:
                outcome.record_error(f"Lemma not found: {lemma_id_str}")
                continue

            release_data = release_lemmas.get(lemma.guid)
            if not release_data:
                outcome.record_error(f"Release data not found for GUID: {lemma.guid}")
                continue

            if action == USE_RELEASE:
                new_level = release_data.get("difficulty_level")
                old_level = lemma.difficulty_level
                lemma.difficulty_level = new_level
                outcome.updated_db += 1

                log_translation_change(
                    session=g.db,
                    source="sync-release",
                    operation_type="difficulty_sync",
                    lemma_id=lemma.id,
                    field_name="difficulty_level",
                    old_value=str(old_level) if old_level is not None else None,
                    new_value=str(new_level) if new_level is not None else None,
                )
                logger.info(
                    f"Updated difficulty for '{lemma.lemma_text}' ({lemma.guid}): "
                    f"{old_level} -> {new_level}"
                )
            else:  # USE_DB
                file_path = release_io.file_for_guid(guid_files, lemma.guid)
                if file_path is None:
                    outcome.record_error(f"Could not find release file for GUID: {lemma.guid}")
                    continue
                release_updates.setdefault(file_path, {})[lemma.guid] = {
                    "difficulty_level": lemma.difficulty_level,
                }
                outcome.updated_release += 1

        except Exception as e:
            outcome.record_error(f"Error updating lemma {lemma_id_str}: {e}")

    outcome.commit(g.db)
    _write_release_updates(release_updates, outcome)
    outcome.flash_summary()
    return redirect(url_for("sync_release.difficulty"))


def _write_release_updates(
    release_updates: Dict[Path, Dict[str, Dict[str, Any]]], outcome: SyncOutcome
) -> None:
    """Flush queued release-file field updates, reporting a failure as an error."""
    if not release_updates:
        return
    try:
        release_io.apply_field_updates(release_updates)
    except Exception as e:  # noqa: BLE001 - surfaced to the user
        logger.error(f"Release file update error: {e}")
        flash(f"Error updating release files: {e}", "error")
        outcome.updated_release = 0
        outcome.errors += 1


# =============================================================================
# Additions (GUIDs in release but not in SQLite)
# =============================================================================


def _find_additions(
    release_lemmas: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find GUIDs in release that don't exist in SQLite."""
    additions: List[Dict[str, Any]] = []

    db_guids = set(guid for (guid,) in db_session.query(Lemma.guid).all() if guid)
    release_guids = set(release_lemmas.keys())

    new_guids = release_guids - db_guids

    for guid in sorted(new_guids):
        release_data = release_lemmas[guid]
        lemma_text = _get_release_lemma_text(release_data)

        additions.append(
            {
                "guid": guid,
                "lemma_text": lemma_text,
                "disambiguation": _get_release_disambiguation(release_data),
                "definition": (release_data.get("concept_definition", "") or "")[:80],
                "pos_type": release_data.get("pos_type", ""),
                "pos_subtype": release_data.get("pos_subtype", ""),
                "difficulty_level": release_data.get("difficulty_level"),
                "translations": release_data.get("translations", {}),
            }
        )

    return additions


@bp.route("/additions")
def additions() -> ResponseReturnValue:
    """Display GUIDs in release that don't exist in SQLite."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_release.index"))

    release_lemmas = _load_release_lemmas(release_dir)
    if not release_lemmas:
        flash("No lemmas found in release directory", "warning")
        return redirect(url_for("sync_release.index"))

    additions_list = _find_additions(release_lemmas, g.db)

    return render_template(
        "sync_release/additions.html",
        page=paginate(additions_list),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
    )


@bp.route("/additions/apply", methods=["POST"])
def apply_additions() -> ResponseReturnValue:
    """Import selected new lemmas from release."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_release.additions"))

    release_dir = _get_release_dir()
    release_lemmas = _load_release_lemmas(release_dir)
    release_grammar_facts = _load_release_grammar_facts(release_dir)

    if request.form.get("select_scope") == "all":
        selected_guids = [item["guid"] for item in _find_additions(release_lemmas, g.db)]
    else:
        selected_guids = request.form.getlist("selected_guids")

    if not selected_guids:
        flash("No lemmas selected for import", "warning")
        return redirect(url_for("sync_release.additions"))

    outcome = SyncOutcome(noun="lemma")
    grammar_fact_count = 0

    for guid in selected_guids:
        release_data = release_lemmas.get(guid)
        if not release_data:
            outcome.record_error(f"Release data not found for GUID: {guid}")
            continue

        try:
            lemma_text = _get_release_lemma_text(release_data)

            lemma = Lemma(
                guid=guid,
                lemma_text=lemma_text,
                disambiguation=_get_release_disambiguation(release_data),
                definition_text=release_data.get("concept_definition", ""),
                pos_type=release_data.get("pos_type", ""),
                pos_subtype=release_data.get("pos_subtype"),
                difficulty_level=release_data.get("difficulty_level"),
            )
            g.db.add(lemma)
            g.db.flush()  # Get the ID

            # Add translations
            translations = release_data.get("translations", {})
            translation_disambiguations = release_data.get("translation_disambiguations", {})
            translation_metadata = release_data.get("translation_metadata", {})
            for lang_code, translation_text in translations.items():
                if lang_code == "en":  # English is stored as lemma_text
                    continue
                if not translation_text:
                    continue
                lang_metadata = translation_metadata.get(lang_code, {})

                trans = LemmaTranslation(
                    lemma_id=lemma.id,
                    language_code=lang_code,
                    translation=translation_text,
                    disambiguation=translation_disambiguations.get(lang_code),
                    translation_status=lang_metadata.get("translation_status"),
                    translation_status_note=lang_metadata.get("translation_status_note"),
                    sort_key=compute_sort_key(lang_code, translation_text),
                    verified=False,
                )
                g.db.add(trans)

            # Add grammar facts from language files
            guid_facts = release_grammar_facts.get(guid, [])
            for fact_entry in guid_facts:
                grammar_fact = GrammarFact(
                    lemma_id=lemma.id,
                    language_code=fact_entry["language_code"],
                    fact_type=fact_entry["fact_type"],
                    fact_value=fact_entry["fact_value"],
                )
                g.db.add(grammar_fact)
                grammar_fact_count += 1

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="lemma_import",
                lemma_id=lemma.id,
                details={
                    "lemma_text": lemma_text,
                    "guid": guid,
                    "pos_type": release_data.get("pos_type", ""),
                    "translation_count": len(translations),
                    "grammar_fact_count": len(guid_facts),
                },
            )

            outcome.imported += 1
            logger.info(f"Imported lemma '{lemma_text}' ({guid})")

        except Exception as e:
            outcome.record_error(f"Error importing GUID {guid}: {e}")

    if grammar_fact_count:
        outcome.details.append(f"{grammar_fact_count} grammar fact(s)")
    outcome.commit(g.db)
    outcome.flash_summary()
    return redirect(url_for("sync_release.additions"))


# =============================================================================
# Grammar Facts (upsert grammar facts for existing GUIDs)
# =============================================================================


def _find_grammar_fact_differences(
    release_grammar_facts: Dict[str, List[Dict[str, str]]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find existing GUIDs where grammar facts differ between release and DB.

    Returns list of dicts with guid, lemma_id, lemma_text, and per-fact diffs.
    """
    differences: List[Dict[str, Any]] = []

    # Only look at GUIDs that exist in DB
    guids_with_facts = list(release_grammar_facts.keys())
    if not guids_with_facts:
        return differences

    batch_size = 500
    for i in range(0, len(guids_with_facts), batch_size):
        batch = guids_with_facts[i : i + batch_size]
        db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch)).all()

        # Batch-load all grammar facts for these lemmas to avoid N+1 queries
        lemma_ids = [db_lemma.id for db_lemma in db_lemmas]
        all_db_facts = (
            db_session.query(GrammarFact).filter(GrammarFact.lemma_id.in_(lemma_ids)).all()
        )
        # Index by (lemma_id, language_code, fact_type) for O(1) lookup
        db_facts_index: Dict[Tuple[int, str, str], str] = {
            (f.lemma_id, f.language_code, f.fact_type): f.fact_value for f in all_db_facts
        }

        for db_lemma in db_lemmas:
            release_facts = release_grammar_facts.get(db_lemma.guid, [])
            fact_diffs: List[Dict[str, Optional[str]]] = []

            for rel_fact in release_facts:
                lang_code = rel_fact["language_code"]
                fact_type = rel_fact["fact_type"]
                release_value = rel_fact["fact_value"]

                db_value = db_facts_index.get((db_lemma.id, lang_code, fact_type))

                if db_value != release_value:
                    fact_diffs.append(
                        {
                            "language_code": lang_code,
                            "fact_type": fact_type,
                            "release_value": release_value,
                            "db_value": db_value,
                        }
                    )

            if fact_diffs:
                differences.append(
                    {
                        "guid": db_lemma.guid,
                        "lemma_id": db_lemma.id,
                        "lemma_text": db_lemma.lemma_text,
                        "pos_type": db_lemma.pos_type,
                        "fact_diffs": fact_diffs,
                    }
                )

    differences.sort(key=lambda x: x["guid"])
    return differences


@bp.route("/grammar-facts")
def grammar_facts() -> ResponseReturnValue:
    """Display grammar fact differences for existing GUIDs."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_release.index"))

    release_grammar = _load_release_grammar_facts(release_dir)
    if not release_grammar:
        flash("No grammar facts found in release directory", "warning")
        return redirect(url_for("sync_release.index"))

    differences = _find_grammar_fact_differences(release_grammar, g.db)

    return render_template(
        "sync_release/grammar_facts.html",
        page=paginate(differences),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
    )


@bp.route("/grammar-facts/apply", methods=["POST"])
def apply_grammar_facts() -> ResponseReturnValue:
    """Upsert selected grammar facts from release into DB."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_release.grammar_facts"))

    release_dir = _get_release_dir()
    release_grammar = _load_release_grammar_facts(release_dir)

    if request.form.get("select_scope") == "all":
        selected_guids = [
            diff["guid"] for diff in _find_grammar_fact_differences(release_grammar, g.db)
        ]
    else:
        selected_guids = request.form.getlist("selected_guids")

    if not selected_guids:
        flash("No lemmas selected for grammar fact sync", "warning")
        return redirect(url_for("sync_release.grammar_facts"))

    outcome = SyncOutcome(noun="grammar fact")
    updated_count = 0
    added_count = 0

    for guid in selected_guids:
        release_facts = release_grammar.get(guid, [])
        if not release_facts:
            continue

        db_lemma = g.db.query(Lemma).filter(Lemma.guid == guid).first()
        if not db_lemma:
            outcome.record_error(f"Lemma not found for GUID: {guid}")
            continue

        try:
            guid_updated = 0
            guid_added = 0
            for rel_fact in release_facts:
                lang_code = rel_fact["language_code"]
                fact_type = rel_fact["fact_type"]
                release_value = rel_fact["fact_value"]

                existing = (
                    g.db.query(GrammarFact)
                    .filter(
                        GrammarFact.lemma_id == db_lemma.id,
                        GrammarFact.language_code == lang_code,
                        GrammarFact.fact_type == fact_type,
                    )
                    .first()
                )

                if existing:
                    if existing.fact_value != release_value:
                        old_value = existing.fact_value
                        existing.fact_value = release_value
                        guid_updated += 1
                        logger.info(
                            f"Updated grammar fact for '{db_lemma.lemma_text}' "
                            f"({guid}): {fact_type} {old_value} -> {release_value}"
                        )
                else:
                    new_fact = GrammarFact(
                        lemma_id=db_lemma.id,
                        language_code=lang_code,
                        fact_type=fact_type,
                        fact_value=release_value,
                    )
                    g.db.add(new_fact)
                    guid_added += 1
                    logger.info(
                        f"Added grammar fact for '{db_lemma.lemma_text}' "
                        f"({guid}): {fact_type}={release_value}"
                    )

            updated_count += guid_updated
            added_count += guid_added

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="grammar_fact_sync",
                lemma_id=db_lemma.id,
                details={
                    "guid": guid,
                    "lemma_text": db_lemma.lemma_text,
                    "facts_updated": guid_updated,
                    "facts_added": guid_added,
                },
            )

        except Exception as e:
            outcome.record_error(f"Error syncing grammar facts for GUID {guid}: {e}")

    # Both an upsert of an existing fact and a brand-new one are reported as
    # "updated"; the added/updated split rides along in the detail line.
    outcome.updated_db = updated_count + added_count
    if added_count:
        outcome.details.append(f"{added_count} added")
    if updated_count:
        outcome.details.append(f"{updated_count} changed")
    outcome.commit(g.db)
    outcome.flash_summary()
    return redirect(url_for("sync_release.grammar_facts"))


# =============================================================================
# Removals (GUIDs in SQLite but not in release)
# =============================================================================


def _find_removals(
    release_lemmas: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find GUIDs in SQLite that don't exist in release."""
    removals: List[Dict[str, Any]] = []

    db_guids = set(guid for (guid,) in db_session.query(Lemma.guid).all() if guid)
    release_guids = set(release_lemmas.keys())

    removed_guids = db_guids - release_guids

    # Query DB for these lemmas
    if removed_guids:
        batch_size = 500
        guid_list = list(removed_guids)

        for i in range(0, len(guid_list), batch_size):
            batch = guid_list[i : i + batch_size]
            db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch)).all()

            for lemma in db_lemmas:
                removals.append(
                    {
                        "guid": lemma.guid,
                        "lemma_id": lemma.id,
                        "lemma_text": lemma.lemma_text,
                        "definition": lemma.definition_text[:80] if lemma.definition_text else "",
                        "pos_type": lemma.pos_type,
                        "pos_subtype": lemma.pos_subtype,
                        "difficulty_level": lemma.difficulty_level,
                    }
                )

    removals.sort(key=lambda x: x["guid"])
    return removals


@bp.route("/removals")
def removals() -> ResponseReturnValue:
    """Display GUIDs in SQLite that don't exist in release."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_release.index"))

    release_lemmas = _load_release_lemmas(release_dir)
    # Note: empty release_lemmas is valid here - we're looking for DB entries not in release

    removals_list = _find_removals(release_lemmas, g.db)

    return render_template(
        "sync_release/removals.html",
        page=paginate(removals_list),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
    )


def _selected_removal_ids() -> List[str]:
    """The lemma ids this submit targets.

    Deletion is never widened to the whole list from a "select all" button: the
    export button beside it is the safe bulk action, and a one-click delete of
    every DB-only lemma is not something this page should offer.
    """
    return request.form.getlist("selected_ids")


@bp.route("/removals/apply", methods=["POST"])
def apply_removals() -> ResponseReturnValue:
    """Delete selected lemmas that are not in release."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_release.removals"))

    selected_ids = _selected_removal_ids()
    if not selected_ids:
        flash("No lemmas selected for deletion", "warning")
        return redirect(url_for("sync_release.removals"))

    outcome = SyncOutcome(noun="lemma")

    for lemma_id_str in selected_ids:
        try:
            lemma = g.db.query(Lemma).filter(Lemma.id == int(lemma_id_str)).first()
            if not lemma:
                outcome.record_error(f"Lemma not found: {lemma_id_str}")
                continue

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="lemma_delete",
                lemma_id=lemma.id,
                details={
                    "lemma_text": lemma.lemma_text,
                    "guid": lemma.guid,
                    "pos_type": lemma.pos_type,
                },
            )

            logger.info(f"Deleting lemma '{lemma.lemma_text}' ({lemma.guid})")
            g.db.delete(lemma)
            outcome.deleted += 1

        except Exception as e:
            outcome.record_error(f"Error deleting lemma {lemma_id_str}: {e}")

    outcome.commit(g.db)
    outcome.flash_summary()
    return redirect(url_for("sync_release.removals"))


def _build_release_entry_from_db(lemma: Lemma) -> Dict[str, Any]:
    """Build a data/release base.jsonl entry from a Lemma and its translations."""
    # Build translations dict with en first (from lemma_text), then RELEASE_LANGUAGES order
    translations: Dict[str, str] = {"en": lemma.lemma_text}
    translation_disambiguations: Dict[str, str] = {}
    translation_metadata: Dict[str, Dict[str, str]] = {}

    lang_to_trans: Dict[str, LemmaTranslation] = {t.language_code: t for t in lemma.translations}

    for lang_code in RELEASE_LANGUAGES:
        if lang_code == "en":
            continue
        trans_obj = lang_to_trans.get(lang_code)
        if trans_obj and trans_obj.translation:
            translations[lang_code] = trans_obj.translation
            if trans_obj.disambiguation:
                translation_disambiguations[lang_code] = trans_obj.disambiguation
            metadata: Dict[str, str] = {}
            if trans_obj.translation_status:
                metadata["translation_status"] = trans_obj.translation_status
            if trans_obj.translation_status_note:
                metadata["translation_status_note"] = trans_obj.translation_status_note
            if metadata:
                translation_metadata[lang_code] = metadata

    # Build concept_label: "word (disambiguation)" if disambiguation exists
    concept_label = lemma.lemma_text
    if lemma.disambiguation:
        concept_label = f"{lemma.lemma_text} ({lemma.disambiguation})"

    entry: Dict[str, Any] = {
        "guid": lemma.guid,
        "pos_type": lemma.pos_type,
        "pos_subtype": lemma.pos_subtype or "",
        "concept_label": concept_label,
        "concept_definition": lemma.definition_text or "",
        "translations": translations,
        "difficulty_level": lemma.difficulty_level if lemma.difficulty_level is not None else -1,
    }

    if translation_disambiguations:
        entry["translation_disambiguations"] = translation_disambiguations
    if translation_metadata:
        entry["translation_metadata"] = translation_metadata

    if lemma.lexical_gap_reason:
        entry["lexical_gap_reason"] = lemma.lexical_gap_reason

    # If this lemma is paired with a concept that has a Wikidata Q-id, emit the
    # Q-id (e.g. "Apple" -> Q89). The concept itself is never exported; this is
    # the only piece of concept data that flows into data/release.
    session = object_session(lemma)
    if session is not None:
        qid = get_qid_for_lemma(session, lemma.id)
        if qid:
            entry["qid"] = qid

    return entry


def _get_release_file_path_for_lemma(release_dir: Path, lemma: Lemma) -> Optional[Path]:
    """Return the base.jsonl path for a lemma based on pos_type/pos_subtype."""
    if not lemma.pos_type or not lemma.pos_subtype:
        return None
    # Map pos_type to plural directory name (e.g. "noun" -> "nouns")
    pos_dir_map = {
        "noun": "nouns",
        "verb": "verbs",
        "adjective": "adjectives",
        "adverb": "adverbs",
        "conjunction": "conjunctions",
        "pronoun": "pronouns",
        "preposition": "prepositions",
        "interjection": "interjections",
        "determiner": "determiners",
        "article": "articles",
        "numeral": "numerals",
        "misc": "misc",
    }
    pos_dir = pos_dir_map.get(lemma.pos_type)
    if not pos_dir:
        return None
    return release_dir / pos_dir / str(lemma.pos_subtype) / "base.jsonl"


@bp.route("/removals/export", methods=["POST"])
def export_removals_to_release() -> ResponseReturnValue:
    """Export selected SQLite-only lemmas to data/release base.jsonl files.

    This is the direction the sync system is actually used in day to day, so it
    honours "export all" as well as a hand-picked selection.
    """
    release_dir = _get_release_dir()

    if request.form.get("select_scope") == "all":
        release_lemmas = _load_release_lemmas(release_dir)
        selected_ids = [str(item["lemma_id"]) for item in _find_removals(release_lemmas, g.db)]
    else:
        selected_ids = request.form.getlist("selected_ids")

    if not selected_ids:
        flash("No lemmas selected for export", "warning")
        return redirect(url_for("sync_release.removals"))

    outcome = SyncOutcome(noun="lemma")
    # Group by target file so each base.jsonl is rewritten once rather than
    # once per exported lemma.
    entries_by_file: Dict[Path, List[Dict[str, Any]]] = {}

    for lemma_id_str in selected_ids:
        try:
            lemma = g.db.query(Lemma).filter(Lemma.id == int(lemma_id_str)).first()
            if not lemma:
                outcome.record_error(f"Lemma not found: {lemma_id_str}")
                continue
            if not lemma.guid:
                outcome.record_error(f"Lemma {lemma_id_str} has no GUID, skipping export")
                continue

            file_path = _get_release_file_path_for_lemma(release_dir, lemma)
            if file_path is None:
                outcome.record_error(
                    f"Cannot determine release file for lemma {lemma.guid} "
                    f"(pos_type={lemma.pos_type}, pos_subtype={lemma.pos_subtype})"
                )
                continue

            entries_by_file.setdefault(file_path, []).append(_build_release_entry_from_db(lemma))

            log_operation(
                session=g.db,
                source="sync-release",
                operation_type="lemma_export",
                lemma_id=lemma.id,
                details={
                    "lemma_text": lemma.lemma_text,
                    "guid": lemma.guid,
                    "pos_type": lemma.pos_type,
                    "release_file": str(file_path.relative_to(release_dir.parent.parent)),
                },
            )
            outcome.exported += 1
            logger.info(f"Exporting lemma '{lemma.lemma_text}' ({lemma.guid}) to {file_path}")

        except Exception as e:
            outcome.record_error(f"Error exporting lemma {lemma_id_str}: {e}")

    try:
        for file_path, entries in entries_by_file.items():
            release_io.upsert_records(file_path, entries)
    except Exception as e:  # noqa: BLE001 - surfaced to the user
        logger.error(f"Release file write error: {e}")
        flash(f"Error writing release files: {e}", "error")
        outcome.exported = 0
        outcome.errors += 1
    else:
        if outcome.exported:
            g.db.commit()

    outcome.flash_summary()
    return redirect(url_for("sync_release.removals"))


# =============================================================================
# Changes (lemma_text differs between release and SQLite)
# =============================================================================


def _find_lemma_text_changes(
    release_lemmas: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find lemmas where any base-concept field differs between release and SQLite.

    Covers fields that live directly on the Lemma row (and the base.jsonl
    record): lemma_text (translations.en), disambiguation (parsed from
    concept_label), concept_definition (DB definition_text), notes,
    lexical_gap_reason, and emoji (JSON-encoded list on the DB side, native
    list in JSONL).
    """
    changes: List[Dict[str, Any]] = []
    release_guids = set(release_lemmas.keys())

    if not release_guids:
        return changes

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch_guids)).all()

        for db_lemma in db_lemmas:
            release_data = release_lemmas.get(db_lemma.guid)
            if not release_data:
                continue

            release_lemma_text = _get_release_lemma_text(release_data)
            release_disambig = _get_release_disambiguation(release_data)
            release_definition = release_data.get("concept_definition", "") or ""
            release_notes = release_data.get("notes")
            release_lexical_gap_reason = release_data.get("lexical_gap_reason")
            release_emoji = _get_release_emoji(release_data)
            release_qid = normalize_qid(release_data.get("qid") or "") or None

            db_definition = db_lemma.definition_text or ""
            db_notes = db_lemma.notes
            db_lexical_gap_reason = db_lemma.lexical_gap_reason
            db_emoji = _decode_db_emoji(db_lemma.emoji)
            db_qid = get_qid_for_lemma(db_session, db_lemma.id)

            text_differs = db_lemma.lemma_text != release_lemma_text
            disambig_differs = db_lemma.disambiguation != release_disambig
            definition_differs = db_definition != release_definition
            notes_differs = (db_notes or None) != (release_notes or None)
            lexical_gap_reason_differs = (db_lexical_gap_reason or None) != (
                release_lexical_gap_reason or None
            )
            emoji_differs = db_emoji != release_emoji
            qid_differs = db_qid != release_qid

            if not (
                text_differs
                or disambig_differs
                or definition_differs
                or notes_differs
                or lexical_gap_reason_differs
                or emoji_differs
                or qid_differs
            ):
                continue

            changes.append(
                {
                    "guid": db_lemma.guid,
                    "lemma_id": db_lemma.id,
                    "db_lemma_text": db_lemma.lemma_text,
                    "release_lemma_text": release_lemma_text,
                    "db_disambiguation": db_lemma.disambiguation,
                    "release_disambiguation": release_disambig,
                    "db_definition": db_definition,
                    "release_definition": release_definition,
                    "db_notes": db_notes or "",
                    "release_notes": release_notes or "",
                    "db_lexical_gap_reason": db_lexical_gap_reason or "",
                    "release_lexical_gap_reason": release_lexical_gap_reason or "",
                    "db_emoji": _format_emoji_for_display(db_emoji),
                    "release_emoji": _format_emoji_for_display(release_emoji),
                    "db_qid": db_qid or "",
                    "release_qid": release_qid or "",
                    "text_differs": text_differs,
                    "disambig_differs": disambig_differs,
                    "definition_differs": definition_differs,
                    "notes_differs": notes_differs,
                    "lexical_gap_reason_differs": lexical_gap_reason_differs,
                    "emoji_differs": emoji_differs,
                    "qid_differs": qid_differs,
                    "pos_type": db_lemma.pos_type,
                    "pos_subtype": db_lemma.pos_subtype,
                }
            )

    changes.sort(key=lambda x: x["guid"])
    return changes


@bp.route("/changes")
def changes() -> ResponseReturnValue:
    """Display lemmas where lemma_text differs between release and SQLite."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_release.index"))

    release_lemmas = _load_release_lemmas(release_dir)
    if not release_lemmas:
        flash("No lemmas found in release directory", "warning")
        return redirect(url_for("sync_release.index"))

    changes_list = _find_lemma_text_changes(release_lemmas, g.db)

    return render_template(
        "sync_release/changes.html",
        page=paginate(changes_list),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
    )


@bp.route("/changes/apply", methods=["POST"])
def apply_changes() -> ResponseReturnValue:
    """Apply selected lemma_text changes."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_release.changes"))

    release_dir = _get_release_dir()
    release_lemmas = _load_release_lemmas(release_dir)

    bulk = parse_bulk_request()
    if bulk is not None:
        all_changes = _find_lemma_text_changes(release_lemmas, g.db)
        expanded = bulk_actions_for(
            bulk, (item["lemma_id"] for item in all_changes), total=len(all_changes)
        )
        if expanded is None:
            return redirect(url_for("sync_release.changes"))
        actions = expanded
    else:
        actions = parse_row_actions()

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_release.changes"))

    outcome = SyncOutcome(noun="lemma")
    guid_files = release_io.build_guid_file_index(release_dir)
    release_updates: Dict[Path, Dict[str, Dict[str, Any]]] = {}

    for lemma_id_str, action in actions.items():
        if action == SKIP:
            outcome.skipped += 1
            continue
        if action not in (USE_RELEASE, USE_DB):
            continue

        try:
            lemma = g.db.query(Lemma).filter(Lemma.id == int(lemma_id_str)).first()
            if not lemma:
                outcome.record_error(f"Lemma not found: {lemma_id_str}")
                continue

            release_data = release_lemmas.get(lemma.guid)
            if not release_data:
                outcome.record_error(f"Release data not found for GUID: {lemma.guid}")
                continue

            if action == USE_RELEASE:
                old_text = lemma.lemma_text
                new_text = _get_release_lemma_text(release_data)
                new_definition = release_data.get("concept_definition", "") or ""
                new_notes = release_data.get("notes") or None
                new_lexical_gap_reason = release_data.get("lexical_gap_reason") or None
                new_emoji_list = _get_release_emoji(release_data)
                new_emoji_json = json.dumps(new_emoji_list) if new_emoji_list else None

                lemma.lemma_text = new_text
                lemma.disambiguation = _get_release_disambiguation(release_data)
                lemma.definition_text = new_definition
                lemma.notes = new_notes
                lemma.lexical_gap_reason = new_lexical_gap_reason
                lemma.emoji = new_emoji_json

                # Concept pairing: the release file carries only the Q-id. Pair
                # (or repair) when present, unlink when absent. The pairing lives
                # in concept_lemma_links and is committed by link/unlink itself.
                new_qid = normalize_qid(release_data.get("qid") or "") or None
                if new_qid:
                    link_lemma_to_concept(g.db, lemma.id, new_qid, verified=True)
                else:
                    unlink_lemma_from_concept(g.db, lemma_id=lemma.id)

                log_translation_change(
                    session=g.db,
                    source="sync-release",
                    operation_type="lemma_text_sync",
                    lemma_id=lemma.id,
                    field_name="lemma_text",
                    old_value=old_text,
                    new_value=new_text,
                )

                outcome.updated_db += 1
                logger.info(f"Updated base info for ({lemma.guid}): '{old_text}' -> '{new_text}'")

            else:  # USE_DB
                file_path = release_io.file_for_guid(guid_files, lemma.guid)
                if file_path is None:
                    outcome.record_error(f"Could not find release file for GUID: {lemma.guid}")
                    continue

                db_text = lemma.lemma_text
                update_fields: Dict[str, Any] = {
                    # English lives in the release record as translations.en.
                    "translations.en": db_text,
                    "concept_definition": lemma.definition_text or "",
                }
                if lemma.notes:
                    update_fields["notes"] = lemma.notes
                if lemma.lexical_gap_reason:
                    update_fields["lexical_gap_reason"] = lemma.lexical_gap_reason
                db_emoji_list = _decode_db_emoji(lemma.emoji)
                if db_emoji_list:
                    update_fields["emoji"] = db_emoji_list
                # Concept pairing: write the DB's Q-id, or remove the field when
                # the lemma is unpaired so a stale qid doesn't linger in release.
                db_qid = get_qid_for_lemma(g.db, lemma.id)
                update_fields["qid"] = db_qid if db_qid else release_io.REMOVE_FIELD

                release_updates.setdefault(file_path, {})[lemma.guid] = update_fields
                outcome.updated_release += 1
                logger.info(f"Queued release update for ({lemma.guid}) lemma_text: -> '{db_text}'")

        except Exception as e:
            outcome.record_error(f"Error updating lemma {lemma_id_str}: {e}")

    outcome.commit(g.db)
    _write_release_updates(release_updates, outcome)
    outcome.flash_summary()
    return redirect(url_for("sync_release.changes"))


# =============================================================================
# Translations (translation differences between release and SQLite)
# =============================================================================


def _find_translation_differences(
    release_lemmas: Dict[str, Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Find lemmas where translations differ between release and SQLite.

    Only considers lemmas where GUID exists in both and lemma_text matches.
    Returns differences where either:
    - Release has a translation that DB doesn't have (or is different)
    - DB has a translation that release doesn't have (or is different)
    """
    differences: List[Dict[str, Any]] = []
    release_guids = set(release_lemmas.keys())

    if not release_guids:
        return differences

    # Languages to check (excluding 'en' which is stored as lemma_text)
    lang_codes_to_check = [lang for lang in RELEASE_LANGUAGES if lang != "en"]

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch_guids)).all()

        # Build lemma_id -> lemma mapping
        lemma_by_id = {lemma.id: lemma for lemma in db_lemmas}
        lemma_ids = list(lemma_by_id.keys())

        # Batch fetch all translations for these lemmas
        db_translations: Dict[int, Dict[str, str]] = {lid: {} for lid in lemma_ids}
        if lemma_ids:
            trans_rows = (
                db_session.query(LemmaTranslation)
                .filter(LemmaTranslation.lemma_id.in_(lemma_ids))
                .all()
            )
            for tr in trans_rows:
                if tr.translation:
                    db_translations[tr.lemma_id][tr.language_code] = tr.translation

        for db_lemma in db_lemmas:
            release_data = release_lemmas.get(db_lemma.guid)
            if not release_data:
                continue

            release_lemma_text = _get_release_lemma_text(release_data)

            # Only check translations for lemmas with matching text
            if db_lemma.lemma_text != release_lemma_text:
                continue

            release_translations = release_data.get("translations", {})
            db_trans = db_translations.get(db_lemma.id, {})

            # Find differences for each language
            lang_diffs: List[Dict[str, Any]] = []
            for lang_code in lang_codes_to_check:
                release_val = release_translations.get(lang_code, "")
                db_val = db_trans.get(lang_code, "")

                # Normalize empty values
                release_val = release_val.strip() if release_val else ""
                db_val = db_val.strip() if db_val else ""

                if release_val != db_val:
                    lang_diffs.append(
                        {
                            "lang_code": lang_code,
                            "lang_name": LANGUAGE_NAMES.get(lang_code, lang_code),
                            "release_val": release_val,
                            "db_val": db_val,
                        }
                    )

            if lang_diffs:
                differences.append(
                    {
                        "guid": db_lemma.guid,
                        "lemma_id": db_lemma.id,
                        "lemma_text": db_lemma.lemma_text,
                        "definition": (
                            db_lemma.definition_text[:60] if db_lemma.definition_text else ""
                        ),
                        "pos_type": db_lemma.pos_type,
                        "pos_subtype": db_lemma.pos_subtype,
                        "lang_diffs": lang_diffs,
                        "diff_count": len(lang_diffs),
                    }
                )

    differences.sort(key=lambda x: x["guid"])
    return differences


def _count_translation_differences(
    release_lemmas: Dict[str, Dict[str, Any]], db_session: Any
) -> int:
    """Count lemmas with translation differences (faster than full diff scan)."""
    count = 0
    release_guids = set(release_lemmas.keys())

    if not release_guids:
        return count

    # Languages to check (excluding 'en')
    lang_codes_to_check = [lang for lang in RELEASE_LANGUAGES if lang != "en"]

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch_guids)).all()

        lemma_by_id = {lemma.id: lemma for lemma in db_lemmas}
        lemma_ids = list(lemma_by_id.keys())

        # Batch fetch translations
        db_translations: Dict[int, Dict[str, str]] = {lid: {} for lid in lemma_ids}
        if lemma_ids:
            trans_rows = (
                db_session.query(LemmaTranslation)
                .filter(LemmaTranslation.lemma_id.in_(lemma_ids))
                .all()
            )
            for tr in trans_rows:
                if tr.translation:
                    db_translations[tr.lemma_id][tr.language_code] = tr.translation

        for db_lemma in db_lemmas:
            release_data = release_lemmas.get(db_lemma.guid)
            if not release_data:
                continue

            release_lemma_text = _get_release_lemma_text(release_data)
            if db_lemma.lemma_text != release_lemma_text:
                continue

            release_translations = release_data.get("translations", {})
            db_trans = db_translations.get(db_lemma.id, {})

            for lang_code in lang_codes_to_check:
                release_val = (release_translations.get(lang_code, "") or "").strip()
                db_val = (db_trans.get(lang_code, "") or "").strip()

                if release_val != db_val:
                    count += 1
                    break  # Just need to know this lemma has differences

    return count


@bp.route("/translations")
def translations() -> ResponseReturnValue:
    """Display translation differences between release and SQLite."""
    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_release.index"))

    release_lemmas = _load_release_lemmas(release_dir)
    if not release_lemmas:
        flash("No lemmas found in release directory", "warning")
        return redirect(url_for("sync_release.index"))

    differences = _find_translation_differences(release_lemmas, g.db)

    return render_template(
        "sync_release/translations.html",
        page=paginate(differences),
        per_page_choices=PER_PAGE_CHOICES,
        release_dir=str(release_dir),
        language_names=LANGUAGE_NAMES,
    )


def _bulk_language_actions(
    differences: List[Dict[str, Any]], action: str
) -> Dict[str, Dict[str, str]]:
    """Expand a bulk choice across every differing (lemma, language) pair."""
    return {
        str(diff["lemma_id"]): {
            str(lang_diff["lang_code"]): action for lang_diff in diff["lang_diffs"]
        }
        for diff in differences
    }


@bp.route("/translations/apply", methods=["POST"])
def apply_translations() -> ResponseReturnValue:
    """Apply selected translation changes."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_release.translations"))

    release_dir = _get_release_dir()
    release_lemmas = _load_release_lemmas(release_dir)

    bulk = parse_bulk_request()
    if bulk is not None:
        differences = _find_translation_differences(release_lemmas, g.db)
        if bulk_actions_for(bulk, (), total=len(differences)) is None:
            return redirect(url_for("sync_release.translations"))
        actions = _bulk_language_actions(differences, bulk.action)
    else:
        actions = parse_language_actions()

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_release.translations"))

    outcome = SyncOutcome(noun="translation")
    guid_files = release_io.build_guid_file_index(release_dir)
    release_updates: Dict[Path, Dict[str, Dict[str, str]]] = {}

    for lemma_id_str, lang_actions in actions.items():
        try:
            lemma = g.db.query(Lemma).filter(Lemma.id == int(lemma_id_str)).first()
            if not lemma:
                outcome.record_error(f"Lemma not found: {lemma_id_str}")
                continue

            release_data = release_lemmas.get(lemma.guid)
            if not release_data:
                outcome.record_error(f"Release data not found for GUID: {lemma.guid}")
                continue

            release_translations = release_data.get("translations", {})
            release_disambiguations = release_data.get("translation_disambiguations", {})
            release_metadata = release_data.get("translation_metadata", {})

            for lang_code, action in lang_actions.items():
                if action == SKIP:
                    outcome.skipped += 1
                    continue

                if action == USE_RELEASE:
                    # Copy from release to DB
                    release_val = release_translations.get(lang_code, "")
                    release_disambig = release_disambiguations.get(lang_code)
                    release_lang_metadata = release_metadata.get(lang_code, {})
                    if release_val:
                        trans_obj = (
                            g.db.query(LemmaTranslation)
                            .filter(
                                LemmaTranslation.lemma_id == lemma.id,
                                LemmaTranslation.language_code == lang_code,
                            )
                            .first()
                        )

                        if trans_obj:
                            old_val = trans_obj.translation
                            trans_obj.translation = release_val
                            trans_obj.disambiguation = release_disambig
                            trans_obj.translation_status = release_lang_metadata.get(
                                "translation_status"
                            )
                            trans_obj.translation_status_note = release_lang_metadata.get(
                                "translation_status_note"
                            )
                            trans_obj.sort_key = compute_sort_key(lang_code, release_val)
                        else:
                            trans_obj = LemmaTranslation(
                                lemma_id=lemma.id,
                                language_code=lang_code,
                                translation=release_val,
                                disambiguation=release_disambig,
                                translation_status=release_lang_metadata.get("translation_status"),
                                translation_status_note=release_lang_metadata.get(
                                    "translation_status_note"
                                ),
                                sort_key=compute_sort_key(lang_code, release_val),
                                verified=False,
                            )
                            g.db.add(trans_obj)
                            old_val = None

                        log_translation_change(
                            session=g.db,
                            source="sync-release",
                            operation_type="translation_sync",
                            lemma_id=lemma.id,
                            language_code=lang_code,
                            old_translation=old_val,
                            new_translation=release_val,
                        )

                        # Invalidate audio that was generated for the old translation
                        invalidate_audio_for_translation_change(
                            g.db, lemma.guid, lang_code, old_val, release_val
                        )

                        outcome.updated_db += 1
                        logger.info(
                            f"Updated DB translation for '{lemma.lemma_text}' "
                            f"({lemma.guid}) {lang_code}: '{old_val}' -> '{release_val}'"
                        )
                    else:
                        outcome.skipped += 1

                elif action == USE_DB:
                    # Mark for release file update (DB value -> release)
                    trans_obj = (
                        g.db.query(LemmaTranslation)
                        .filter(
                            LemmaTranslation.lemma_id == lemma.id,
                            LemmaTranslation.language_code == lang_code,
                        )
                        .first()
                    )

                    db_val = trans_obj.translation if trans_obj else ""
                    db_disambig = trans_obj.disambiguation if trans_obj else None
                    if not db_val:
                        outcome.skipped += 1
                        continue

                    file_path = release_io.file_for_guid(guid_files, lemma.guid)
                    if file_path is None:
                        outcome.record_error(f"Could not find release file for GUID: {lemma.guid}")
                        continue

                    guid_updates = release_updates.setdefault(file_path, {}).setdefault(
                        lemma.guid, {}
                    )
                    guid_updates[lang_code] = db_val
                    if db_disambig:
                        guid_updates[f"{_DISAMBIG_PREFIX}{lang_code}"] = db_disambig
                    outcome.updated_release += 1
                    logger.info(
                        f"Queued release update for '{lemma.lemma_text}' "
                        f"({lemma.guid}) {lang_code}: -> '{db_val}'"
                    )

        except Exception as e:
            outcome.record_error(f"Error processing lemma {lemma_id_str}: {e}")

    outcome.commit(g.db)
    if release_updates:
        try:
            _apply_release_translation_updates(release_updates)
        except Exception as e:  # noqa: BLE001 - surfaced to the user
            logger.error(f"Release file update error: {e}")
            flash(f"Error updating release files: {e}", "error")
            outcome.updated_release = 0
            outcome.errors += 1
    outcome.flash_summary()

    return redirect(url_for("sync_release.translations"))


# =============================================================================
# Secondary Translations (secondary.jsonl — Tier 3 languages)
# =============================================================================


def _find_secondary_translation_differences(
    release_lemmas: Dict[str, Dict[str, Any]],
    secondary_translations: Dict[str, Dict[str, str]],
    db_session: Any,
) -> List[Dict[str, Any]]:
    """Find lemmas where secondary translations differ between release and SQLite.

    Only considers lemmas where GUID exists in both release and DB
    and lemma_text matches.
    """
    return _find_secondary_translation_differences_filtered(
        release_lemmas, secondary_translations, db_session, SECONDARY_RELEASE_LANGUAGES
    )


def _find_secondary_translation_differences_filtered(
    release_lemmas: Dict[str, Dict[str, Any]],
    secondary_translations: Dict[str, Dict[str, str]],
    db_session: Any,
    lang_codes_to_check: List[str],
) -> List[Dict[str, Any]]:
    """Find lemmas where secondary translations differ, checking only specified languages.

    Args:
        release_lemmas: Dictionary of release lemma data by GUID
        secondary_translations: Dictionary of secondary translations by GUID
        db_session: Database session
        lang_codes_to_check: List of language codes to check for differences

    Returns:
        List of differences found
    """
    differences: List[Dict[str, Any]] = []

    if not lang_codes_to_check:
        return differences

    # We compare for all GUIDs in the base release (the canonical set)
    release_guids = set(release_lemmas.keys())
    if not release_guids:
        return differences

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch_guids)).all()

        lemma_by_id = {lemma.id: lemma for lemma in db_lemmas}
        lemma_ids = list(lemma_by_id.keys())

        # Batch fetch all translations for these lemmas
        db_translations: Dict[int, Dict[str, str]] = {lid: {} for lid in lemma_ids}
        if lemma_ids:
            trans_rows = (
                db_session.query(LemmaTranslation)
                .filter(LemmaTranslation.lemma_id.in_(lemma_ids))
                .all()
            )
            for tr in trans_rows:
                if tr.translation:
                    db_translations[tr.lemma_id][tr.language_code] = tr.translation

        for db_lemma in db_lemmas:
            release_data = release_lemmas.get(db_lemma.guid)
            if not release_data:
                continue

            release_lemma_text = _get_release_lemma_text(release_data)
            if db_lemma.lemma_text != release_lemma_text:
                continue

            sec_trans = secondary_translations.get(db_lemma.guid, {})
            db_trans = db_translations.get(db_lemma.id, {})

            lang_diffs: List[Dict[str, Any]] = []
            for lang_code in lang_codes_to_check:
                release_val = (sec_trans.get(lang_code, "") or "").strip()
                db_val = (db_trans.get(lang_code, "") or "").strip()

                if release_val != db_val:
                    lang_diffs.append(
                        {
                            "lang_code": lang_code,
                            "lang_name": LANGUAGE_NAMES.get(lang_code, lang_code),
                            "release_val": release_val,
                            "db_val": db_val,
                        }
                    )

            if lang_diffs:
                differences.append(
                    {
                        "guid": db_lemma.guid,
                        "lemma_id": db_lemma.id,
                        "lemma_text": db_lemma.lemma_text,
                        "definition": (
                            db_lemma.definition_text[:60] if db_lemma.definition_text else ""
                        ),
                        "pos_type": db_lemma.pos_type,
                        "pos_subtype": db_lemma.pos_subtype,
                        "lang_diffs": lang_diffs,
                        "diff_count": len(lang_diffs),
                    }
                )

    differences.sort(key=lambda x: x["guid"])
    return differences


def _count_secondary_translation_differences(
    release_lemmas: Dict[str, Dict[str, Any]],
    secondary_translations: Dict[str, Dict[str, str]],
    db_session: Any,
) -> int:
    """Count lemmas with secondary translation differences."""
    return _count_secondary_translation_differences_filtered(
        release_lemmas, secondary_translations, db_session, SECONDARY_RELEASE_LANGUAGES
    )


def _count_secondary_translation_differences_filtered(
    release_lemmas: Dict[str, Dict[str, Any]],
    secondary_translations: Dict[str, Dict[str, str]],
    db_session: Any,
    lang_codes_to_check: List[str],
) -> int:
    """Count lemmas with secondary translation differences for specified languages."""
    count = 0

    if not lang_codes_to_check:
        return count

    release_guids = set(release_lemmas.keys())
    if not release_guids:
        return count

    batch_size = 500
    guid_list = list(release_guids)

    for i in range(0, len(guid_list), batch_size):
        batch_guids = guid_list[i : i + batch_size]
        db_lemmas = db_session.query(Lemma).filter(Lemma.guid.in_(batch_guids)).all()

        lemma_by_id = {lemma.id: lemma for lemma in db_lemmas}
        lemma_ids = list(lemma_by_id.keys())

        db_translations: Dict[int, Dict[str, str]] = {lid: {} for lid in lemma_ids}
        if lemma_ids:
            trans_rows = (
                db_session.query(LemmaTranslation)
                .filter(LemmaTranslation.lemma_id.in_(lemma_ids))
                .all()
            )
            for tr in trans_rows:
                if tr.translation:
                    db_translations[tr.lemma_id][tr.language_code] = tr.translation

        for db_lemma in db_lemmas:
            release_data = release_lemmas.get(db_lemma.guid)
            if not release_data:
                continue

            release_lemma_text = _get_release_lemma_text(release_data)
            if db_lemma.lemma_text != release_lemma_text:
                continue

            sec_trans = secondary_translations.get(db_lemma.guid, {})
            db_trans = db_translations.get(db_lemma.id, {})

            for lang_code in lang_codes_to_check:
                release_val = (sec_trans.get(lang_code, "") or "").strip()
                db_val = (db_trans.get(lang_code, "") or "").strip()

                if release_val != db_val:
                    count += 1
                    break  # Just need to know this lemma has differences

    return count


@bp.route("/secondary-translations")
def secondary_translations() -> ResponseReturnValue:
    """Display language selection page for secondary translations."""
    return render_template(
        "sync_release/secondary_translations_select.html",
        secondary_languages=SECONDARY_RELEASE_LANGUAGES,
        language_names=LANGUAGE_NAMES,
    )


@bp.route("/secondary-translations/view")
def secondary_translations_view() -> ResponseReturnValue:
    """Display secondary translation differences for selected languages."""
    # Get selected languages from query params
    selected_langs = request.args.getlist("lang")

    if not selected_langs:
        flash("No languages selected", "warning")
        return redirect(url_for("sync_release.secondary_translations"))

    release_dir = _get_release_dir()

    if not release_dir.exists():
        flash(f"Release directory not found: {release_dir}", "error")
        return redirect(url_for("sync_release.index"))

    release_lemmas = _load_release_lemmas(release_dir)
    if not release_lemmas:
        flash("No lemmas found in release directory", "warning")
        return redirect(url_for("sync_release.index"))

    sec_translations = _load_secondary_translations(release_dir)

    # Filter differences to only include selected languages
    differences = _find_secondary_translation_differences_filtered(
        release_lemmas, sec_translations, g.db, selected_langs
    )

    return render_template(
        "sync_release/secondary_translations_detail.html",
        page=paginate(differences),
        per_page_choices=PER_PAGE_CHOICES,
        # The language filter has to survive the pager links, so it is carried
        # through page_args rather than rebuilt in the template.
        list_args=page_args(),
        release_dir=str(release_dir),
        language_names=LANGUAGE_NAMES,
        selected_languages=selected_langs,
    )


@bp.route("/secondary-translations/apply", methods=["POST"])
def apply_secondary_translations() -> ResponseReturnValue:
    """Apply selected secondary translation changes."""
    if is_readonly():
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_release.secondary_translations"))

    release_dir = _get_release_dir()
    sec_translations = _load_secondary_translations(release_dir)

    bulk = parse_bulk_request()
    if bulk is not None:
        # The bulk button carries the language filter the page was viewed with,
        # so "apply to all" stays scoped to the languages on screen.
        selected_langs = request.form.getlist("lang")
        release_lemmas = _load_release_lemmas(release_dir)
        differences = _find_secondary_translation_differences_filtered(
            release_lemmas, sec_translations, g.db, selected_langs
        )
        if bulk_actions_for(bulk, (), total=len(differences)) is None:
            return redirect(url_for("sync_release.secondary_translations"))
        actions = _bulk_language_actions(differences, bulk.action)
    else:
        actions = parse_language_actions()

    if not actions:
        flash("No changes selected", "warning")
        return redirect(url_for("sync_release.secondary_translations"))

    outcome = SyncOutcome(noun="secondary translation")
    guid_files = release_io.build_guid_file_index(release_dir)
    # Release updates are keyed by directory: a GUID may not be in
    # secondary.jsonl yet, so the target is the category dir, not a known file.
    release_updates: Dict[Path, Dict[str, Dict[str, str]]] = {}

    for lemma_id_str, lang_actions in actions.items():
        try:
            lemma = g.db.query(Lemma).filter(Lemma.id == int(lemma_id_str)).first()
            if not lemma:
                outcome.record_error(f"Lemma not found: {lemma_id_str}")
                continue

            guid_sec_trans = sec_translations.get(lemma.guid, {})

            for lang_code, action in lang_actions.items():
                if action == SKIP:
                    outcome.skipped += 1
                    continue

                if action == USE_RELEASE:
                    release_val = guid_sec_trans.get(lang_code, "")
                    if release_val:
                        trans_obj = (
                            g.db.query(LemmaTranslation)
                            .filter(
                                LemmaTranslation.lemma_id == lemma.id,
                                LemmaTranslation.language_code == lang_code,
                            )
                            .first()
                        )

                        if trans_obj:
                            old_val = trans_obj.translation
                            trans_obj.translation = release_val
                            trans_obj.sort_key = compute_sort_key(lang_code, release_val)
                        else:
                            trans_obj = LemmaTranslation(
                                lemma_id=lemma.id,
                                language_code=lang_code,
                                translation=release_val,
                                sort_key=compute_sort_key(lang_code, release_val),
                                verified=False,
                            )
                            g.db.add(trans_obj)
                            old_val = None

                        log_translation_change(
                            session=g.db,
                            source="sync-release-secondary",
                            operation_type="translation_sync",
                            lemma_id=lemma.id,
                            language_code=lang_code,
                            old_translation=old_val,
                            new_translation=release_val,
                        )

                        invalidate_audio_for_translation_change(
                            g.db, lemma.guid, lang_code, old_val, release_val
                        )

                        outcome.updated_db += 1
                        logger.info(
                            f"Updated DB secondary translation for "
                            f"'{lemma.lemma_text}' ({lemma.guid}) "
                            f"{lang_code}: '{old_val}' -> '{release_val}'"
                        )
                    else:
                        outcome.skipped += 1

                elif action == USE_DB:
                    trans_obj = (
                        g.db.query(LemmaTranslation)
                        .filter(
                            LemmaTranslation.lemma_id == lemma.id,
                            LemmaTranslation.language_code == lang_code,
                        )
                        .first()
                    )

                    db_val = trans_obj.translation if trans_obj else ""
                    if not db_val:
                        outcome.skipped += 1
                        continue

                    # base.jsonl locates the category directory; the GUID may not
                    # be in secondary.jsonl yet, so we cannot look it up there.
                    base_file = release_io.file_for_guid(guid_files, lemma.guid)
                    if base_file is None:
                        outcome.record_error(f"Could not find release dir for GUID: {lemma.guid}")
                        continue

                    release_updates.setdefault(base_file.parent, {}).setdefault(lemma.guid, {})[
                        lang_code
                    ] = db_val
                    outcome.updated_release += 1
                    logger.info(
                        f"Queued secondary release update for "
                        f"'{lemma.lemma_text}' ({lemma.guid}) {lang_code}: -> '{db_val}'"
                    )

        except Exception as e:
            outcome.record_error(f"Error processing lemma {lemma_id_str}: {e}")

    outcome.commit(g.db)
    if release_updates:
        try:
            _apply_secondary_translation_updates(release_updates)
        except Exception as e:  # noqa: BLE001 - surfaced to the user
            logger.error(f"Release file update error: {e}")
            flash(f"Error updating release files: {e}", "error")
            outcome.updated_release = 0
            outcome.errors += 1
    outcome.flash_summary()
    return redirect(url_for("sync_release.secondary_translations"))


def _apply_release_translation_updates(
    updates: Dict[Path, Dict[str, Dict[str, str]]],
) -> None:
    """Apply translation updates to release base.jsonl files.

    Keys prefixed ``_disambig_`` carry a per-language disambiguation rather than
    a translation; see :func:`release_io.apply_translation_updates`.
    """
    release_io.apply_translation_updates(updates, disambiguation_prefix=_DISAMBIG_PREFIX)


def _extra_translation_filenames() -> List[str]:
    """Return all grouped extra-translation filenames (secondary + named groups)."""
    return ["secondary.jsonl"] + [
        f"{group_name}.jsonl" for group_name in EXTRA_RELEASE_LANGUAGE_GROUPS
    ]


def _load_secondary_translations(
    release_dir: Path,
) -> Dict[str, Dict[str, str]]:
    """Load extra translations from data/release secondary/group JSONL files.

    Returns:
        Dictionary mapping GUID to {lang_code: translation} for extra languages.
        A GUID may appear in several group files; their languages are merged.
    """
    secondary: Dict[str, Dict[str, str]] = {}
    for extra_filename in _extra_translation_filenames():
        for guid, record in release_io.load_release_records(release_dir, extra_filename).items():
            translations = record.get("translations") or {}
            if translations:
                secondary.setdefault(guid, {}).update(translations)
    return secondary


def _apply_secondary_translation_updates(
    updates: Dict[Path, Dict[str, Dict[str, str]]],
) -> None:
    """Apply translation updates to secondary.jsonl files.

    Keyed by *directory* rather than file: a GUID that has no secondary
    translations yet has no line in secondary.jsonl to find, so the target is
    resolved from the category directory and the record is created.

    Args:
        updates: {directory_path: {guid: {lang_code: new_translation}}}
    """
    for dir_path, guid_updates in updates.items():
        secondary_file = dir_path / "secondary.jsonl"
        existing = release_io.load_records_from_file(secondary_file)

        merged: List[Dict[str, Any]] = []
        for guid, record in existing.items():
            if guid in guid_updates:
                record.setdefault("translations", {})
                for lang_code, new_value in guid_updates[guid].items():
                    if new_value:
                        record["translations"][lang_code] = new_value
                    else:
                        record["translations"].pop(lang_code, None)
            merged.append(record)

        for guid, translations in guid_updates.items():
            if guid in existing:
                continue
            non_empty = {lang: text for lang, text in translations.items() if text}
            if non_empty:
                merged.append({"guid": guid, "translations": non_empty})

        release_io.write_jsonl_sorted(secondary_file, merged)
        logger.info(f"Updated {len(guid_updates)} record(s) in {secondary_file}")
