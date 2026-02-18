#!/usr/bin/python3

"""Tests for language-specific verb-form layout lookup."""

from langtools.verb_forms import get_language_verb_forms_config


def test_default_layout_for_unknown_language():
    config = get_language_verb_forms_config("xx")

    assert config["person_slots"] == ["1s", "2s", "3s", "1p", "2p", "3p"]
    assert [slot["key"] for slot in config["core_slots"]] == ["present", "past", "future"]


def test_french_layout_includes_imparfait_and_passe_compose():
    config = get_language_verb_forms_config("fr")

    assert [slot["key"] for slot in config["core_slots"]] == [
        "present",
        "imparfait",
        "passe_compose",
        "futur_simple",
    ]


def test_swedish_and_japanese_are_not_person_indexed():
    swedish = get_language_verb_forms_config("sv")
    japanese = get_language_verb_forms_config("ja")

    assert swedish["person_slots"] == []
    assert japanese["person_slots"] == []
    assert any(slot["key"] == "preterite" for slot in swedish["core_slots"])
    assert any(slot["key"] == "masu_present" for slot in japanese["core_slots"])
