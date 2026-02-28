from importlib import util
from pathlib import Path
from types import SimpleNamespace


_MODULE_PATH = Path(__file__).with_name("tiers.py")
_SPEC = util.spec_from_file_location("benchmarks_tiers", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

get_benchmark_tier = _MODULE.get_benchmark_tier
get_model_max_tier = _MODULE.get_model_max_tier
model_can_run_benchmark = _MODULE.model_can_run_benchmark
get_tier_label = _MODULE.get_tier_label


def test_get_benchmark_tier_assigns_screening_benchmarks():
    assert get_benchmark_tier("0016_antonym") == 1
    assert get_benchmark_tier("0029_placeholder") == 1
    assert get_benchmark_tier("0107_translation_fr_ko") == 1


def test_get_benchmark_tier_defaults_to_full_for_other_benchmarks():
    assert get_benchmark_tier("0062_sentence_decomposition") == 2
    assert get_benchmark_tier("0152_syllogism_validity") == 2
    assert get_benchmark_tier("bad_code") == 2


def test_model_tier_helpers_guard_eligibility():
    restricted_model = SimpleNamespace(max_benchmark_tier=1)
    unrestricted_model = SimpleNamespace(max_benchmark_tier=2)

    assert get_model_max_tier(restricted_model) == 1
    assert model_can_run_benchmark(restricted_model, "0016_antonym")
    assert not model_can_run_benchmark(restricted_model, "0152_syllogism_validity")
    assert model_can_run_benchmark(unrestricted_model, "0152_syllogism_validity")


def test_get_tier_label_supports_future_tiers():
    assert get_tier_label(3) == "Tier 3 (Advanced)"
    assert get_tier_label(4) == "Tier 4"
