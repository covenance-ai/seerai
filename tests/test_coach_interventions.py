"""Tests for coach intervention schema, plausibility, and session API.

Covers:
  - Round-trip of coach_intervention events and counterfactual transcripts
    through the Pydantic models and the Firestore client API.
  - The shipped hero archetype is both loadable and plausibility-clean.
  - CoachInterventionIntegrity detects each class of violation and
    normalization is idempotent on a clean snapshot.
  - GET /api/users/{uid}/sessions/{sid} surfaces counterfactual_events,
    counterfactual_utility, intervention_count, intervention_categories.
"""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from seerai.entities import CoachInterventionMetadata, InlineEvent, Session
from seerai.plausibility import CoachInterventionIntegrity, check_all

# ─── Fixtures ──────────────────────────────────────────────────────────


def _coached_snapshot():
    """Minimal valid snapshot where one session has a coach intervention.

    Mirrors the shape of the shipped hero archetype but small enough to
    inspect. All session-level invariants hold.
    """
    return {
        "users": {
            "alice": {
                "user_id": "alice",
                "last_active": "2026-01-01T00:10:00Z",
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
                "last_event_at": "2026-01-01T00:10:00Z",
                "last_event_type": "ai_message",
                "event_count": 3,
                "utility": "useful",
                "intervention_count": 1,
                "intervention_categories": ["factuality"],
                "counterfactual_utility": "harmful",
                "counterfactual_events": [
                    {
                        "event_id": "cf_u",
                        "event_type": "user_message",
                        "content": "hi",
                        "timestamp": "2026-01-01T00:00:00Z",
                        "metadata": None,
                    },
                    {
                        "event_id": "cf_a",
                        "event_type": "ai_message",
                        "content": "use made_up_api()",
                        "timestamp": "2026-01-01T00:01:00Z",
                        "metadata": {
                            "model": "claude-sonnet-4",
                            "tokens": 40,
                            "latency_ms": 400,
                        },
                    },
                ],
            },
        },
        "users/alice/sessions/s1/events": {
            "e_u": {
                "event_id": "e_u",
                "event_type": "user_message",
                "content": "hi",
                "timestamp": "2026-01-01T00:00:00Z",
                "metadata": None,
            },
            "e_c": {
                "event_id": "e_c",
                "event_type": "coach_intervention",
                "content": "Rewrote hallucinated API.",
                "timestamp": "2026-01-01T00:00:45Z",
                "metadata": {
                    "category": "factuality",
                    "kind": "hallucinated_api",
                    "mode": "rewrite",
                    "severity": 2,
                    "targets_event_id": "e_a",
                    "quoted_span": "made_up_api()",
                    "sources": ["https://example.com/docs"],
                    "accepted": True,
                    "estimated_savings_cents": 1200,
                    "pre_coach_excerpt": "made_up_api()",
                },
            },
            "e_a": {
                "event_id": "e_a",
                "event_type": "ai_message",
                "content": "use real_api()",
                "timestamp": "2026-01-01T00:01:00Z",
                "metadata": {
                    "model": "claude-sonnet-4",
                    "tokens": 60,
                    "latency_ms": 500,
                    "coached": True,
                    "coach_intervention_ids": ["e_c"],
                    "pre_coach_content": "use made_up_api()",
                },
            },
        },
    }


@pytest.fixture
def coached_snapshot():
    return _coached_snapshot()


# ─── Schema round-trip ─────────────────────────────────────────────────


class TestInterventionMetadataRoundTrip:
    """CoachInterventionMetadata validates + round-trips without loss."""

    def test_minimal_metadata_validates(self):
        md = CoachInterventionMetadata(
            category="factuality", kind="hallucinated_api", mode="rewrite"
        )
        assert md.severity == 3  # default
        assert md.estimated_savings_cents == 0

    def test_full_metadata_round_trip(self):
        payload = {
            "category": "sources",
            "kind": "fabricated_citation",
            "mode": "amend",
            "severity": 1,
            "targets_event_id": "evt-123",
            "quoted_span": "Article 47 of GDPR",
            "sources": ["https://example.com"],
            "accepted": True,
            "estimated_savings_cents": 4500,
            "pre_coach_excerpt": "Article 47",
        }
        md = CoachInterventionMetadata.model_validate(payload)
        assert md.model_dump() == payload

    def test_invalid_category_rejected(self):
        with pytest.raises(Exception):
            CoachInterventionMetadata(
                category="not_a_category", kind="hallucinated_api", mode="rewrite"
            )

    def test_invalid_mode_rejected(self):
        with pytest.raises(Exception):
            CoachInterventionMetadata(
                category="factuality", kind="hallucinated_api", mode="sneak"
            )


