"""Tests for grammatical form normalization and equivalence checking."""

from langtools.form_equivalences import (
    are_grammatical_forms_equivalent,
    normalize_grammatical_form,
)


class TestNormalizeGrammaticalForm:
    """Tests for normalize_grammatical_form."""

    def test_canonical_form_unchanged(self) -> None:
        assert (
            normalize_grammatical_form("noun/lt_locative_singular") == "noun/lt_locative_singular"
        )

    def test_lt_inessive_alias_normalized_to_locative(self) -> None:
        assert (
            normalize_grammatical_form("noun/lt_inessive_singular") == "noun/lt_locative_singular"
        )

    def test_lt_number_before_case_reordered(self) -> None:
        assert (
            normalize_grammatical_form("noun/lt_singular_locative") == "noun/lt_locative_singular"
        )

    def test_lt_singular_inessive_normalized(self) -> None:
        # Both alias resolution and component reordering applied together.
        assert (
            normalize_grammatical_form("noun/lt_singular_inessive") == "noun/lt_locative_singular"
        )

    def test_lt_inessive_plural_normalized(self) -> None:
        assert normalize_grammatical_form("noun/lt_inessive_plural") == "noun/lt_locative_plural"

    def test_adjective_gender_placed_last(self) -> None:
        assert (
            normalize_grammatical_form("adjective/lt_singular_locative_f")
            == "adjective/lt_locative_singular_f"
        )

    def test_adjective_inessive_alias_and_reordering(self) -> None:
        assert (
            normalize_grammatical_form("adjective/lt_singular_inessive_m")
            == "adjective/lt_locative_singular_m"
        )

    def test_non_lt_form_not_aliased(self) -> None:
        # No aliases defined for other languages; form returned as-is.
        assert (
            normalize_grammatical_form("noun/de_accusative_singular")
            == "noun/de_accusative_singular"
        )

    def test_form_without_lang_prefix_returned_as_is(self) -> None:
        assert normalize_grammatical_form("preposition/base") == "preposition/base"

    def test_case_insensitive_normalization(self) -> None:
        assert (
            normalize_grammatical_form("Noun/LT_Inessive_Singular") == "noun/lt_locative_singular"
        )


class TestAreGrammaticalFormsEquivalent:
    """Tests for are_grammatical_forms_equivalent."""

    def test_identical_forms_are_equivalent(self) -> None:
        assert are_grammatical_forms_equivalent(
            "noun/lt_locative_singular", "noun/lt_locative_singular"
        )

    def test_inessive_and_locative_are_equivalent(self) -> None:
        assert are_grammatical_forms_equivalent(
            "noun/lt_locative_singular", "noun/lt_inessive_singular"
        )

    def test_singular_inessive_and_locative_singular_are_equivalent(self) -> None:
        assert are_grammatical_forms_equivalent(
            "noun/lt_locative_singular", "noun/lt_singular_inessive"
        )

    def test_inessive_plural_and_locative_plural_are_equivalent(self) -> None:
        assert are_grammatical_forms_equivalent(
            "noun/lt_locative_plural", "noun/lt_inessive_plural"
        )

    def test_adjective_inessive_and_locative_equivalent(self) -> None:
        assert are_grammatical_forms_equivalent(
            "adjective/lt_locative_singular_f", "adjective/lt_singular_inessive_f"
        )

    def test_different_cases_not_equivalent(self) -> None:
        assert not are_grammatical_forms_equivalent(
            "noun/lt_locative_singular", "noun/lt_genitive_singular"
        )

    def test_different_numbers_not_equivalent(self) -> None:
        assert not are_grammatical_forms_equivalent(
            "noun/lt_locative_singular", "noun/lt_locative_plural"
        )

    def test_different_roles_not_equivalent(self) -> None:
        assert not are_grammatical_forms_equivalent(
            "noun/lt_locative_singular", "adjective/lt_locative_singular"
        )

    def test_non_lt_forms_obey_exact_match(self) -> None:
        assert are_grammatical_forms_equivalent(
            "noun/de_accusative_singular", "noun/de_accusative_singular"
        )
        assert not are_grammatical_forms_equivalent(
            "noun/de_accusative_singular", "noun/de_dative_singular"
        )
