"""Smoke tests for langtools modules.

These tests verify that all language modules can be imported and
their basic configurations are valid. This catches basic syntax errors,
import issues, and structural problems.

Note: These tests gracefully handle missing optional dependencies
(like bs4, sqlalchemy) since they may not be available in all environments.
The focus is on catching Python syntax errors and structural issues.
"""

import importlib
import unittest
from typing import Any, Dict, Optional

import pytest


def is_missing_dependency_error(error: Exception) -> bool:
    """Check if an error is due to a missing external dependency."""
    error_str = str(error)
    # Common patterns for missing dependencies
    missing_modules = ["bs4", "sqlalchemy", "pypinyin", "jieba", "opencc"]
    return any(f"No module named '{mod}'" in error_str for mod in missing_modules)


def import_module_safely(module_name: str) -> tuple[Optional[Any], Optional[str]]:
    """
    Try to import a module, distinguishing between missing dependencies and real errors.

    Returns:
        (module, error_msg) where:
        - If successful: (module_object, None)
        - If missing dependency: (None, None) - acceptable, not an error
        - If real error (syntax, etc.): (None, error_msg)
    """
    try:
        module = importlib.import_module(module_name)
        return module, None
    except ImportError as e:
        # If it's just a missing dependency, that's acceptable
        if is_missing_dependency_error(e):
            return None, None
        # Otherwise it's a real import error
        return None, str(e)
    except Exception as e:
        # Any other error (syntax, etc.) is a real problem
        return None, str(e)


# All supported language codes
ALL_LANGUAGES = [
    "am",
    "az",
    "bg",
    "bn",
    "cs",
    "da",
    "de",
    "el",
    "en",
    "es",
    "et",
    "fa",
    "fi",
    "fr",
    "ga",
    "gu",
    "ha",
    "hi",
    "hr",
    "hu",
    "hy",
    "id",
    "ig",
    "it",
    "ja",
    "ka",
    "kk",
    "km",
    "kn",
    "ko",
    "lo",
    "lt",
    "lv",
    "ml",
    "mr",
    "ms",
    "mt",
    "my",
    "nl",
    "om",
    "or",
    "pa",
    "pl",
    "ps",
    "pt",
    "ro",
    "si",
    "sk",
    "sl",
    "sn",
    "so",
    "sv",
    "sw",
    "ta",
    "te",
    "th",
    "tl",
    "tr",
    "uk",
    "ur",
    "uz",
    "vi",
    "xh",
    "yo",
    "zh",
    "zu",
]

# Language codes that are Python reserved keywords. These cannot appear in an
# `import langtools.or` statement, but nothing needs to: every caller outside
# src/langtools reaches languages dynamically, e.g. get_verb_conjugation(lang="or").
KEYWORD_CONFLICT_LANGUAGES = ["or"]  # "or" is Odia but conflicts with Python's "or" keyword


@pytest.mark.smoke
class TestLanguageModuleImports(unittest.TestCase):
    """Test that all language modules can be imported."""

    def test_keyword_conflict_languages_import_dynamically(self) -> None:
        """Keyword-named language codes must still be reachable via import_module.

        The statement form (`import langtools.or`) is a syntax error, so the
        dynamic path is the only way in and must keep working.
        """
        for lang_code in KEYWORD_CONFLICT_LANGUAGES:
            with self.subTest(lang=lang_code):
                module = importlib.import_module(f"langtools.{lang_code}")
                self.assertIsNotNone(module)

    def test_all_language_init_imports(self) -> None:
        """Test that __init__.py can be imported for all languages."""
        errors = {}
        for lang_code in ALL_LANGUAGES:
            # Skip languages with keyword conflicts
            if lang_code in KEYWORD_CONFLICT_LANGUAGES:
                continue

            with self.subTest(lang=lang_code):
                _, error = import_module_safely(f"langtools.{lang_code}")
                if error:
                    errors[lang_code] = error

        if errors:
            error_msg = "\n".join(f"  {lang}: {err}" for lang, err in errors.items())
            self.fail(f"Failed to import {len(errors)} language modules:\n{error_msg}")

    def test_all_language_types_imports(self) -> None:
        """Test that types.py can be imported for all languages."""
        errors = {}
        for lang_code in ALL_LANGUAGES:
            # Skip languages with keyword conflicts
            if lang_code in KEYWORD_CONFLICT_LANGUAGES:
                continue

            with self.subTest(lang=lang_code):
                _, error = import_module_safely(f"langtools.{lang_code}.types")
                if error:
                    errors[lang_code] = error

        if errors:
            error_msg = "\n".join(f"  {lang}: {err}" for lang, err in errors.items())
            self.fail(f"Failed to import types for {len(errors)} languages:\n{error_msg}")

    def test_all_language_llm_forms_imports(self) -> None:
        """Test that llm_forms.py can be imported for all enabled languages.

        Pattern B languages are scaffolded but not registered in FORM_SPECS
        (see form_registry.py), so importing their llm_forms raises KeyError.
        They are skipped until their forms_config.py files are written.
        """
        from langtools.form_registry import _PATTERN_B_LANGS

        not_yet_enabled = {lang_code for lang_code, _ in _PATTERN_B_LANGS}

        errors = {}
        for lang_code in ALL_LANGUAGES:
            # Skip languages with keyword conflicts
            if lang_code in KEYWORD_CONFLICT_LANGUAGES:
                continue
            if lang_code in not_yet_enabled:
                continue

            with self.subTest(lang=lang_code):
                _, error = import_module_safely(f"langtools.{lang_code}.llm_forms")
                if error:
                    errors[lang_code] = error

        if errors:
            error_msg = "\n".join(f"  {lang}: {err}" for lang, err in errors.items())
            self.fail(f"Failed to import llm_forms for {len(errors)} languages:\n{error_msg}")