class TestInlineEventRoundTrip:
    """InlineEvent accepts coach events and preserves metadata as-is."""

    def test_coach_intervention_fits_inline_event(self):
        ev = InlineEvent(
            event_id="e1",
            event_type="coach_intervention",
            content="rewrite",
            timestamp="2026-01-01T00:00:00Z",
            metadata={"category": "factuality"},
        )
        assert ev.event_type == "coach_intervention"

    def test_inline_event_round_trip(self):
        src = {
            "event_id": "e1",
            "event_type": "ai_message",
            "content": "hi",
            "timestamp": "2026-01-01T00:00:00Z",
            "metadata": {"model": "claude-sonnet-4", "coached": True},
        }
        ev = InlineEvent.model_validate(src)
        # model_dump serializes timestamp back to datetime; compare semantic shape
        d = ev.model_dump()
        assert d["event_id"] == "e1"
        assert d["metadata"] == src["metadata"]


# ─── Hero archetype is loadable + clean ────────────────────────────────


class TestHeroArchetype:
    """The committed hero session passes schema + plausibility checks.

    Uses the real local snapshot — regression test for any future
    refactor that would silently break the shipped demo data.
    """

    HERO_UID = "bob.martinez"
    HERO_SID = "coach-hero-factuality-fast-merge"

    def test_hero_session_loads(self, local_snapshot):
        s = Session.get(self.HERO_SID, parent_path=f"users/{self.HERO_UID}")
        assert s is not None
        assert s.intervention_count == 1
        assert s.intervention_categories == ["factuality"]
        assert s.counterfactual_utility == "harmful"
        assert s.counterfactual_events is not None
        assert len(s.counterfactual_events) >= 4

    def test_hero_passes_all_plausibility_checks(self, local_snapshot):
        """Whole snapshot, including hero, must be violation-free."""
        assert check_all(local_snapshot) == []


@pytest.fixture
def local_snapshot():
    """Load the committed snapshot for hero-archetype assertions."""
    import json
    from pathlib import Path

    path = Path(__file__).parent.parent / "data" / "snapshot.json"
    return json.loads(path.read_text())


# ─── Plausibility: CoachInterventionIntegrity ─────────────────────────


class TestIntegrityCheckDetects:
    """Each class of violation is detected."""

    def test_clean_snapshot_no_violations(self, coached_snapshot):
        assert CoachInterventionIntegrity().violations(coached_snapshot) == []

    def test_invalid_category(self, coached_snapshot):
        data = deepcopy(coached_snapshot)
        data["users/alice/sessions/s1/events"]["e_c"]["metadata"]["category"] = "bogus"
        v = CoachInterventionIntegrity().violations(data)
        assert any("invalid category" in str(x) for x in v)

    def test_invalid_mode(self, coached_snapshot):
        data = deepcopy(coached_snapshot)
        data["users/alice/sessions/s1/events"]["e_c"]["metadata"]["mode"] = "sneak"
        v = CoachInterventionIntegrity().violations(data)
        assert any("invalid mode" in str(x) for x in v)

    def test_missing_category(self, coached_snapshot):
        data = deepcopy(coached_snapshot)
        del data["users/alice/sessions/s1/events"]["e_c"]["metadata"]["category"]
        v = CoachInterventionIntegrity().violations(data)
        assert any("missing metadata.category" in str(x) for x in v)

    def test_targets_missing_event(self, coached_snapshot):
        data = deepcopy(coached_snapshot)
        data["users/alice/sessions/s1/events"]["e_c"]["metadata"][
            "targets_event_id"
        ] = "no_such"
        v = CoachInterventionIntegrity().violations(data)
        assert any("not in session" in str(x) for x in v)

    def test_stale_intervention_count_detected(self, coached_snapshot):
        data = deepcopy(coached_snapshot)
        data["users/alice/sessions"]["s1"]["intervention_count"] = 5
        v = CoachInterventionIntegrity().violations(data)
        assert any("intervention_count=5" in str(x) for x in v)

    def test_counterfactual_without_interventions(self, coached_snapshot):
        data = deepcopy(coached_snapshot)
        # Drop the coach event but keep counterfactual fields — orphan state.
        del data["users/alice/sessions/s1/events"]["e_c"]
        data["users/alice/sessions"]["s1"]["intervention_count"] = 0
        v = CoachInterventionIntegrity().violations(data)
        assert any("counterfactual_events without interventions" in str(x) for x in v)

    def test_interventions_without_counterfactual(self, coached_snapshot):
        data = deepcopy(coached_snapshot)
        data["users/alice/sessions"]["s1"]["counterfactual_events"] = None
        data["users/alice/sessions"]["s1"]["counterfactual_utility"] = None
        v = CoachInterventionIntegrity().violations(data)
        assert any("coached but no counterfactual_events" in str(x) for x in v)

    def test_counterfactual_events_without_utility(self, coached_snapshot):
        data = deepcopy(coached_snapshot)
        data["users/alice/sessions"]["s1"]["counterfactual_utility"] = None
        v = CoachInterventionIntegrity().violations(data)
        assert any("without counterfactual_utility" in str(x) for x in v)


