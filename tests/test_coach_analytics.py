"""Tests for coach analytics aggregations and the /api/coach endpoints.

Property-style coverage: invariants the aggregator must satisfy regardless
of the underlying snapshot, plus contract checks on the HTTP endpoints.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from seerai.coach.analytics import (
    UTILITY_VALUE_CENTS,
    coach_feed,
    coach_summary,
)
from seerai.entities import Session, User

# ─── Aggregation invariants ────────────────────────────────────────────


class TestSummaryInvariants:
    """Properties that must hold for any snapshot."""

    def test_per_category_counts_sum_to_total(self):
        s = coach_summary()
        per_cat = sum(c.interventions for c in s.by_category)
        assert per_cat == s.interventions_total

    def test_per_category_savings_sum_to_total(self):
        s = coach_summary()
        per_cat = sum(c.estimated_savings_cents for c in s.by_category)
        assert per_cat == s.estimated_savings_cents

    def test_accepted_never_exceeds_total(self):
        s = coach_summary()
        assert s.interventions_accepted <= s.interventions_total
        assert 0.0 <= s.acceptance_rate <= 1.0

    def test_value_delta_matches_with_minus_without(self):
        s = coach_summary()
        assert (
            s.value_cents.delta
            == s.value_cents.with_coach - s.value_cents.without_coach
        )

    def test_turns_delta_is_nonnegative(self):
        """Per-session turn savings clamp at zero — delta cannot go negative."""
        s = coach_summary()
        assert s.turns.delta >= 0

    def test_coached_sessions_le_observed(self):
        s = coach_summary()
        assert s.coached_sessions <= s.sessions_observed

    def test_uncoached_sessions_contribute_zero_value_delta(self):
        """Sessions without interventions add equal amounts to both sides."""
        s_all = coach_summary()
        # Filtering to a category drops sessions without that category's
        # interventions from the contribution but keeps every session in
        # the observation count. Per-category filter still counts all
        # sessions, so value_without is unchanged from the all view.
        s_fact = coach_summary(category="factuality")
        assert s_fact.sessions_observed == s_all.sessions_observed
        assert s_fact.value_cents.without_coach == s_all.value_cents.without_coach


class TestUtilityShifts:
    """Utility-shift entries must reflect actual session deltas in the snapshot."""

    def test_shifts_only_recorded_when_classes_differ(self):
        s = coach_summary()
        for sh in s.utility_shifts:
            assert sh.from_class != sh.to_class
            assert sh.sessions > 0

    def test_shift_count_matches_per_session_inspection(self):
        """The aggregator's shift counts equal a from-scratch recount."""
        from collections import Counter

        manual: Counter = Counter()
        for u in User.list(order_by=None, limit=0):
            for sess in Session.for_user(u.user_id, limit=0):
                actual = sess.utility or "non_work"
                cf = sess.counterfactual_utility or actual
                if actual != cf:
                    manual[(cf, actual)] += 1

        s = coach_summary()
        agg = {(sh.from_class, sh.to_class): sh.sessions for sh in s.utility_shifts}
        assert agg == dict(manual)


class TestFilterScopes:
    """Filtering to a single user / org / category narrows results correctly."""

    def test_user_filter_restricts_interventions_to_that_user(self):
        s = coach_summary(user_id="bob.martinez")
        feed = coach_feed(user_id="bob.martinez")
        assert all(it.user_id == "bob.martinez" for it in feed)
        assert s.interventions_total == len(feed)

    def test_category_filter_restricts_feed(self):
        feed = coach_feed(category="sources")
        assert all(it.category == "sources" for it in feed)

    def test_unknown_user_yields_zero_results(self):
        s = coach_summary(user_id="not-a-user")
        assert s.sessions_observed == 0
        assert s.interventions_total == 0


class TestValuationPriors:
    """Value priors must produce a sensible ordering of utility classes."""

    def test_useful_outranks_harmful(self):
        assert UTILITY_VALUE_CENTS["useful"] > UTILITY_VALUE_CENTS["harmful"]

    def test_harmful_is_negative(self):
        assert UTILITY_VALUE_CENTS["harmful"] < 0


# ─── Endpoint contract ─────────────────────────────────────────────────


class TestCoachEndpoints:
    def setup_method(self):
        self.client = TestClient(app)

    def test_summary_endpoint_returns_expected_shape(self):
        r = self.client.get("/api/coach/summary")
        assert r.status_code == 200
        d = r.json()
        for key in (
            "sessions_observed",
            "coached_sessions",
            "interventions_total",
            "interventions_accepted",
            "acceptance_rate",
            "estimated_savings_cents",
            "by_category",
            "by_kind",
            "by_mode",
            "utility_distribution_with",
            "utility_distribution_without",
            "utility_shifts",
            "value_cents",
            "turns",
        ):
            assert key in d, f"missing key {key}"
        for sub in ("without_coach", "with_coach", "delta"):
            assert sub in d["value_cents"]
            assert sub in d["turns"]

    def test_feed_endpoint_returns_items_newest_first(self):
        r = self.client.get("/api/coach/feed?limit=20")
        assert r.status_code == 200
        items = r.json()
        if len(items) >= 2:
            timestamps = [it["timestamp"] for it in items]
            assert timestamps == sorted(timestamps, reverse=True)

    def test_feed_limit_caps_results(self):
        r = self.client.get("/api/coach/feed?limit=2")
        assert r.status_code == 200
        assert len(r.json()) <= 2

    def test_invalid_category_rejected(self):
        r = self.client.get("/api/coach/summary?category=bogus")
        assert r.status_code == 422

    def test_each_hero_appears_in_feed(self):
        """All four shipped hero archetypes must surface in the unfiltered feed."""
        r = self.client.get("/api/coach/feed?limit=200")
        kinds = {it["kind"] for it in r.json()}
        assert {
            "hallucinated_api",
            "off_track",
            "fabricated_citation",
            "pii_leak",
        } <= kinds


class TestCoachPageServes:
    def test_coach_dashboard_page_returns_html(self):
        client = TestClient(app)
        r = client.get("/exec/coach")
        assert r.status_code == 200
        # Sanity markers — the page references the coach API and category
        # filter chips. Catches accidental fallthrough to /exec/{org_id}.
        body = r.text
        assert "/api/coach/summary" in body
        assert 'data-filter="factuality"' in body
