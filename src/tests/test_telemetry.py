"""Tests for LLM token-price estimation."""

import pytest

from util.telemetry import CostConfig, ModelTier


def test_gemini_35_flash_lite_pricing() -> None:
    """Gemini 3.5 Flash Lite uses its configured per-million-token rates."""
    model = "gemini-3.5-flash-lite"

    assert CostConfig.get_model_tier(model) is ModelTier.GEMINI_35_FLASH_LITE
    assert (
        CostConfig.estimate_cost(
            tokens_in=1_000_000,
            tokens_out=1_000_000,
            model=model,
        )
        == 2.80
    )


# DigitalOcean model ids embed the vendor name, so they must be matched before
# the first-party substring chain -- "anthropic-claude-fable-5" contains
# "claude" and would otherwise be priced as a first-party Anthropic model.
# Names here are the post-"do/"-strip ids the backend actually sends.
@pytest.mark.parametrize(
    "model, expected_tier",
    [
        ("anthropic-claude-fable-5", ModelTier.DO_CLAUDE_FABLE),
        ("openai-gpt-5.6-sol", ModelTier.DO_GPT_56_SOL),
        ("llama-4-maverick", ModelTier.DO_LLAMA_4_MAVERICK),
        ("deepseek-v4-pro", ModelTier.DO_DEEPSEEK_V4_PRO),
        ("deepseek-4-flash", ModelTier.DO_DEEPSEEK_4_FLASH),
    ],
)
def test_digitalocean_model_tiers(model: str, expected_tier: ModelTier) -> None:
    """Each priced DigitalOcean model resolves to its own tier, not a vendor tier."""
    assert CostConfig.get_model_tier(model) is expected_tier


@pytest.mark.parametrize(
    "model",
    [
        "anthropic-claude-fable-5",
        "openai-gpt-5.6-sol",
        "llama-4-maverick",
        "deepseek-v4-pro",
        "deepseek-4-flash",
    ],
)
def test_digitalocean_models_are_priced(model: str) -> None:
    """A priced DO model yields a non-zero token cost."""
    cost = CostConfig.estimate_cost(tokens_in=1_000_000, tokens_out=1_000_000, model=model)
    assert cost > 0


def test_do_claude_is_not_priced_as_first_party_claude() -> None:
    """The DO rate is used, not CLAUDE_HAIKU or the unknown-model zero."""
    rates = CostConfig.DIGITALOCEAN_COSTS[ModelTier.DO_CLAUDE_FABLE]
    expected = rates["input"] + rates["output"]

    assert (
        CostConfig.estimate_cost(
            tokens_in=1_000_000, tokens_out=1_000_000, model="anthropic-claude-fable-5"
        )
        == expected
    )


def test_all_digitalocean_tiers_carry_real_rates() -> None:
    """Every DO tier is priced, and none is still on the synthetic placeholder."""
    do_tiers = {tier for tier in ModelTier if tier.name.startswith("DO_")}

    assert do_tiers == set(
        CostConfig.DIGITALOCEAN_COSTS
    ), "a DO tier is missing from the cost table"
    for tier, rates in CostConfig.DIGITALOCEAN_COSTS.items():
        assert rates != CostConfig.DIGITALOCEAN_PLACEHOLDER_COST, f"{tier.name} is unpriced"


def test_deepseek_pro_and_flash_price_separately() -> None:
    """The two DeepSeek variants differ ~12x; matching one to the other's tier is a real risk."""
    pro = CostConfig.estimate_cost(
        tokens_in=1_000_000, tokens_out=1_000_000, model="deepseek-v4-pro"
    )
    flash = CostConfig.estimate_cost(
        tokens_in=1_000_000, tokens_out=1_000_000, model="deepseek-4-flash"
    )

    assert pro == 1.39 + 2.78
    assert flash == 0.11 + 0.22
    assert pro > flash


def test_unpriced_digitalocean_model_warns_and_returns_zero() -> None:
    """An unrecognized DO model must not fall through to Ollama compute-time pricing."""
    model = "mistral-large-unpriced"

    assert CostConfig.get_model_tier(model) is ModelTier.OLLAMA
    assert (
        CostConfig.estimate_cost(tokens_in=1000, tokens_out=1000, compute_ms=60_000, model=model)
        == 0.0
    )
