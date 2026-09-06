"""Behavioral tests for the cross-language langtools dispatchers."""

import importlib

import pytest

from langtools.conjugation import conjugate
from langtools.dialect_overrides import get_llm_prompt_note
from langtools.directions import get_language_direction_note
from langtools.inflection import inflect
from langtools.wiktionary import _PARSER_SPECS, _POS_TO_METHOD

# Optional native deps only.  sqlalchemy is a hard dependency and must never
# be listed here: swallowing its ModuleNotFoundError would turn a real breakage
# into a silent pass.
OPTIONAL_DEPENDENCIES = {"bs4", "jieba", "opencc", "pypinyin", "pykakasi"}


def test_wiktionary_parser_registry_resolves_adapters() -> None:
    """Registered parser names resolve to adapters with the shared interface."""
    failures: list[str] = []
    skipped: list[str] = []

    for language_code, (module_path, class_name) in _PARSER_SPECS.items():
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as error:
            if error.name in OPTIONAL_DEPENDENCIES:
                skipped.append(f"{language_code} ({error.name})")
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

    # Every parser skipped for a missing optional dep means this test verified
    # less than it appears to.  Skip rather than pass green on an empty check.
    if skipped and len(skipped) == len(_PARSER_SPECS):
        pytest.skip("no wiktionary parser could be imported: " + ", ".join(skipped))


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


def test_dispatchers_route_a_dialect_to_its_parent_module() -> None:
    """There is no langtools/en-gb/, and there should not need to be.

    A dialect differs in vocabulary and accent, not in morphology, so it uses
    the parent's engines rather than a copy of them.
    """
    assert inflect("giraffe", "en-gb", "noun") == inflect("giraffe", "en", "noun")
    assert conjugate("walk", "en-gb") == conjugate("walk", "en")


def test_dispatchers_accept_unnormalized_dialect_codes() -> None:
    assert inflect("giraffe", "en_GB", "noun") == inflect("giraffe", "en", "noun")


def test_a_dialect_does_not_inherit_its_parents_variant_direction_note() -> None:
    """The parent's note pins the default variant and would contradict the dialect.

    "For Spanish, use Castilian" is exactly wrong for es-419; the dialect's own
    llm_prompt_note says what to use instead.
    """
    assert get_language_direction_note("es")
    assert get_language_direction_note("es-419") == ""
    assert get_language_direction_note("zh-tw") == ""
    assert get_llm_prompt_note("es-419")
