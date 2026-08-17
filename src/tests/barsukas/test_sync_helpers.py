"""Tests for the shared /sync machinery: release-file I/O and pagination.

These back the pieces that every sync blueprint now routes through, so a
regression here would silently corrupt release files or drop rows from a
difference list rather than failing loudly in one page.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from flask import Flask

from barsukas.routes.sync import release_io, sync_release_helpers
from barsukas.routes.sync.paging import PER_PAGE_CHOICES, Page, page_args, paginate
from storage.models.schema import DerivativeForm


@pytest.fixture()
def app() -> Flask:
    """A bare Flask app, only needed for the request context paginate() reads."""
    return Flask(__name__)


def _write_jsonl(file_path: Path, records: List[Dict[str, Any]]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _read_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in file_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# --- Loading ---------------------------------------------------------------


def test_load_release_records_walks_the_whole_tree(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "nouns" / "food" / "base.jsonl", [{"guid": "N06_001"}])
    _write_jsonl(tmp_path / "verbs" / "change" / "base.jsonl", [{"guid": "V08_002"}])

    records = release_io.load_release_records(tmp_path)
    assert set(records) == {"N06_001", "V08_002"}


def test_load_release_records_skips_records_without_a_guid(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "base.jsonl", [{"guid": "N06_001"}, {"translations": {}}])
    assert set(release_io.load_release_records(tmp_path)) == {"N06_001"}


def test_a_malformed_line_does_not_hide_the_rest_of_the_file(tmp_path: Path) -> None:
    release_file = tmp_path / "base.jsonl"
    release_file.parent.mkdir(parents=True, exist_ok=True)
    release_file.write_text(
        '{"guid": "N06_001"}\nnot json at all\n{"guid": "N06_002"}\n', encoding="utf-8"
    )
    assert set(release_io.load_release_records(tmp_path)) == {"N06_001", "N06_002"}


def test_missing_directory_loads_as_empty(tmp_path: Path) -> None:
    assert release_io.load_release_records(tmp_path / "nope") == {}


def test_subtype_key_is_filled_in_from_the_directory(tmp_path: Path) -> None:
    """Phrases store their subtype as the directory name, not as a field."""
    _write_jsonl(tmp_path / "greetings" / "base.jsonl", [{"guid": "F01_001"}])
    _write_jsonl(
        tmp_path / "traveler" / "base.jsonl",
        [{"guid": "F02_001", "phrase_subtype": "explicit"}],
    )

    records = release_io.load_release_records(tmp_path, subtype_key="phrase_subtype")
    assert records["F01_001"]["phrase_subtype"] == "greetings"
    # An explicit value is not overwritten by the directory name.
    assert records["F02_001"]["phrase_subtype"] == "explicit"


# --- GUID -> file index ----------------------------------------------------


def test_guid_file_index_maps_every_guid_to_its_file(tmp_path: Path) -> None:
    food = tmp_path / "nouns" / "food" / "base.jsonl"
    verbs = tmp_path / "verbs" / "change" / "base.jsonl"
    _write_jsonl(food, [{"guid": "N06_001"}, {"guid": "N06_002"}])
    _write_jsonl(verbs, [{"guid": "V08_001"}])

    index = release_io.build_guid_file_index(tmp_path)
    assert release_io.file_for_guid(index, "N06_002") == food
    assert release_io.file_for_guid(index, "V08_001") == verbs
    assert release_io.file_for_guid(index, "N06_999") is None


# --- Field updates ---------------------------------------------------------


def test_field_updates_touch_only_the_named_guids(tmp_path: Path) -> None:
    release_file = tmp_path / "base.jsonl"
    _write_jsonl(
        release_file,
        [
            {"guid": "N06_001", "difficulty_level": 1},
            {"guid": "N06_002", "difficulty_level": 2},
        ],
    )

    release_io.apply_field_updates({release_file: {"N06_001": {"difficulty_level": 5}}})

    records = _read_jsonl(release_file)
    assert records[0]["difficulty_level"] == 5
    assert records[1]["difficulty_level"] == 2


def test_dotted_paths_address_nested_fields(tmp_path: Path) -> None:
    release_file = tmp_path / "base.jsonl"
    _write_jsonl(
        release_file, [{"guid": "N06_001", "translations": {"en": "bread", "lt": "duona"}}]
    )

    release_io.apply_field_updates({release_file: {"N06_001": {"translations.en": "loaf"}}})

    record = _read_jsonl(release_file)[0]
    assert record["translations"] == {"en": "loaf", "lt": "duona"}


def test_dotted_path_creates_a_missing_parent(tmp_path: Path) -> None:
    release_file = tmp_path / "base.jsonl"
    _write_jsonl(release_file, [{"guid": "N06_001"}])

    release_io.apply_field_updates({release_file: {"N06_001": {"translations.en": "bread"}}})

    assert _read_jsonl(release_file)[0]["translations"] == {"en": "bread"}


def test_remove_field_deletes_rather_than_nulls(tmp_path: Path) -> None:
    """An unpaired lemma must lose its qid, not carry a null one."""
    release_file = tmp_path / "base.jsonl"
    _write_jsonl(release_file, [{"guid": "N06_001", "qid": "Q7802"}])

    release_io.apply_field_updates({release_file: {"N06_001": {"qid": release_io.REMOVE_FIELD}}})

    assert "qid" not in _read_jsonl(release_file)[0]


def test_remove_field_works_on_a_dotted_path(tmp_path: Path) -> None:
    release_file = tmp_path / "base.jsonl"
    _write_jsonl(
        release_file, [{"guid": "N06_001", "translations": {"en": "bread", "lt": "duona"}}]
    )

    release_io.apply_field_updates(
        {release_file: {"N06_001": {"translations.lt": release_io.REMOVE_FIELD}}}
    )

    assert _read_jsonl(release_file)[0]["translations"] == {"en": "bread"}


def test_unparseable_lines_are_preserved_verbatim(tmp_path: Path) -> None:
    """A line we cannot read must survive a write that did not target it."""
    release_file = tmp_path / "base.jsonl"
    release_file.parent.mkdir(parents=True, exist_ok=True)
    release_file.write_text(
        '{"guid": "N06_001", "difficulty_level": 1}\nbroken line\n', encoding="utf-8"
    )

    release_io.apply_field_updates({release_file: {"N06_001": {"difficulty_level": 3}}})

    assert "broken line" in release_file.read_text(encoding="utf-8")


def test_updating_a_missing_file_is_a_no_op(tmp_path: Path) -> None:
    assert release_io.apply_field_updates({tmp_path / "gone.jsonl": {"N06_001": {}}}) == 0


# --- Translation updates ---------------------------------------------------


def test_translation_updates_merge_into_the_existing_map(tmp_path: Path) -> None:
    release_file = tmp_path / "base.jsonl"
    _write_jsonl(release_file, [{"guid": "N06_001", "translations": {"en": "bread"}}])

    release_io.apply_translation_updates({release_file: {"N06_001": {"lt": "duona"}}})

    assert _read_jsonl(release_file)[0]["translations"] == {"en": "bread", "lt": "duona"}


def test_an_empty_translation_removes_the_language(tmp_path: Path) -> None:
    """ "No translation" round-trips as a missing key, never as an empty string."""
    release_file = tmp_path / "base.jsonl"
    _write_jsonl(
        release_file, [{"guid": "N06_001", "translations": {"en": "bread", "lt": "duona"}}]
    )

    release_io.apply_translation_updates({release_file: {"N06_001": {"lt": ""}}})

    assert _read_jsonl(release_file)[0]["translations"] == {"en": "bread"}


def test_prefixed_keys_route_to_disambiguations(tmp_path: Path) -> None:
    release_file = tmp_path / "base.jsonl"
    _write_jsonl(release_file, [{"guid": "N06_001", "translations": {"en": "bank"}}])

    release_io.apply_translation_updates(
        {release_file: {"N06_001": {"lt": "krantas", "_disambig_lt": "riverside"}}},
        disambiguation_prefix="_disambig_",
    )

    record = _read_jsonl(release_file)[0]
    assert record["translations"] == {"en": "bank", "lt": "krantas"}
    assert record["translation_disambiguations"] == {"lt": "riverside"}


def test_prefix_routing_is_off_unless_asked_for(tmp_path: Path) -> None:
    """Without the prefix argument a "_disambig_lt" key is just a language key."""
    release_file = tmp_path / "base.jsonl"
    _write_jsonl(release_file, [{"guid": "N06_001", "translations": {}}])

    release_io.apply_translation_updates({release_file: {"N06_001": {"_disambig_lt": "x"}}})

    assert _read_jsonl(release_file)[0]["translations"] == {"_disambig_lt": "x"}


# --- Writing ---------------------------------------------------------------


def test_write_jsonl_sorted_orders_by_guid(tmp_path: Path) -> None:
    release_file = tmp_path / "base.jsonl"
    release_io.write_jsonl_sorted(
        release_file, [{"guid": "N06_003"}, {"guid": "N06_001"}, {"guid": "N06_002"}]
    )
    assert [record["guid"] for record in _read_jsonl(release_file)] == [
        "N06_001",
        "N06_002",
        "N06_003",
    ]


def test_upsert_replaces_matches_and_keeps_siblings(tmp_path: Path) -> None:
    release_file = tmp_path / "base.jsonl"
    _write_jsonl(
        release_file,
        [
            {"guid": "N06_001", "concept_label": "bread"},
            {"guid": "N06_003", "concept_label": "jam"},
        ],
    )

    merged = release_io.upsert_records(
        release_file,
        [
            {"guid": "N06_001", "concept_label": "loaf"},
            {"guid": "N06_002", "concept_label": "milk"},
        ],
    )

    assert merged == 2
    records = _read_jsonl(release_file)
    assert [record["guid"] for record in records] == ["N06_001", "N06_002", "N06_003"]
    assert records[0]["concept_label"] == "loaf"
    assert records[2]["concept_label"] == "jam"


def test_upsert_creates_the_file_and_its_directory(tmp_path: Path) -> None:
    release_file = tmp_path / "nouns" / "food" / "base.jsonl"
    release_io.upsert_records(release_file, [{"guid": "N06_001"}])
    assert _read_jsonl(release_file) == [{"guid": "N06_001"}]


# --- Pagination ------------------------------------------------------------


def test_paginate_slices_to_the_requested_page(app: Flask) -> None:
    items = list(range(500))
    with app.test_request_context("/?page=2&per_page=200"):
        page = paginate(items)
    assert page.items == items[200:400]
    assert (page.page, page.pages, page.total) == (2, 3, 500)
    assert (page.first_index, page.last_index) == (201, 400)


def test_paginate_defaults_to_the_first_page(app: Flask) -> None:
    with app.test_request_context("/"):
        page = paginate(list(range(10)))
    assert (page.page, page.pages) == (1, 1)
    assert page.has_prev is False and page.has_next is False


def test_per_page_zero_shows_everything(app: Flask) -> None:
    with app.test_request_context("/?per_page=0"):
        page = paginate(list(range(2000)))
    assert page.unlimited is True
    assert len(page.items) == 2000
    assert page.pages == 1


def test_an_out_of_range_page_clamps_to_the_last_one(app: Flask) -> None:
    """A stale bookmark should show the last page, not an error."""
    with app.test_request_context("/?page=99&per_page=50"):
        page = paginate(list(range(120)))
    assert page.page == 3
    assert page.items == list(range(100, 120))


def test_unparseable_paging_arguments_fall_back(app: Flask) -> None:
    with app.test_request_context("/?page=banana&per_page=lots"):
        page = paginate(list(range(10)))
    assert (page.page, page.per_page) == (1, 200)


def test_an_unoffered_page_size_falls_back(app: Flask) -> None:
    """Only the sizes the selector offers are honoured."""
    with app.test_request_context("/?per_page=17"):
        page = paginate(list(range(10)))
    assert page.per_page in PER_PAGE_CHOICES
    assert page.per_page == 200


def test_an_empty_list_still_has_one_page(app: Flask) -> None:
    with app.test_request_context("/"):
        page = paginate([])
    assert (page.pages, page.total, page.first_index) == (1, 0, 0)


def test_page_numbers_elide_long_runs() -> None:
    page = Page(items=[], page=10, per_page=10, total=500)
    numbers = page.page_numbers(window=1)
    assert numbers[0] == 1
    assert numbers[-1] == 50
    assert None in numbers
    assert {9, 10, 11}.issubset({number for number in numbers if number is not None})


def test_page_numbers_of_a_short_list_are_contiguous() -> None:
    page = Page(items=[], page=1, per_page=10, total=25)
    assert page.page_numbers() == [1, 2, 3]


def test_page_args_drops_page_and_keeps_filters(app: Flask) -> None:
    with app.test_request_context("/?page=4&lang=ta&lang=kn&per_page=50"):
        args = page_args()
    assert "page" not in args
    assert args["lang"] == ["ta", "kn"]
    assert args["per_page"] == "50"


# --- Per-language form records ---------------------------------------------


def _derivative(**overrides: Any) -> DerivativeForm:
    fields: Dict[str, Any] = {
        "grammatical_form": "noun/lt_plural",
        "derivative_form_text": "šunys",
        "is_base_form": False,
        "ipa_pronunciation": None,
        "phonetic_pronunciation": None,
    }
    fields.update(overrides)
    return DerivativeForm(**fields)


def test_db_form_to_dict_reads_the_form_text() -> None:
    """The column is derivative_form_text; naming it wrong silently exports nothing."""
    record = sync_release_helpers.db_form_to_dict(form=_derivative(), include_base_form=True)
    assert record["text"] == "šunys"
    assert record["grammatical_form"] == "noun/lt_plural"


def test_db_form_to_dict_carries_base_form_only_for_inflections() -> None:
    inflection = sync_release_helpers.db_form_to_dict(
        form=_derivative(is_base_form=True), include_base_form=True
    )
    synonym = sync_release_helpers.db_form_to_dict(
        form=_derivative(grammatical_form="synonym", derivative_form_text="kalė"),
        include_base_form=False,
    )
    assert inflection["is_base_form"] is True
    assert "is_base_form" not in synonym


def test_db_form_to_dict_omits_empty_pronunciations() -> None:
    record = sync_release_helpers.db_form_to_dict(form=_derivative(), include_base_form=True)
    assert "ipa" not in record and "phonetic" not in record

    with_ipa = sync_release_helpers.db_form_to_dict(
        form=_derivative(ipa_pronunciation="ʃuːnʲiːs"), include_base_form=True
    )
    assert with_ipa["ipa"] == "ʃuːnʲiːs"


def test_languages_with_release_files_ignores_grouped_files(tmp_path: Path) -> None:
    """base/secondary/ancient are file names, not language codes."""
    for name in ("lt", "en", "base", "secondary", "ancient", "audio"):
        _write_jsonl(tmp_path / "nouns" / "food" / f"{name}.jsonl", [{"guid": "N06_001"}])

    assert sync_release_helpers.languages_with_release_files(tmp_path) == {"lt", "en"}
