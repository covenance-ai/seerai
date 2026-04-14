"""Org tree model validation and endpoint tests."""

from unittest.mock import MagicMock, patch

import pytest

from seerai.entities import OrgNode
from seerai.models import OrgNodeStats


class TestOrgNode:
    def test_root_node(self):
        """Root node has depth 0, path contains only itself, no parent."""
        n = OrgNode(org_id="acme", name="Acme Corp", path=["acme"], depth=0)
        assert n.parent_id is None
        assert n.depth == 0
        assert n.path == ["acme"]

    def test_child_node(self):
        """Child node has parent, deeper depth, and path includes ancestors."""
        n = OrgNode(
            org_id="acme-eng",
            name="Engineering",
            parent_id="acme",
            path=["acme", "acme-eng"],
            depth=1,
        )
        assert n.parent_id == "acme"
        assert n.path[0] == "acme"
        assert n.path[-1] == n.org_id

    def test_serialization_roundtrip(self):
        """model_dump -> model_validate preserves all fields."""
        original = OrgNode(
            org_id="x", name="X", parent_id="p", path=["p", "x"], depth=1
        )
        rebuilt = OrgNode.model_validate(original.model_dump())
        assert rebuilt == original


class TestOrgNodeStats:
    def test_defaults_to_zero(self):
        """All counters default to zero."""
        s = OrgNodeStats(org_id="x", name="X", depth=0)
        assert s.user_count == 0
        assert s.session_count == 0
        assert s.message_count == 0
        assert s.error_count == 0

    def test_accepts_counts(self):
        """Explicit counts are preserved."""
        s = OrgNodeStats(
            org_id="x",
            name="X",
            depth=0,
            user_count=5,
            session_count=20,
            message_count=100,
            error_count=3,
        )
        assert s.user_count == 5
        assert s.error_count == 3


class TestOrgEndpoints:
    @pytest.fixture
    def client(self):
        mock_db = MagicMock()
        mock_batch = MagicMock()
        mock_db.batch.return_value = mock_batch

        with patch("seerai.firestore_client._client", mock_db):
            from fastapi.testclient import TestClient

            from main import app

            yield TestClient(app), mock_db

    def test_create_root_org(self, client):
        """POST /api/orgs creates a root node when no parent_id."""
        tc, mock_db = client
        resp = tc.post(
            "/api/orgs",
            json={"org_id": "acme", "name": "Acme Corp"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["org_id"] == "acme"
        assert data["depth"] == 0
        assert data["path"] == ["acme"]
        assert data["parent_id"] is None

    def test_create_child_org(self, client):
        """POST /api/orgs with parent_id computes path and depth from parent."""
        tc, mock_db = client
        # Mock parent document
        parent_doc = MagicMock()
        parent_doc.exists = True
        parent_doc.to_dict.return_value = {
            "org_id": "acme",
            "name": "Acme",
            "path": ["acme"],
            "depth": 0,
            "parent_id": None,
        }
        mock_db.collection.return_value.document.return_value.get.return_value = (
            parent_doc
        )

        resp = tc.post(
            "/api/orgs",
            json={"org_id": "acme-eng", "name": "Engineering", "parent_id": "acme"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["depth"] == 1
        assert data["path"] == ["acme", "acme-eng"]
        assert data["parent_id"] == "acme"

    def test_create_child_org_missing_parent(self, client):
        """POST /api/orgs with nonexistent parent returns 404."""
        tc, mock_db = client
        parent_doc = MagicMock()
        parent_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = (
            parent_doc
        )

        resp = tc.post(
            "/api/orgs",
            json={"org_id": "orphan", "name": "Orphan", "parent_id": "nope"},
        )
        assert resp.status_code == 404

    def test_list_root_orgs(self, client):
        """GET /api/orgs returns root-level (depth=0) nodes."""
        tc, mock_db = client
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "org_id": "acme",
            "name": "Acme Corp",
            "parent_id": None,
            "path": ["acme"],
            "depth": 0,
        }
        mock_db.collection.return_value.where.return_value.stream.return_value = iter(
            [mock_doc]
        )
        resp = tc.get("/api/orgs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["org_id"] == "acme"
