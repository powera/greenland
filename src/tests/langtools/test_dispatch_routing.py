"""Behavioral tests for the cross-language langtools dispatchers."""

import importlib

import pytest

from langtools.conjugation import conjugate
from langtools.inflection import inflect
from langtools.wiktionary import _PARSER_SPECS, _POS_TO_METHOD

OPTIONAL_DEPENDENCIES = {"bs4", "jieba", "opencc", "pypinyin", "sqlalchemy"}


def test_wiktionary_parser_registry_resolves_adapters() -> None:
    """Registered parser names resolve to adapters with the shared interface."""
    failures: list[str] = []

    for language_code, (module_path, class_name) in _PARSER_SPECS.items():
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as error:
            if error.name in OPTIONAL_DEPENDENCIES:
                continue
            raise

        parser_class = getattr(module, class_name, None)
        if parser_class is None:
            failures.append(f"{language_code}: {module_path} has no class {class_name}")
            continue

        missing_methods = [
            method_name
            for method_name in _POS_TO_METHOD.values()
            if not callable(getattr(parser_class, method_name, None))
        ]
        if missing_methods:
            failures.append(f"{language_code}: {class_name} missing methods: {missing_methods}")

    assert not failures, "Wiktionary parser registry issues:\n  " + "\n  ".join(failures)


@pytest.mark.parametrize(
    ("word", "facts", "expected"),
    [
        ("giraffe", None, {"singular": "giraffe", "plural": "giraffes"}),
        ("rice", {"countability": "uncountable"}, {"singular": "rice"}),
    ],
)
def test_inflection_dispatches_to_english(
    word: str,
    facts: dict[str, str | None] | None,
    expected: dict[str, str],
) -> None:
    """The requested language and grammar facts reach the English adapter."""
    assert inflect(word, "en", "noun", facts) == expected


def test_dispatchers_reject_an_unknown_language() -> None:
    """Both dispatchers use their documented fallback for unsupported languages."""
    assert inflect("example", "xx", "noun") is None
    assert conjugate("example", "xx") is None


def test_conjugation_dispatches_to_english() -> None:
    """Keep one representative generated form as a routing smoke test."""
    forms = conjugate("walk", "en")

    assert forms is not None
    assert forms["3s_present"] == "walks"
