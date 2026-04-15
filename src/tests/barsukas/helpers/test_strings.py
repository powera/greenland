"""Tests for Barsukas string helper accessors."""

from markupsafe import escape

from barsukas.helpers.strings import SUPPORTED_UI_LANGS
from strings.barsukas_helpers import (
    create_cstr_accessor,
    create_lstr_accessor,
    create_sstr_accessor,
)


def test_lstr_resolves_common_default_path() -> None:
    strings_by_namespace = {
        "common": {"level": "Level"},
    }
    lstr = create_lstr_accessor(strings_by_namespace, default_module="dictionary")

    assert str(lstr.level) == "Level"


def test_lstr_resolves_current_other_and_explicit_namespace_paths() -> None:
    strings_by_namespace = {
        "common": {"level": "Common Level"},
        "dictionary": {"level": "Dictionary Level"},
        "navigation": {"sort_by": "Sort by"},
    }
    lstr = create_lstr_accessor(strings_by_namespace, default_module="dictionary")

    assert str(lstr.CURRENT.level) == "Dictionary Level"
    assert str(lstr.OTHER.navigation.sort_by) == "Sort by"
    assert str(lstr.navigation.sort_by) == "Sort by"


def test_sstr_requires_namespace() -> None:
    strings_by_namespace = {
        "sentences": {"edit_title": "Edit sentence"},
    }
    sstr = create_sstr_accessor(strings_by_namespace, default_module="common")

    assert str(sstr.sentences.edit_title) == "Edit sentence"
    assert str(sstr.edit_title) == ""


def test_cstr_requires_namespace() -> None:
    strings_by_namespace = {
        "ipa": {"intro_block": "<p>Intro block.</p>"},
    }
    cstr = create_cstr_accessor(strings_by_namespace, default_module="common")

    assert str(cstr.ipa.intro_block) == "<p>Intro block.</p>"
    assert str(cstr.intro_block) == ""


def test_accessors_do_not_expose_dunder_attributes_to_markupsafe() -> None:
    lstr = create_lstr_accessor({"common": {"apply": "Apply"}}, default_module="common")

    with_dunder_lookup = lstr.apply
    assert str(escape(with_dunder_lookup)) == "Apply"


def test_barsukas_wrapper_re_exports_supported_languages() -> None:
    assert SUPPORTED_UI_LANGS == frozenset({"en", "lt"})