class TestIntegrityNormalization:
    """Normalization fixes auto-fixable state and is idempotent on clean data."""

    def test_rebuilds_intervention_count(self, coached_snapshot):
        data = deepcopy(coached_snapshot)
        data["users/alice/sessions"]["s1"]["intervention_count"] = 99
        CoachInterventionIntegrity().normalize(data)
        assert data["users/alice/sessions"]["s1"]["intervention_count"] == 1

    def test_rebuilds_categories(self, coached_snapshot):
        data = deepcopy(coached_snapshot)
        data["users/alice/sessions"]["s1"]["intervention_categories"] = None
        CoachInterventionIntegrity().normalize(data)
        assert data["users/alice/sessions"]["s1"]["intervention_categories"] == [
            "factuality"
        ]

    def test_clears_orphan_counterfactual_on_uncoached_session(self, coached_snapshot):
        data = deepcopy(coached_snapshot)
        # Remove the coach event; session is now uncoached but still has counterfactual.
        del data["users/alice/sessions/s1/events"]["e_c"]
        data["users/alice/sessions"]["s1"]["intervention_count"] = 1  # lying

        CoachInterventionIntegrity().normalize(data)

        sess = data["users/alice/sessions"]["s1"]
        assert sess["intervention_count"] == 0
        assert sess["counterfactual_events"] is None
        assert sess["counterfactual_utility"] is None

    def test_normalize_is_idempotent_on_clean_data(self, coached_snapshot):
        data = deepcopy(coached_snapshot)
        # One full pass brings the snapshot into normal form.
        CoachInterventionIntegrity().normalize(data)
        # A second pass should find nothing to do.
        before = deepcopy(data)
        CoachInterventionIntegrity().normalize(data)
        assert data == before


# ─── Session detail API exposes counterfactual surface ────────────────


class TestSessionDetailAPI:
    def test_coached_session_surfaces_counterfactual(self):
        from main import app

        client = TestClient(app)
        r = client.get(
            "/api/users/bob.martinez/sessions/coach-hero-factuality-fast-merge"
        )
        assert r.status_code == 200
        d = r.json()

        assert d["intervention_count"] == 1
        assert d["intervention_categories"] == ["factuality"]
        assert d["counterfactual_utility"] == "harmful"
        assert d["counterfactual_events"] is not None
        assert len(d["counterfactual_events"]) > len(d["events"]) - 2  # spiral

        # Coach event targets an AI event in the same session; that AI event
        # carries the pre_coach_content so the diff panel has data.
        coach = next(e for e in d["events"] if e["event_type"] == "coach_intervention")
        target_id = coach["metadata"]["targets_event_id"]
        target = next(e for e in d["events"] if e["event_id"] == target_id)
        assert target["event_type"] == "ai_message"
        assert target["metadata"]["coached"] is True
        assert target["metadata"]["pre_coach_content"]

    def test_uncoached_session_has_no_counterfactual(self):
        from main import app

        client = TestClient(app)
        # Use any other session from the snapshot that has no coach.
        r = client.get("/api/users")
        assert r.status_code == 200
        # Find a session that isn't the hero and has no intervention flags.
        # We rely on list_sessions; any ordinary user's first session works.
        sessions = client.get("/api/users/carol.chen/sessions").json()
        # Pick one that doesn't have intervention metadata (any regular session).
        uncoached = next(s for s in sessions if not s.get("intervention_count"))
        r = client.get(f"/api/users/carol.chen/sessions/{uncoached['session_id']}")
        assert r.status_code == 200
        d = r.json()
        assert d["intervention_count"] == 0
        assert d["counterfactual_events"] is None
        assert d["counterfactual_utility"] is None
