"""Tests for pricing logic, value computation, and cost efficiency models."""

import math
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from seerai.cost.endpoint import (
    DISPLACEMENT_FACTOR,
    UTILITY_HOURS_FACTOR,
    WINDOW_DAYS,
    _user_cost,
    session_value,
)
from seerai.entities import Session, Subscription, User
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
    """Tests for session_value: hourly_rate × log2(events) × hours_factor."""

    def test_non_work_always_zero(self):
        """Non-work sessions produce zero value regardless of rate or size."""
        assert session_value(100.0, 100, "non_work") == 0.0

    def test_useful_higher_than_trivial(self):
        """Same session classified as useful produces more value than trivial."""
        useful = session_value(50.0, 10, "useful")
        trivial = session_value(50.0, 10, "trivial")
        assert useful == trivial * UTILITY_HOURS_FACTOR["useful"] / UTILITY_HOURS_FACTOR["trivial"]

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
        """Positive sessions: rate × log2(n) × hours_factor × displacement."""
        rate, n, utility = 75.0, 16, "useful"
        expected = rate * math.log2(n) * UTILITY_HOURS_FACTOR[utility] * DISPLACEMENT_FACTOR
        assert session_value(rate, n, utility) == pytest.approx(expected)

    def test_realistic_values(self):
        """A useful 2-event session at $100/hr ≈ $12.5 (15 min saved × 0.5 displacement)."""
        val = session_value(100.0, 2, "useful")
        assert val == pytest.approx(100.0 * 1.0 * 0.25 * DISPLACEMENT_FACTOR)
        # 64-event useful session at $100/hr ≈ $75 (1.5 hr × 0.5)
        val64 = session_value(100.0, 64, "useful")
        assert val64 == pytest.approx(100.0 * 6.0 * 0.25 * DISPLACEMENT_FACTOR)

    def test_none_utility_zero(self):
        """Unclassified sessions (utility=None) produce zero value."""
        assert session_value(100.0, 10, None) == 0.0

    def test_zero_events_zero_value(self):
        """Empty session produces zero value."""
        assert session_value(100.0, 0, "useful") == 0.0


class TestHarmfulSessionValue:
    """Harmful sessions (post-hoc QA reclassification) produce negative value
    on the same log2(events) scale — deeper sessions = more cleanup needed.
    Negatives are NOT discounted by DISPLACEMENT_FACTOR: cleanup time is real
    wall-clock time, not a counterfactual estimate."""

    def test_harmful_is_negative(self):
        assert session_value(100.0, 16, "harmful") < 0

    def test_harmful_scales_log_with_size(self):
        """Bigger harmful session = proportionally more wasted time."""
        small = session_value(100.0, 4, "harmful")
        big = session_value(100.0, 64, "harmful")
        # log2(64)/log2(4) = 6/2 = 3
        assert big == pytest.approx(small * 3)

    def test_harmful_undiscounted_vs_useful_discounted(self):
        """For a session where |hours_factor| is similar, harmful damage > useful gain
        (in absolute terms) because positives are discounted but negatives aren't."""
        rate, events = 100.0, 16
        useful_factor = UTILITY_HOURS_FACTOR["useful"]
        harmful_factor = UTILITY_HOURS_FACTOR["harmful"]
        useful = session_value(rate, events, "useful")
        harmful = session_value(rate, events, "harmful")
        # Manual direct check: harmful raw = rate × log2 × |factor|; useful raw same × DF
        assert useful == pytest.approx(rate * math.log2(events) * useful_factor * DISPLACEMENT_FACTOR)
        assert harmful == pytest.approx(rate * math.log2(events) * harmful_factor)
        # The asymmetry is real: harmful is undiscounted
        assert abs(harmful) > useful  # given |harmful_factor| > useful_factor × DF


class TestUserCostWindow:
    """Cost/value/session_count are reported over the trailing WINDOW_DAYS so
    they are apples-to-apples with monthly_subscription. Sessions outside the
    window must not contribute — otherwise ROI would inflate as data ages.
    """

    @staticmethod
    def _user() -> User:
        return User(
            user_id="u1",
            org_id="org1",
            hourly_rate=100.0,
            role="user",
            last_active=datetime.now(UTC),
        )

    @staticmethod
    def _sub() -> Subscription:
        return Subscription(
            subscription_id="s",
            user_id="u1",
            provider="anthropic",
            plan="Claude Pro",
            monthly_cost_cents=2000,
            started_at=datetime.now(UTC) - timedelta(days=365),
        )

    @staticmethod
    def _session(days_ago: float, *, tokens: int = 1000) -> Session:
        return Session(
            session_id=f"sess-{days_ago}",
            user_id="u1",
            last_event_at=datetime.now(UTC) - timedelta(days=days_ago),
            event_count=16,
            utility="useful",
            token_usage={"claude-sonnet-4": tokens},
        )

    def test_sessions_outside_window_excluded(self):
        """Old sessions don't contribute to value, api_equivalent, or session_count."""
        user, sub = self._user(), self._sub()
        recent = self._session(days_ago=5)
        old = self._session(days_ago=WINDOW_DAYS + 5)

        only_recent = _user_cost(user, [recent], [sub])
        with_old = _user_cost(user, [recent, old], [sub])

        assert only_recent.estimated_value == with_old.estimated_value
        assert only_recent.api_equivalent == with_old.api_equivalent
        assert only_recent.session_count == with_old.session_count == 1
        assert only_recent.utility_breakdown == with_old.utility_breakdown

    def test_roi_is_per_month_ratio(self):
        """ROI = monthly value / monthly subscription. Same load over a longer
        history must yield the same ROI as over a shorter one — the metric is
        time-window-invariant on the value side because of the cutoff."""
        user, sub = self._user(), self._sub()
        # Two installations: one user has only recent activity, another also has
        # ancient activity. ROI must be identical.
        recent_only = _user_cost(user, [self._session(days_ago=1)], [sub])
        with_history = _user_cost(
            user,
            [self._session(days_ago=1), self._session(days_ago=180)],
            [sub],
        )
        assert recent_only.roi == with_history.roi

    def test_harmful_session_lowers_total_value(self):
        """Reclassifying a useful session as harmful must strictly decrease total
        estimated value and increase the harmful-bucket count. Regression guard
        for the QA-pass narrative on the cost dashboard."""
        user, sub = self._user(), self._sub()
        useful_only = _user_cost(user, [self._session(days_ago=1)], [sub])
        s = self._session(days_ago=1)
        s.utility = "harmful"
        with_harmful = _user_cost(user, [s], [sub])
        assert with_harmful.estimated_value < useful_only.estimated_value
        assert with_harmful.utility_breakdown.harmful == 1
        assert with_harmful.utility_breakdown.useful == 0
