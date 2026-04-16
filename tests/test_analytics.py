"""Tests for the /api/analytics/org endpoint.

Strategy: seed a tiny local snapshot, hit the HTTP endpoint, check invariants
that must hold regardless of the particular mock data:

- sums across departments == org totals
- weekly + hour×weekday cover the same sessions they should
- users array has rows consistent with department rollups
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from seerai import firestore_client as fc


def _seed_snapshot(path: Path) -> None:
    """Minimal two-department snapshot exercising all chart slices.

    Acme → Eng (alice useful + trivial), Sales (bob useful in harmful + non_work).
    Timestamps span recent days so they hit both the 30d value window and the
    13-week trend window.
    """
    now = datetime.now(UTC)

    def days_ago(n: int) -> str:
        return (now - timedelta(days=n)).isoformat()

    data = {
        "orgs": {
            "acme": {
                "org_id": "acme",
                "name": "Acme",
                "parent_id": None,
                "path": ["acme"],
                "depth": 0,
            },
            "acme-eng": {
                "org_id": "acme-eng",
                "name": "Eng",
                "parent_id": "acme",
                "path": ["acme", "acme-eng"],
                "depth": 1,
            },
            "acme-sal": {
                "org_id": "acme-sal",
                "name": "Sales",
                "parent_id": "acme",
                "path": ["acme", "acme-sal"],
                "depth": 1,
            },
        },
        "users": {
            "alice": {
                "user_id": "alice",
                "last_active": days_ago(1),
                "org_id": "acme-eng",
                "role": "user",
                "hourly_rate": 100.0,
            },
            "bob": {
                "user_id": "bob",
                "last_active": days_ago(1),
                "org_id": "acme-sal",
                "role": "user",
                "hourly_rate": 50.0,
            },
        },
        "subscriptions": {
            "s1": {
                "subscription_id": "s1",
                "user_id": "alice",
                "provider": "anthropic",
                "plan": "Claude Pro",
                "monthly_cost_cents": 2000,
                "currency": "USD",
                "started_at": days_ago(60),
                "ended_at": None,
            },
            "s2": {
                "subscription_id": "s2",
                "user_id": "bob",
                "provider": "openai",
                "plan": "ChatGPT Plus",
                "monthly_cost_cents": 2000,
                "currency": "USD",
                "started_at": days_ago(60),
                "ended_at": None,
            },
        },
        # Sessions inside 30d window, with varied utility / provider / time.
        "users/alice/sessions": {
            "a1": {
                "session_id": "a1",
                "user_id": "alice",
                "last_event_at": days_ago(2),
                "event_count": 16,
                "error_count": 0,
                "provider": "anthropic",
                "utility": "useful",
                "last_event_type": "ai_message",
            },
            "a2": {
                "session_id": "a2",
                "user_id": "alice",
                "last_event_at": days_ago(10),
                "event_count": 8,
                "error_count": 0,
                "provider": "anthropic",
                "utility": "trivial",
                "last_event_type": "ai_message",
            },
            "a3": {
                "session_id": "a3",
                "user_id": "alice",
                "last_event_at": days_ago(20),
                "event_count": 4,
                "error_count": 0,
                "provider": "openai",
                "utility": "useful",
                "last_event_type": "ai_message",
            },
        },
        "users/bob/sessions": {
            "b1": {
                "session_id": "b1",
                "user_id": "bob",
                "last_event_at": days_ago(3),
                "event_count": 8,
                "error_count": 0,
                "provider": "openai",
                "utility": "non_work",
                "last_event_type": "ai_message",
            },
            "b2": {
                "session_id": "b2",
                "user_id": "bob",
                "last_event_at": days_ago(5),
                "event_count": 16,
                "error_count": 0,
                "provider": "openai",
                "utility": "harmful",
                "last_event_type": "ai_message",
            },
        },
        # Older session for alice — should land in weekly trend but not 30d window.
        "users/alice/sessions/old": {},
    }
    # Add a session from 50 days ago so the 30d vs 91d window distinction is testable.
    data["users/alice/sessions"]["a_old"] = {
        "session_id": "a_old",
        "user_id": "alice",
        "last_event_at": days_ago(50),
        "event_count": 4,
        "error_count": 0,
        "provider": "anthropic",
        "utility": "useful",
        "last_event_type": "ai_message",
    }
    data.pop("users/alice/sessions/old", None)

    path.write_text(json.dumps(data, indent=2))


@pytest.fixture
def client(tmp_path, monkeypatch):
    snap = tmp_path / "snapshot.json"
    _seed_snapshot(snap)
    monkeypatch.setenv("LOCAL_DATA_PATH", str(snap))
    fc._client = None
    fc._source = None
    fc.set_datasource("local")

    from main import app

    yield TestClient(app)

    fc._client = None
    fc._source = None


class TestShape:
    def test_returns_expected_keys(self, client):
        """Response has all slices the frontend expects."""
        r = client.get("/api/analytics/org/acme")
        assert r.status_code == 200
        body = r.json()
        for key in (
            "org_id",
            "org_name",
            "window_days",
            "user_count",
            "active_user_count",
            "session_count",
            "message_count",
            "total_subscription_cost",
            "total_estimated_value",
            "roi",
            "utility",
            "provider_totals",
            "departments",
            "users",
            "weekly",
            "hour_weekday",
        ):
            assert key in body, f"missing key: {key}"

    def test_unknown_org_404s(self, client):
        assert client.get("/api/analytics/org/does-not-exist").status_code == 404

    def test_hour_weekday_is_7x24(self, client):
        body = client.get("/api/analytics/org/acme").json()
        assert len(body["hour_weekday"]) == 7
        assert all(len(row) == 24 for row in body["hour_weekday"])
        assert all(
            isinstance(c, int) and c >= 0 for row in body["hour_weekday"] for c in row
        )


class TestInvariants:
    """Properties that must hold regardless of the mock data particulars."""

    def test_department_totals_sum_to_org_totals(self, client):
        body = client.get("/api/analytics/org/acme").json()
        depts = body["departments"]
        # Session counts sum (30-day window).
        assert sum(d["session_count"] for d in depts) == body["session_count"]
        assert sum(d["message_count"] for d in depts) == body["message_count"]
        assert sum(d["user_count"] for d in depts) == body["user_count"]
        assert sum(d["active_user_count"] for d in depts) == body["active_user_count"]
        # Utility counts sum.
        for k in ("useful", "trivial", "non_work", "harmful", "unclassified"):
            assert sum(d["utility"][k] for d in depts) == body["utility"][k], (
                f"utility '{k}' mismatch"
            )
        # Subscription $ sum.
        assert (
            abs(
                sum(d["subscription_cost"] for d in depts)
                - body["total_subscription_cost"]
            )
            < 0.01
        )
        assert (
            abs(
                sum(d["estimated_value"] for d in depts) - body["total_estimated_value"]
            )
            < 0.01
        )

    def test_provider_counts_sum_consistently(self, client):
        body = client.get("/api/analytics/org/acme").json()
        dept_sum = {}
        for d in body["departments"]:
            for p, n in d["provider_counts"].items():
                dept_sum[p] = dept_sum.get(p, 0) + n
        assert dept_sum == body["provider_totals"]

    def test_user_session_counts_sum_to_org(self, client):
        body = client.get("/api/analytics/org/acme").json()
        assert sum(u["session_count"] for u in body["users"]) == body["session_count"]

    def test_hour_weekday_sum_equals_session_count(self, client):
        body = client.get("/api/analytics/org/acme").json()
        grid_total = sum(c for row in body["hour_weekday"] for c in row)
        assert grid_total == body["session_count"]

    def test_weekly_includes_sessions_older_than_30d(self, client):
        """Trend window is wider than value window — covers ~13 weeks."""
        body = client.get("/api/analytics/org/acme").json()
        weekly_total = sum(
            w["useful"]
            + w["trivial"]
            + w["non_work"]
            + w["harmful"]
            + w["unclassified"]
            for w in body["weekly"]
        )
        # 5 recent + 1 older session = 6; confirm trend picks up the older one too.
        assert weekly_total >= body["session_count"]
        assert weekly_total == 6

    def test_users_sorted_by_value_desc(self, client):
        body = client.get("/api/analytics/org/acme").json()
        values = [u["estimated_value"] for u in body["users"]]
        assert values == sorted(values, reverse=True)

    def test_roi_matches_value_over_cost(self, client):
        body = client.get("/api/analytics/org/acme").json()
        # Spot-check alice: both her subs = $20/mo, value is positive.
        alice = next(u for u in body["users"] if u["user_id"] == "alice")
        assert alice["subscription_cost"] == 20.0
        assert alice["roi"] == pytest.approx(alice["estimated_value"] / 20.0, rel=0.01)

    def test_active_user_count_matches_users_with_sessions(self, client):
        body = client.get("/api/analytics/org/acme").json()
        active = sum(1 for u in body["users"] if u["session_count"] > 0)
        assert active == body["active_user_count"]


class TestClassification:
    def test_harmful_session_included(self, client):
        """Bob has one 'harmful' session — must be counted in org + dept + user."""
        body = client.get("/api/analytics/org/acme").json()
        assert body["utility"]["harmful"] == 1
        sales = next(d for d in body["departments"] if d["org_id"] == "acme-sal")
        assert sales["utility"]["harmful"] == 1
        bob = next(u for u in body["users"] if u["user_id"] == "bob")
        assert bob["harmful_count"] == 1

    def test_useful_session_value_is_positive(self, client):
        body = client.get("/api/analytics/org/acme").json()
        alice = next(u for u in body["users"] if u["user_id"] == "alice")
        # Two useful sessions at $100/hr → value should be > 0.
        assert alice["estimated_value"] > 0
        assert alice["useful_count"] == 2

    def test_harmful_session_value_negative_contribution(self, client):
        """Bob's harmful session dominates his one non-work (0-value) session."""
        body = client.get("/api/analytics/org/acme").json()
        bob = next(u for u in body["users"] if u["user_id"] == "bob")
        assert bob["estimated_value"] < 0

    def test_primary_provider_reflects_session_majority(self, client):
        body = client.get("/api/analytics/org/acme").json()
        alice = next(u for u in body["users"] if u["user_id"] == "alice")
        assert alice["primary_provider"] == "anthropic"  # 2 of 3 windowed sessions
        bob = next(u for u in body["users"] if u["user_id"] == "bob")
        assert bob["primary_provider"] == "openai"


