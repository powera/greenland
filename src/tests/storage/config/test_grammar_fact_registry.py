from agents.lape.agent import LapeAgent
from storage.config.grammar_fact_registry import (
    VERB_FORM_OVERRIDE_PREFIX,
    get_generatable_fact_definitions,
    is_release_grammar_fact_type,
    legacy_supported_fact_types,
)
from workqueue.handlers.lape import SUPPORTED_FACT_TYPES


def test_lape_and_workqueue_share_supported_fact_registry() -> None:
    expected = legacy_supported_fact_types()

    assert LapeAgent.SUPPORTED_FACT_TYPES == expected
    assert SUPPORTED_FACT_TYPES == expected
    assert set(expected) == set(get_generatable_fact_definitions())
    assert "ru" not in expected["grammatical_gender"]["languages"]
    assert "nl" in expected["auxiliary_verb"]["languages"]


def test_release_registry_accepts_exact_and_verb_form_prefix_facts() -> None:
    assert is_release_grammar_fact_type("lt", "3s_present")
    assert is_release_grammar_fact_type("it", "1s_future")
    assert is_release_grammar_fact_type("en", "past")
    assert is_release_grammar_fact_type("en", "past_participle")
    assert is_release_grammar_fact_type("fr", "past_participle")
    assert is_release_grammar_fact_type("sv", "past_participle")
    assert is_release_grammar_fact_type("en", "plural")
    assert is_release_grammar_fact_type("de", "plural")
    assert is_release_grammar_fact_type("lt", "number_type")
    assert is_release_grammar_fact_type("fr", "feminine_form")
    assert is_release_grammar_fact_type("nl", "comparative")
    assert is_release_grammar_fact_type("pt", "superlative")
    assert is_release_grammar_fact_type("es", f"{VERB_FORM_OVERRIDE_PREFIX}3s_past")
    assert is_release_grammar_fact_type("sv", f"{VERB_FORM_OVERRIDE_PREFIX}past")
    assert not is_release_grammar_fact_type("zh", "measure_words")
    assert not is_release_grammar_fact_type("zh", "default_measure_word")
    assert not is_release_grammar_fact_type("zh", "plural")
    assert not is_release_grammar_fact_type("fr", "past")
    assert not is_release_grammar_fact_type("vi", f"{VERB_FORM_OVERRIDE_PREFIX}past")
