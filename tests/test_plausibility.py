"""Tests for plausibility checks and normalization.

Each test constructs a minimal snapshot with a known violation,
verifies detection, verifies fix, and checks that normalize is idempotent.
"""

import json

from seerai.plausibility import (
    EventModelMatchesProvider,
    MinEventCount,
    ProviderMatch,
    SessionEndsOnAI,
    SessionStartsWithUser,
    SingleModelPerSession,
    SubscriptionCoverage,
    check_all,
    normalize_all,
)


def _base_snapshot():
    """Minimal valid snapshot with zero violations."""
    return {
        "users": {
            "alice": {
                "user_id": "alice",
                "last_active": "2026-01-01T00:00:00Z",
                "org_id": "eng",
            },
        },
        "subscriptions": {
            "sub1": {
                "subscription_id": "sub1",
                "user_id": "alice",
                "provider": "anthropic",
                "plan": "Claude Pro",
                "monthly_cost_cents": 2000,
                "currency": "USD",
                "started_at": "2025-06-01T00:00:00Z",
                "ended_at": None,
            },
        },
        "users/alice/sessions": {
            "s1": {
                "session_id": "s1",
                "user_id": "alice",
                "provider": "anthropic",
                "platform": "vscode",
                "last_event_at": "2026-01-01T00:03:00Z",
                "last_event_type": "ai_message",
                "event_count": 4,
            },
        },
        "users/alice/sessions/s1/events": {
            "e1": {
                "event_id": "e1",
                "event_type": "user_message",
                "content": "hi",
                "timestamp": "2026-01-01T00:00:00Z",
                "metadata": None,
            },
            "e2": {
                "event_id": "e2",
                "event_type": "ai_message",
                "content": "hello",
                "timestamp": "2026-01-01T00:01:00Z",
                "metadata": {
                    "model": "claude-sonnet-4",
                    "tokens": 100,
                    "latency_ms": 500,
                },
            },
            "e3": {
                "event_id": "e3",
                "event_type": "user_message",
                "content": "thanks",
                "timestamp": "2026-01-01T00:02:00Z",
                "metadata": None,
            },
            "e4": {
                "event_id": "e4",
                "event_type": "ai_message",
                "content": "welcome",
                "timestamp": "2026-01-01T00:03:00Z",
                "metadata": {
                    "model": "claude-sonnet-4",
                    "tokens": 80,
                    "latency_ms": 400,
                },
            },
        },
    }


class TestBaseSnapshotIsClean:
    """Sanity: the base fixture itself should have zero violations."""

    def test_no_violations(self):
        assert check_all(_base_snapshot()) == []


class TestSubscriptionCoverage:
    """Users with sessions must have subscriptions."""

    def _add_bob_no_sub(self, data):
        data["users"]["bob"] = {
            "user_id": "bob",
            "last_active": "2026-01-01T00:00:00Z",
        }
        data["users/bob/sessions"] = {
            "s2": {
                "session_id": "s2",
                "user_id": "bob",
                "provider": "openai",
                "last_event_at": "2026-01-01T00:05:00Z",
                "last_event_type": "ai_message",
                "event_count": 4,
            },
        }

    def test_detects_missing_subscription(self):
        data = _base_snapshot()
        self._add_bob_no_sub(data)
        violations = SubscriptionCoverage().violations(data)
        assert len(violations) == 1
        assert "bob" in violations[0].path

    def test_normalize_adds_subscription_matching_usage(self):
        """Normalize should add a subscription for the provider bob actually uses."""
        data = _base_snapshot()
        self._add_bob_no_sub(data)
        SubscriptionCoverage().normalize(data)
        bob_subs = [s for s in data["subscriptions"].values() if s["user_id"] == "bob"]
        assert len(bob_subs) >= 1
        assert any(s["provider"] == "openai" for s in bob_subs)