class TestDescendantAggregation:
    """Sub-department users aggregate up to the requested root's direct children."""

    def test_nested_dept_users_roll_up(self, tmp_path, monkeypatch):
        """A user in acme-eng-backend appears under the 'Eng' row when querying 'acme'."""
        snap = tmp_path / "snap.json"
        now = datetime.now(UTC)

        def days_ago(n):
            return (now - timedelta(days=n)).isoformat()

        snap.write_text(
            json.dumps(
                {
                    "orgs": {
                        "acme": {
                            "org_id": "acme",
                            "name": "Acme",
                            "parent_id": None,
                            "path": ["acme"],
                            "depth": 0,
                        },
                        "acme-eng": {
                            "org_id": "acme-eng",
                            "name": "Eng",
                            "parent_id": "acme",
                            "path": ["acme", "acme-eng"],
                            "depth": 1,
                        },
                        "acme-eng-be": {
                            "org_id": "acme-eng-be",
                            "name": "Backend",
                            "parent_id": "acme-eng",
                            "path": ["acme", "acme-eng", "acme-eng-be"],
                            "depth": 2,
                        },
                    },
                    "users": {
                        "deep": {
                            "user_id": "deep",
                            "last_active": days_ago(1),
                            "org_id": "acme-eng-be",
                            "role": "user",
                            "hourly_rate": 100.0,
                        },
                    },
                    "users/deep/sessions": {
                        "d1": {
                            "session_id": "d1",
                            "user_id": "deep",
                            "last_event_at": days_ago(1),
                            "event_count": 8,
                            "error_count": 0,
                            "provider": "anthropic",
                            "utility": "useful",
                            "last_event_type": "ai_message",
                        },
                    },
                }
            )
        )
        monkeypatch.setenv("LOCAL_DATA_PATH", str(snap))
        fc._client = None
        fc._source = None
        fc.set_datasource("local")
        from main import app

        body = TestClient(app).get("/api/analytics/org/acme").json()
        eng = next(d for d in body["departments"] if d["org_id"] == "acme-eng")
        assert eng["user_count"] == 1
        assert eng["session_count"] == 1

        fc._client = None
        fc._source = None


