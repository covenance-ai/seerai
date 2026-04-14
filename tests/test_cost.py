"""Tests for pricing logic, value computation, and cost efficiency models."""

import math
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from seerai.cost.endpoint import UTILITY_SCORES, session_value
from seerai.entities import Subscription
from seerai.pricing import API_PRICE_PER_TOKEN, DEFAULT_PRICE_PER_TOKEN, token_cost


class TestTokenCost:
    def test_known_model_uses_table_price(self):
        """Known models use their specific pricing, not the default."""
        cost = token_cost("claude-opus-4", 1_000_000)
        expected = API_PRICE_PER_TOKEN["claude-opus-4"] * 1_000_000
        assert cost == pytest.approx(expected)
        assert cost != DEFAULT_PRICE_PER_TOKEN * 1_000_000

    def test_unknown_model_uses_default(self):
        """Unknown models fall back to DEFAULT_PRICE_PER_TOKEN."""
        cost = token_cost("made-up-model-9000", 1000)
        assert cost == pytest.approx(DEFAULT_PRICE_PER_TOKEN * 1000)

    def test_zero_tokens_zero_cost(self):
        """Zero tokens costs nothing regardless of model."""
        for model in list(API_PRICE_PER_TOKEN) + ["unknown"]:
            assert token_cost(model, 0) == 0.0

    def test_cost_scales_linearly(self):
        """Doubling tokens doubles cost."""
        c1 = token_cost("claude-sonnet-4", 500)
        c2 = token_cost("claude-sonnet-4", 1000)
        assert c2 == pytest.approx(c1 * 2)

    def test_cheap_model_cheaper_than_expensive(self):
        """gemini-2.0-flash should be much cheaper than claude-opus-4 for same tokens."""
        cheap = token_cost("gemini-2.0-flash", 100_000)
        expensive = token_cost("claude-opus-4", 100_000)
        assert cheap < expensive * 0.1  # at least 10x cheaper

    def test_all_prices_positive(self):
        """Every entry in the pricing table is positive."""
        for model, price in API_PRICE_PER_TOKEN.items():
            assert price > 0, f"{model} has non-positive price"
        assert DEFAULT_PRICE_PER_TOKEN > 0


class TestSubscriptionEntity:
    def test_active_subscription(self):
        """Active subscription has ended_at=None."""
        sub = Subscription(
            subscription_id="s1",
            user_id="alice",
            provider="anthropic",
            plan="Claude Pro",
            monthly_cost_cents=2000,
            started_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        assert sub.ended_at is None
        assert sub.monthly_cost_cents == 2000

    def test_serialization_roundtrip(self):
        """Subscription survives model_dump -> model_validate."""
        original = Subscription(
            subscription_id="s1",
            user_id="bob",
            provider="openai",
            plan="ChatGPT Plus",
            monthly_cost_cents=2000,
            started_at=datetime(2025, 3, 1, tzinfo=UTC),
            ended_at=datetime(2025, 6, 1, tzinfo=UTC),
        )
        rebuilt = Subscription.model_validate(original.model_dump())
        assert rebuilt == original

    def test_currency_defaults_to_usd(self):
        sub = Subscription(
            subscription_id="s1",
            user_id="u",
            provider="p",
            plan="p",
            monthly_cost_cents=100,
            started_at=datetime.now(UTC),
        )
        assert sub.currency == "USD"

    def test_missing_required_field_rejected(self):
        with pytest.raises(ValidationError):
            Subscription(
                subscription_id="s1",
                user_id="u",
                # missing provider, plan, monthly_cost_cents, started_at
            )


class TestSessionValue:
    """Tests for the session_value formula: hourly_rate × log2(event_count) × utility_score."""

    def test_non_work_always_zero(self):
        """Non-work sessions produce zero value regardless of rate or size."""
        assert session_value(100.0, 100, "non_work") == 0.0

    def test_useful_higher_than_trivial(self):
        """Same session classified as useful produces more value than trivial."""
        useful = session_value(50.0, 10, "useful")
        trivial = session_value(50.0, 10, "trivial")
        assert useful == trivial * UTILITY_SCORES["useful"] / UTILITY_SCORES["trivial"]

    def test_value_scales_with_rate(self):
        """Doubling hourly rate doubles value."""
        v1 = session_value(50.0, 10, "useful")
        v2 = session_value(100.0, 10, "useful")
        assert v2 == pytest.approx(v1 * 2)

    def test_log_scaling_with_size(self):
        """Value grows logarithmically with session size, not linearly."""
        v8 = session_value(50.0, 8, "useful")
        v64 = session_value(50.0, 64, "useful")
        # 64 messages is 8x more than 8, but value should be only 2x (log2(64)/log2(8) = 6/3)
        assert v64 == pytest.approx(v8 * 2)

    def test_formula_matches_direct_computation(self):
        """Verify the formula produces hourly_rate × log2(n) × score."""
        rate, n, utility = 75.0, 16, "useful"
        expected = rate * math.log2(n) * UTILITY_SCORES[utility]
        assert session_value(rate, n, utility) == pytest.approx(expected)

    def test_none_utility_zero(self):
        """Unclassified sessions (utility=None) produce zero value."""
        assert session_value(100.0, 10, None) == 0.0

    def test_zero_events_zero_value(self):
        """Empty session produces zero value."""
        assert session_value(100.0, 0, "useful") == 0.0
