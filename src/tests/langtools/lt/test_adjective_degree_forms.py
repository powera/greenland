"""Lithuanian adjectives carry degree forms alongside their case table.

A comparative declines like any other adjective, so the complete paradigm would
be 3 degrees x 28 cases = 84 forms.  Trakaido does not drill declension tables,
so only the cases that carry ordinary sentences are stored -- nominative ("the
apple was redder") and accusative ("he has a redder apple") -- in both genders
and numbers, which is 8 per degree.

Degree rides on ``extra_forms`` rather than becoming a third axis of the case
expansion, so adding it multiplies nothing: a language that wants degree lists
exactly the slots it needs.
"""

from langtools.form_patterns import expand_fields
from langtools.form_registry import FORM_SPECS
from storage.models.enums import GrammaticalForm

EXPECTED_POSITIVE_FORMS = 7 * 2 * 2  # cases x numbers x genders
EXPECTED_FORMS_PER_DEGREE = 2 * 2 * 2  # (nom, acc) x numbers x genders
EXPECTED_TOTAL = EXPECTED_POSITIVE_FORMS + 2 * EXPECTED_FORMS_PER_DEGREE


def _degree_fields(prefix: str) -> list:
    spec = FORM_SPECS[("lt", "adjective")]
    return [field for field in spec.form_fields if field.startswith(prefix)]


def test_adjective_spec_carries_case_table_and_both_degrees() -> None:
    spec = FORM_SPECS[("lt", "adjective")]

    assert len(spec.form_fields) == EXPECTED_TOTAL
    assert len(_degree_fields("comparative_")) == EXPECTED_FORMS_PER_DEGREE
    assert len(_degree_fields("superlative_")) == EXPECTED_FORMS_PER_DEGREE


def test_degree_forms_cover_only_nominative_and_accusative() -> None:
    """The other five cases are deliberately absent, not forgotten."""
    for prefix in ("comparative_", "superlative_"):
        cases = {field.split("_")[1] for field in _degree_fields(prefix)}
        assert cases == {"nominative", "accusative"}


def test_degree_forms_cover_both_numbers_and_genders() -> None:
    """ "those apples were the reddest" needs a plural superlative."""
    fields = set(_degree_fields("superlative_"))

    assert "superlative_nominative_plural_m" in fields
    assert "superlative_nominative_plural_f" in fields
    assert "superlative_accusative_singular_m" in fields


def test_degree_slots_resolve_to_grammatical_form_enum_members() -> None:
    """Enum members are generated from the config, so the slots must resolve."""
    spec = FORM_SPECS[("lt", "adjective")]

    for field in _degree_fields("comparative_") + _degree_fields("superlative_"):
        value = f"adjective/lt_{field}"
        assert GrammaticalForm(value).value == value
        assert spec.form_mapping[field].value == value


def test_extra_forms_are_optional_for_case_number_gender() -> None:
    """A language that lists no degree slots is unaffected by the new support."""
    config = {
        "type": "case_number_gender",
        "cases": ["nominative", "genitive"],
        "numbers": ["singular", "plural"],
        "genders": ["m", "f"],
    }

    assert len(expand_fields(config)) == 2 * 2 * 2


def test_extra_forms_append_after_the_case_table() -> None:
    config = {
        "type": "case_number_gender",
        "cases": ["nominative"],
        "numbers": ["singular"],
        "genders": ["m"],
        "extra_forms": ["comparative_nominative_singular_m"],
    }

    assert expand_fields(config) == [
        "nominative_singular_m",
        "comparative_nominative_singular_m",
    ]