class TestFormsConfigParsing(unittest.TestCase):
    """Test that forms_config.py files are valid and parseable."""

    # Languages that should have forms_config.py
    LANGUAGES_WITH_FORMS_CONFIG = [
        "am",
        "bg",
        "bn",
        "cs",
        "da",
        "de",
        "el",
        "en",
        "es",
        "et",
        "fi",
        "fr",
        "ga",
        "ha",
        "hi",
        "hr",
        "hu",
        "ig",
        "it",
        "ja",
        "km",
        "kn",
        "ko",
        "lo",
        "lt",
        "lv",
        "ml",
        "mt",
        "my",
        "nl",
        "om",
        "pl",
        "pt",
        "ro",
        "si",
        "sk",
        "sl",
        "sn",
        "so",
        "sv",
        "sw",
        "ta",
        "te",
        "th",
        "uk",
        "vi",
        "xh",
        "yo",
        "zh",
        "zu",
    ]

    def test_forms_config_imports(self) -> None:
        """Test that forms_config.py can be imported for languages that have it."""
        errors = {}
        for lang_code in self.LANGUAGES_WITH_FORMS_CONFIG:
            with self.subTest(lang=lang_code):
                _, error = import_module_safely(f"langtools.{lang_code}.forms_config")
                if error:
                    errors[lang_code] = error

        if errors:
            error_msg = "\n".join(f"  {lang}: {err}" for lang, err in errors.items())
            self.fail(f"Failed to import forms_config for {len(errors)} languages:\n{error_msg}")

    def test_forms_config_structure(self) -> None:
        """Test that forms_config.py files have required attributes."""
        errors = {}
        for lang_code in self.LANGUAGES_WITH_FORMS_CONFIG:
            with self.subTest(lang=lang_code):
                try:
                    module, error = import_module_safely(f"langtools.{lang_code}.forms_config")
                    if error:
                        errors[lang_code] = error
                        continue
                    if module is None:
                        # Missing dependency, skip
                        continue

                    # Check that LANGUAGE_CODE and LANGUAGE_NAME exist
                    if not hasattr(module, "LANGUAGE_CODE"):
                        errors[lang_code] = "Missing LANGUAGE_CODE"
                        continue

                    if not hasattr(module, "LANGUAGE_NAME"):
                        errors[lang_code] = "Missing LANGUAGE_NAME"
                        continue

                    # Verify LANGUAGE_CODE matches the directory name
                    if module.LANGUAGE_CODE != lang_code:
                        errors[lang_code] = (
                            f"LANGUAGE_CODE mismatch: expected '{lang_code}', "
                            f"got '{module.LANGUAGE_CODE}'"
                        )
                        continue

                    # Check that LANGUAGE_NAME is a non-empty string
                    if not isinstance(module.LANGUAGE_NAME, str) or not module.LANGUAGE_NAME:
                        errors[lang_code] = (
                            f"LANGUAGE_NAME should be non-empty string, got {module.LANGUAGE_NAME!r}"
                        )
                        continue

                except Exception as e:
                    # Catch any unexpected exceptions
                    if not is_missing_dependency_error(e):
                        errors[lang_code] = str(e)

        if errors:
            error_msg = "\n".join(f"  {lang}: {err}" for lang, err in errors.items())
            self.fail(f"Forms config structure issues in {len(errors)} languages:\n{error_msg}")

    def test_noun_config_structure(self) -> None:
        """Test that NOUN_CONFIG has valid structure when present."""
        errors = {}
        for lang_code in self.LANGUAGES_WITH_FORMS_CONFIG:
            with self.subTest(lang=lang_code):
                try:
                    module, error = import_module_safely(f"langtools.{lang_code}.forms_config")
                    if error:
                        errors[lang_code] = f"Error checking NOUN_CONFIG: {error}"
                        continue
                    if module is None:
                        # Missing dependency, skip
                        continue

                    if not hasattr(module, "NOUN_CONFIG"):
                        # NOUN_CONFIG is optional
                        continue

                    noun_config = module.NOUN_CONFIG
                    if not isinstance(noun_config, dict):
                        errors[lang_code] = f"NOUN_CONFIG should be dict, got {type(noun_config)}"
                        continue

                    # Check for required fields
                    if "type" not in noun_config:
                        errors[lang_code] = "NOUN_CONFIG missing 'type' field"
                        continue

                except Exception as e:
                    if not is_missing_dependency_error(e):
                        errors[lang_code] = f"Error checking NOUN_CONFIG: {e}"

        if errors:
            error_msg = "\n".join(f"  {lang}: {err}" for lang, err in errors.items())
            self.fail(f"NOUN_CONFIG structure issues in {len(errors)} languages:\n{error_msg}")

    def test_verb_config_structure(self) -> None:
        """Test that VERB_CONFIG has valid structure when present."""
        errors = {}
        for lang_code in self.LANGUAGES_WITH_FORMS_CONFIG:
            with self.subTest(lang=lang_code):
                try:
                    module, error = import_module_safely(f"langtools.{lang_code}.forms_config")
                    if error:
                        errors[lang_code] = f"Error checking VERB_CONFIG: {error}"
                        continue
                    if module is None:
                        # Missing dependency, skip
                        continue

                    if not hasattr(module, "VERB_CONFIG"):
                        # VERB_CONFIG is optional
                        continue

                    verb_config = module.VERB_CONFIG
                    if not isinstance(verb_config, dict):
                        errors[lang_code] = f"VERB_CONFIG should be dict, got {type(verb_config)}"
                        continue

                    # Check for required fields
                    if "type" not in verb_config:
                        errors[lang_code] = "VERB_CONFIG missing 'type' field"
                        continue

                except Exception as e:
                    if not is_missing_dependency_error(e):
                        errors[lang_code] = f"Error checking VERB_CONFIG: {e}"

        if errors:
            error_msg = "\n".join(f"  {lang}: {err}" for lang, err in errors.items())
            self.fail(f"VERB_CONFIG structure issues in {len(errors)} languages:\n{error_msg}")