class TestProviderMatch:
    """Session provider must match user's subscriptions."""

    def test_detects_mismatch(self):
        data = _base_snapshot()
        data["users/alice/sessions"]["s1"]["provider"] = "openai"
        assert len(ProviderMatch().violations(data)) == 1

    def test_normalize_reassigns_to_subscribed_provider(self):
        data = _base_snapshot()
        data["users/alice/sessions"]["s1"]["provider"] = "openai"
        ProviderMatch().normalize(data)
        assert data["users/alice/sessions"]["s1"]["provider"] == "anthropic"

    def test_normalize_fixes_event_models_too(self):
        """When provider changes, event models must follow."""
        data = _base_snapshot()
        data["users/alice/sessions"]["s1"]["provider"] = "openai"
        data["users/alice/sessions/s1/events"]["e2"]["metadata"]["model"] = "gpt-4o"
        ProviderMatch().normalize(data)
        model = data["users/alice/sessions/s1/events"]["e2"]["metadata"]["model"]
        assert model in {"claude-sonnet-4", "claude-haiku-4"}


class TestSessionEndsOnAI:
    """Sessions must not end on user_message."""

    def test_detects_trailing_user_message(self):
        data = _base_snapshot()
        data["users/alice/sessions/s1/events"]["e5"] = {
            "event_id": "e5",
            "event_type": "user_message",
            "content": "one more",
            "timestamp": "2026-01-01T00:10:00Z",
            "metadata": None,
        }
        assert len(SessionEndsOnAI().violations(data)) == 1

    def test_normalize_removes_trailing_user_message(self):
        data = _base_snapshot()
        data["users/alice/sessions/s1/events"]["e5"] = {
            "event_id": "e5",
            "event_type": "user_message",
            "content": "one more",
            "timestamp": "2026-01-01T00:10:00Z",
            "metadata": None,
        }
        SessionEndsOnAI().normalize(data)
        assert "e5" not in data["users/alice/sessions/s1/events"]
        assert data["users/alice/sessions"]["s1"]["last_event_type"] == "ai_message"
        assert data["users/alice/sessions"]["s1"]["event_count"] == 4

    def test_detects_stub_ending_on_user(self):
        data = _base_snapshot()
        del data["users/alice/sessions/s1/events"]
        data["users/alice/sessions"]["s1"]["last_event_type"] = "user_message"
        assert len(SessionEndsOnAI().violations(data)) == 1

    def test_normalize_fixes_stub(self):
        data = _base_snapshot()
        del data["users/alice/sessions/s1/events"]
        data["users/alice/sessions"]["s1"]["last_event_type"] = "user_message"
        SessionEndsOnAI().normalize(data)
        assert data["users/alice/sessions"]["s1"]["last_event_type"] == "ai_message"


class TestSessionStartsWithUser:
    """First event must be user_message."""

    def test_detects_ai_first(self):
        data = _base_snapshot()
        data["users/alice/sessions/s1/events"]["e1"]["event_type"] = "ai_message"
        data["users/alice/sessions/s1/events"]["e1"]["metadata"] = {
            "model": "claude-sonnet-4",
            "tokens": 50,
            "latency_ms": 300,
        }
        assert len(SessionStartsWithUser().violations(data)) == 1

    def test_normalize_drops_leading_non_user_events(self):
        """e1→ai, e2=ai, e3=user, e4=ai → drops e1 AND e2, leaving 2 events."""
        data = _base_snapshot()
        data["users/alice/sessions/s1/events"]["e1"]["event_type"] = "ai_message"
        data["users/alice/sessions/s1/events"]["e1"]["metadata"] = {
            "model": "claude-sonnet-4",
            "tokens": 50,
            "latency_ms": 300,
        }
        SessionStartsWithUser().normalize(data)
        assert "e1" not in data["users/alice/sessions/s1/events"]
        assert "e2" not in data["users/alice/sessions/s1/events"]
        assert data["users/alice/sessions"]["s1"]["event_count"] == 2


