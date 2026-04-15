"""Insights endpoint tests — dismiss/restore round-trip and archived filter.

Backed by the local JSON store on a tmp snapshot so writes persist for the
duration of a single test, exercising the same code path as production
(load → mutate → sync → reload).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from seerai import firestore_client as fc


def _seed_snapshot(path: Path) -> dict:
    """Write a minimal snapshot with two insights, return the payload."""
    now = datetime.now(UTC).isoformat()
    data = {
        "orgs": {
            "acme": {
                "org_id": "acme",
                "name": "Acme",
                "parent_id": None,
                "path": ["acme"],
                "depth": 0,
            },
        },
        "insights": {
            "i1": {
                "insight_id": "i1",
                "kind": "above_paygrade",
                "priority": 2,
                "created_at": now,
                "title": "Active insight",
                "description": "...",
                "user_id": "alice",
                "org_id": "acme",
                "target_org_id": None,
                "evidence_session_ids": [],
                "dismissed_at": None,
            },
            "i2": {
                "insight_id": "i2",
                "kind": "below_paygrade",
                "priority": 3,
                "created_at": now,
                "title": "Already archived",
                "description": "...",
                "user_id": "bob",
                "org_id": "acme",
                "target_org_id": None,
                "evidence_session_ids": [],
                "dismissed_at": now,
            },
        },
    }
    path.write_text(json.dumps(data, indent=2))
    return data


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


class TestArchivedFilter:
    def test_default_returns_only_active(self, client):
        """GET /api/insights without archived flag excludes dismissed ones."""
        resp = client.get("/api/insights")
        assert resp.status_code == 200
        ids = {i["insight_id"] for i in resp.json()}
        assert ids == {"i1"}

    def test_archived_true_returns_only_dismissed(self, client):
        """archived=true returns only dismissed insights."""
        resp = client.get("/api/insights?archived=true")
        assert resp.status_code == 200
        ids = {i["insight_id"] for i in resp.json()}
        assert ids == {"i2"}

    def test_active_and_archived_partition_full_set(self, client):
        """Active ∪ Archived = all insights, with no overlap."""
        active = {i["insight_id"] for i in client.get("/api/insights").json()}
        archived = {
            i["insight_id"]
            for i in client.get("/api/insights?archived=true").json()
        }
        assert active.isdisjoint(archived)
        assert active | archived == {"i1", "i2"}


class TestDismissRestore:
    def test_dismiss_moves_to_archived(self, client):
        """Dismissing an active insight removes it from active and adds to archived."""
        resp = client.post("/api/insights/i1/dismiss")
        assert resp.status_code == 200
        body = resp.json()
        assert body["dismissed_at"] is not None

        active_ids = {i["insight_id"] for i in client.get("/api/insights").json()}
        archived_ids = {
            i["insight_id"]
            for i in client.get("/api/insights?archived=true").json()
        }
        assert "i1" not in active_ids
        assert "i1" in archived_ids

    def test_restore_moves_back_to_active(self, client):
        """Restoring a dismissed insight returns it to the active list."""
        resp = client.post("/api/insights/i2/restore")
        assert resp.status_code == 200
        assert resp.json()["dismissed_at"] is None

        active_ids = {i["insight_id"] for i in client.get("/api/insights").json()}
        assert "i2" in active_ids

    def test_dismiss_then_restore_roundtrip(self, client):
        """Dismiss → restore returns the insight to its original state."""
        client.post("/api/insights/i1/dismiss")
        client.post("/api/insights/i1/restore")
        resp = client.get("/api/insights")
        active = {i["insight_id"]: i for i in resp.json()}
        assert "i1" in active
        assert active["i1"]["dismissed_at"] is None

    def test_dismiss_is_idempotent(self, client):
        """Dismissing twice keeps the original timestamp (does not bump it)."""
        first = client.post("/api/insights/i1/dismiss").json()["dismissed_at"]
        second = client.post("/api/insights/i1/dismiss").json()["dismissed_at"]
        assert first == second

    def test_dismiss_unknown_id_returns_404(self, client):
        resp = client.post("/api/insights/does-not-exist/dismiss")
        assert resp.status_code == 404


class TestUserAndOrgFilter:
    def test_user_filter_isolates_one_user(self, client):
        """user_id filter only returns insights about that user."""
        ids = {
            i["insight_id"]
            for i in client.get("/api/insights?user_id=alice").json()
        }
        assert ids == {"i1"}

        # bob's insight is archived, so user_id filter alone returns empty
        # unless archived=true is also passed.
        ids_archived = {
            i["insight_id"]
            for i in client.get("/api/insights?user_id=bob&archived=true").json()
        }
        assert ids_archived == {"i2"}

    def test_user_filter_plus_archived_intersect(self, client):
        """user_id + archived combine via AND, not OR."""
        # alice has only an active insight, so archived view is empty for her.
        resp = client.get("/api/insights?user_id=alice&archived=true")
        assert resp.json() == []
