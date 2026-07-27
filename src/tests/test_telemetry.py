"""Tests for LLM token-price estimation."""

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