class TestSharedModules(unittest.TestCase):
    """Test that shared langtools modules can be imported."""

    def test_collation_import(self) -> None:
        """Test that collation module can be imported."""
        try:
            import langtools.collation
        except Exception as e:
            self.fail(f"Failed to import langtools.collation: {e}")

    def test_dialect_overrides_import(self) -> None:
        """Test that dialect_overrides module can be imported."""
        try:
            import langtools.dialect_overrides
        except Exception as e:
            self.fail(f"Failed to import langtools.dialect_overrides: {e}")

    def test_form_patterns_import(self) -> None:
        """Test that form_patterns module can be imported."""
        try:
            import langtools.form_patterns
        except Exception as e:
            self.fail(f"Failed to import langtools.form_patterns: {e}")


class TestDispatchers(unittest.TestCase):
    """Test the cross-language dispatchers (inflection, conjugation, wiktionary).

    These dispatchers resolve per-language modules/classes by *string* name, so
    a renamed parser class or builder would fail silently at runtime.  These
    tests pin the registries to the real modules to catch that.
    """

    def test_wiktionary_parser_registry_resolves(self) -> None:
        """Every registered Wiktionary parser must expose the standard methods."""
        from langtools.wiktionary import _PARSER_SPECS, _POS_TO_METHOD

        errors = {}
        for lang_code, (module_path, class_name) in _PARSER_SPECS.items():
            with self.subTest(lang=lang_code):
                module, error = import_module_safely(module_path)
                if error:
                    errors[lang_code] = error
                    continue
                if module is None:
                    # Missing optional dependency (bs4, etc.); acceptable.
                    continue
                parser_cls = getattr(module, class_name, None)
                if parser_cls is None:
                    errors[lang_code] = f"{module_path} has no class {class_name}"
                    continue
                missing = [
                    method_name
                    for method_name in _POS_TO_METHOD.values()
                    if not callable(getattr(parser_cls, method_name, None))
                ]
                if missing:
                    errors[lang_code] = f"{class_name} missing methods: {missing}"

        if errors:
            error_msg = "\n".join(f"  {lang}: {err}" for lang, err in errors.items())
            self.fail(f"Wiktionary parser registry issues:\n{error_msg}")

    def test_inflection_dispatcher_resolves_english(self) -> None:
        """The inflection dispatcher must reach English builders and honor facts."""
        from langtools.inflection import inflect

        # Grammar facts are threaded through and consumed by the builder.
        self.assertEqual(
            inflect("giraffe", "en", "noun"),
            {"singular": "giraffe", "plural": "giraffes"},
        )
        self.assertEqual(
            inflect("rice", "en", "noun", {"countability": "uncountable"}),
            {"singular": "rice"},
        )
        # Unsupported language falls through to None rather than raising.
        self.assertIsNone(inflect("foo", "xx", "noun"))

    def test_conjugation_dispatcher_resolves_english(self) -> None:
        """The conjugation dispatcher must reach the English conjugator."""
        from langtools.conjugation import conjugate

        forms = conjugate("walk", "en")
        assert forms is not None
        self.assertEqual(forms["3s_present"], "walks")
        self.assertIsNone(conjugate("foo", "xx"))


if __name__ == "__main__":
    unittest.main()