class TestSingleModelPerSession:
    """All AI events in a session must use the same model."""

    def test_detects_mixed_models(self):
        data = _base_snapshot()
        data["users/alice/sessions/s1/events"]["e4"]["metadata"]["model"] = (
            "claude-haiku-4"
        )
        assert len(SingleModelPerSession().violations(data)) == 1

    def test_normalize_picks_most_common(self):
        """With 2 sonnet events and 1 haiku, sonnet wins."""
        data = _base_snapshot()
        data["users/alice/sessions/s1/events"]["e4"]["metadata"]["model"] = (
            "claude-haiku-4"
        )
        # e2 = sonnet, e4 = haiku → add a third AI event as sonnet to get 2:1
        data["users/alice/sessions/s1/events"]["e6"] = {
            "event_id": "e6",
            "event_type": "ai_message",
            "content": "more",
            "timestamp": "2026-01-01T00:04:00Z",
            "metadata": {
                "model": "claude-sonnet-4",
                "tokens": 60,
                "latency_ms": 350,
            },
        }
        SingleModelPerSession().normalize(data)
        models = {
            e["metadata"]["model"]
            for e in data["users/alice/sessions/s1/events"].values()
            if e.get("metadata") and "model" in e["metadata"]
        }
        assert models == {"claude-sonnet-4"}


class TestMinEventCount:
    """Sessions must have at least 2 events."""

    def test_detects_low_count(self):
        data = _base_snapshot()
        data["users/alice/sessions"]["s1"]["event_count"] = 1
        assert len(MinEventCount().violations(data)) == 1

    def test_normalize_deletes_session_and_events(self):
        data = _base_snapshot()
        data["users/alice/sessions"]["s1"]["event_count"] = 1
        MinEventCount().normalize(data)
        assert "s1" not in data["users/alice/sessions"]
        assert "users/alice/sessions/s1/events" not in data


class TestEventModelMatchesProvider:
    """Event model must belong to the session's provider."""

    def test_detects_wrong_model(self):
        data = _base_snapshot()
        data["users/alice/sessions/s1/events"]["e2"]["metadata"]["model"] = "gpt-4o"
        assert len(EventModelMatchesProvider().violations(data)) == 1

    def test_normalize_assigns_valid_model(self):
        data = _base_snapshot()
        data["users/alice/sessions/s1/events"]["e2"]["metadata"]["model"] = "gpt-4o"
        EventModelMatchesProvider().normalize(data)
        model = data["users/alice/sessions/s1/events"]["e2"]["metadata"]["model"]
        assert model in {"claude-sonnet-4", "claude-haiku-4"}


class TestNormalizeIdempotent:
    """Running normalize twice must produce identical data."""

    def test_idempotent(self):
        data = _base_snapshot()
        data["users/alice/sessions"]["s1"]["provider"] = "openai"
        data["users/alice/sessions/s1/events"]["e4"]["metadata"]["model"] = "gpt-4o"

        normalize_all(data)
        after_first = json.dumps(data, sort_keys=True)
        normalize_all(data)
        after_second = json.dumps(data, sort_keys=True)
        assert after_first == after_second


class TestFullPipeline:
    """normalize_all should leave zero violations for any combination."""

    def test_clean_after_normalize(self):
        """Bob: no subscription, session ends on user, wrong model for provider."""
        data = _base_snapshot()
        data["users"]["bob"] = {
            "user_id": "bob",
            "last_active": "2026-01-01T00:00:00Z",
        }
        data["users/bob/sessions"] = {
            "s2": {
                "session_id": "s2",
                "user_id": "bob",
                "provider": "mistral",
                "last_event_at": "2026-01-01T00:02:00Z",
                "last_event_type": "user_message",
                "event_count": 3,
            },
        }
        data["users/bob/sessions/s2/events"] = {
            "e10": {
                "event_id": "e10",
                "event_type": "user_message",
                "content": "hi",
                "timestamp": "2026-01-01T00:00:00Z",
                "metadata": None,
            },
            "e11": {
                "event_id": "e11",
                "event_type": "ai_message",
                "content": "yo",
                "timestamp": "2026-01-01T00:01:00Z",
                "metadata": {"model": "gpt-4o", "tokens": 50, "latency_ms": 200},
            },
            "e12": {
                "event_id": "e12",
                "event_type": "user_message",
                "content": "bye",
                "timestamp": "2026-01-01T00:02:00Z",
                "metadata": None,
            },
        }
        normalize_all(data)
        remaining = check_all(data)
        assert remaining == [], f"Remaining violations: {remaining}"
