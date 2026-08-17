"""Shared helpers for derivative-form / synonym release sync routes.

The two sync pages (``/sync/derivatives`` and ``/sync/synonyms``) both read and
write per-language JSONL files of the shape::

    {"guid": "N02_001", "forms": [...], "synonyms": [...]}

Each route operates on exactly one of those top-level array keys; the other
must be preserved when rewriting a line. The helpers in this module factor
out that file I/O so the two routes can share it.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from storage.models.schema import Lemma

logger = logging.getLogger(__name__)


def db_form_to_dict(form: Any, *, include_base_form: bool) -> Dict[str, Any]:
    """Convert a DB ``DerivativeForm`` to its release-file dict shape.

    ``include_base_form`` is the one real difference between the two callers:
    an inflection records whether it is the base form, a synonym has no such
    notion.
    """
    record: Dict[str, Any] = {
        "grammatical_form": form.grammatical_form,
        "text": form.form_text,
    }
    if include_base_form:
        record["is_base_form"] = form.is_base_form
    if form.ipa_pronunciation:
        record["ipa"] = form.ipa_pronunciation
    if form.phonetic_pronunciation:
        record["phonetic"] = form.phonetic_pronunciation
    return record


def form_key(grammatical_form: str, text: str) -> str:
    """Comparison key identifying one form within a lemma+language."""
    return f"{grammatical_form}\x00{text}"


def languages_with_release_files(release_dir: Path) -> Set[str]:
    """Language codes that have per-language files under the release tree.

    Only 2-3 letter alphabetic stems count, which excludes ``base`` and the
    grouped translation files (``secondary``, ``ancient``) along with it.
    """
    languages: Set[str] = set()
    if not release_dir.exists():
        return languages

    for jsonl_file in release_dir.rglob("*.jsonl"):
        stem = jsonl_file.stem
        if stem != "base" and len(stem) in (2, 3) and stem.isalpha():
            languages.add(stem)
    return languages


def lemma_info_by_guids(db_session: Any, guids: Set[str]) -> Dict[str, Dict[str, Any]]:
    """Look up basic lemma display info for a set of GUIDs, in batches."""
    info: Dict[str, Dict[str, Any]] = {}
    guid_list = list(guids)
    for start in range(0, len(guid_list), 500):
        for lemma in (
            db_session.query(Lemma).filter(Lemma.guid.in_(guid_list[start : start + 500])).all()
        ):
            info[lemma.guid] = {
                "lemma_id": lemma.id,
                "lemma_text": lemma.lemma_text,
                "pos_type": lemma.pos_type,
                "pos_subtype": lemma.pos_subtype or "",
            }
    return info


def guid_to_lemma_id(db_session: Any) -> Dict[str, int]:
    """Map every GUIDed lemma's GUID to its row id."""
    return {
        guid: lemma_id
        for lemma_id, guid in db_session.query(Lemma.id, Lemma.guid)
        .filter(Lemma.guid.isnot(None))
        .all()
    }


def load_release_array_for_lang(
    release_dir: Path, lang_code: str, array_key: str
) -> Dict[str, List[Dict[str, Any]]]:
    """Load one of the top-level arrays (``forms`` or ``synonyms``) per GUID.

    Scans every ``{lang_code}.jsonl`` under the release directory.
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    if not release_dir.exists():
        return out

    filename = f"{lang_code}.jsonl"
    for lang_file in release_dir.rglob(filename):
        try:
            with open(lang_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parse error in {lang_file}:{line_num}: {e}")
                        continue
                    guid = data.get("guid")
                    arr = data.get(array_key, [])
                    if guid and arr:
                        out[guid] = arr
        except Exception as e:
            logger.error(f"Error reading {lang_file}: {e}")
    return out


def find_release_file_for_lemma_lang(
    release_dir: Path, guid: str, lang_code: str
) -> Optional[Path]:
    """Find the {lang}.jsonl file that contains (or should contain) ``guid``.

    First searches existing lang files; if not found, resolves the directory
    from the matching ``base.jsonl``.
    """
    filename = f"{lang_code}.jsonl"

    for lang_file in release_dir.rglob(filename):
        try:
            with open(lang_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("guid") == guid:
                            return lang_file
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

    for base_file in release_dir.rglob("base.jsonl"):
        try:
            with open(base_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("guid") == guid:
                            return base_file.parent / filename
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

    return None


def write_release_line_partial(
    file_path: Path, guid: str, array_key: str, value: List[Dict[str, Any]]
) -> None:
    """Write or update one top-level array key on a GUID's JSONL line.

    Only ``array_key`` is replaced; any other top-level keys present on an
    existing line (e.g. the *other* of ``forms`` / ``synonyms``) are preserved.
    If ``value`` is empty the key is dropped from the line; if no other keys
    remain besides ``guid`` the line is removed entirely.
    """
    existing: Optional[Dict[str, Any]] = None
    other_lines: List[str] = []

    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    other_lines.append(line)
                    continue
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError:
                    other_lines.append(line)
                    continue
                if data.get("guid") == guid:
                    existing = data
                else:
                    other_lines.append(line)

    record: Dict[str, Any] = existing or {"guid": guid}
    if value:
        record[array_key] = value
    else:
        record.pop(array_key, None)

    drop_record = len(record) <= 1  # only "guid" left

    if not drop_record:
        new_line = json.dumps(record, ensure_ascii=False) + "\n"
        merged = _insert_sorted(other_lines, guid, new_line)
    else:
        merged = other_lines

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(merged)

    logger.info(f"Wrote {array_key} for {guid} to {file_path}")


def _insert_sorted(lines: List[str], new_guid: str, new_line: str) -> List[str]:
    """Insert ``new_line`` into ``lines`` maintaining GUID sort order."""
    result: List[str] = []
    inserted = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        if not inserted:
            try:
                data = json.loads(stripped)
                existing_guid = data.get("guid", "")
                if existing_guid > new_guid:
                    result.append(new_line)
                    inserted = True
            except json.JSONDecodeError:
                pass
        result.append(line)
    if not inserted:
        result.append(new_line)
    return result