class TestAdoptionRate:
    """Adoption rate (active_user_count / user_count) must be size-invariant.

    Regression test for the dashboard bug where the dept-adoption chart sized
    bars by absolute user_count: a 10-person, 100%-adoption dept rendered 2x
    wider than a 5-person, 100%-adoption dept. The fix keeps the visual on the
    rate; this test pins the API contract the rate is computed from.
    """

    def test_active_per_user_invariant_to_dept_size(self, tmp_path, monkeypatch):
        snap = tmp_path / "snap.json"
        now = datetime.now(UTC)

        def days_ago(n):
            return (now - timedelta(days=n)).isoformat()

        # Two depts: small (2 users) and big (5 users), both at 100% adoption.
        orgs = {
            "acme": {
                "org_id": "acme",
                "name": "Acme",
                "parent_id": None,
                "path": ["acme"],
                "depth": 0,
            },
            "small": {
                "org_id": "small",
                "name": "Small",
                "parent_id": "acme",
                "path": ["acme", "small"],
                "depth": 1,
            },
            "big": {
                "org_id": "big",
                "name": "Big",
                "parent_id": "acme",
                "path": ["acme", "big"],
                "depth": 1,
            },
        }
        users = {}
        sessions: dict[str, dict] = {}

        def add_user(uid: str, dept: str) -> None:
            users[uid] = {
                "user_id": uid,
                "last_active": days_ago(1),
                "org_id": dept,
                "role": "user",
                "hourly_rate": 100.0,
            }
            sessions[f"users/{uid}/sessions"] = {
                f"{uid}_s": {
                    "session_id": f"{uid}_s",
                    "user_id": uid,
                    "last_event_at": days_ago(1),
                    "event_count": 4,
                    "error_count": 0,
                    "provider": "anthropic",
                    "utility": "useful",
                    "last_event_type": "ai_message",
                }
            }

        for uid in ("s1", "s2"):
            add_user(uid, "small")
        for uid in ("b1", "b2", "b3", "b4", "b5"):
            add_user(uid, "big")

        snap.write_text(json.dumps({"orgs": orgs, "users": users, **sessions}))
        monkeypatch.setenv("LOCAL_DATA_PATH", str(snap))
        fc._client = None
        fc._source = None
        fc.set_datasource("local")
        from main import app

        body = TestClient(app).get("/api/analytics/org/acme").json()
        depts = {d["org_id"]: d for d in body["departments"]}

        # Both fully adopted — rate must be 1.0 regardless of headcount.
        for dept_id, expected_total in (("small", 2), ("big", 5)):
            d = depts[dept_id]
            assert d["user_count"] == expected_total
            assert d["active_user_count"] == expected_total
            rate = d["active_user_count"] / d["user_count"]
            assert rate == 1.0, f"{dept_id} rate {rate} != 1.0"

        # The whole point: rates equal across depts of different sizes.
        rate_small = depts["small"]["active_user_count"] / depts["small"]["user_count"]
        rate_big = depts["big"]["active_user_count"] / depts["big"]["user_count"]
        assert rate_small == rate_big

        fc._client = None
        fc._source = None

    def test_partial_adoption_rate_below_one(self, tmp_path, monkeypatch):
        """Half the users active → rate is 0.5, not "5 of 10 vs 2 of 4 = different."""
        snap = tmp_path / "snap.json"
        now = datetime.now(UTC)

        def days_ago(n):
            return (now - timedelta(days=n)).isoformat()

        # Dept with 4 users, 2 of them active in the 30d window.
        users = {
            f"u{i}": {
                "user_id": f"u{i}",
                "last_active": days_ago(1),
                "org_id": "d",
                "role": "user",
                "hourly_rate": 100.0,
            }
            for i in range(4)
        }
        # Only u0 and u1 have a recent session; u2, u3 have none.
        recent_sessions = {
            f"users/u{i}/sessions": {
                f"u{i}_s": {
                    "session_id": f"u{i}_s",
                    "user_id": f"u{i}",
                    "last_event_at": days_ago(1),
                    "event_count": 4,
                    "error_count": 0,
                    "provider": "anthropic",
                    "utility": "useful",
                    "last_event_type": "ai_message",
                }
            }
            for i in (0, 1)
        }

        snap.write_text(
            json.dumps(
                {
                    "orgs": {
                        "acme": {
                            "org_id": "acme",
                            "name": "Acme",
                            "parent_id": None,
                            "path": ["acme"],
                            "depth": 0,
                        },
                        "d": {
                            "org_id": "d",
                            "name": "D",
                            "parent_id": "acme",
                            "path": ["acme", "d"],
                            "depth": 1,
                        },
                    },
                    "users": users,
                    **recent_sessions,
                }
            )
        )
        monkeypatch.setenv("LOCAL_DATA_PATH", str(snap))
        fc._client = None
        fc._source = None
        fc.set_datasource("local")
        from main import app

        body = TestClient(app).get("/api/analytics/org/acme").json()
        d = next(d for d in body["departments"] if d["org_id"] == "d")
        assert d["user_count"] == 4
        assert d["active_user_count"] == 2
        assert d["active_user_count"] / d["user_count"] == 0.5

        fc._client = None
        fc._source = None
