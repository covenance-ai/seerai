"""Ingest endpoint tests with mocked Firestore.

Verifies the FastAPI layer accepts valid payloads, rejects invalid ones,
and that the Firestore batch write structure is correct.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """TestClient with Firestore mocked out via the module-level _client cache."""
    mock_db = MagicMock()
    mock_batch = MagicMock()
    mock_db.batch.return_value = mock_batch

    with patch("seerai.firestore_client._client", mock_db):
        from main import app

        yield TestClient(app), mock_db, mock_batch


class TestIngestEndpoint:
    def test_single_event_returns_stored_event(self, client):
        """POST /api/ingest returns a StoredEvent with generated id and timestamp."""
        tc, _, _ = client
        resp = tc.post(
            "/api/ingest",
            json={
                "user_id": "alice",
                "session_id": "s1",
                "event_type": "user_message",
                "content": "hello world",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "alice"
        assert data["event_id"]  # server-generated
        assert data["timestamp"]  # server-generated

    def test_single_event_commits_batch(self, client):
        """POST /api/ingest commits exactly one Firestore batch."""
        tc, _, mock_batch = client
        tc.post(
            "/api/ingest",
            json={
                "user_id": "bob",
                "session_id": "s2",
                "event_type": "ai_message",
                "content": "hi bob",
            },
        )
        mock_batch.commit.assert_called_once()

    def test_batch_ingest(self, client):
        """POST /api/ingest/batch processes multiple events."""
        tc, _, mock_batch = client
        events = [
            {
                "user_id": "u",
                "session_id": "s",
                "event_type": "user_message",
                "content": f"msg-{i}",
            }
            for i in range(3)
        ]
        resp = tc.post("/api/ingest/batch", json=events)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert mock_batch.commit.call_count == 3

    def test_invalid_event_type_rejected(self, client):
        """Invalid event_type gets a 422 from Pydantic validation."""
        tc, _, _ = client
        resp = tc.post(
            "/api/ingest",
            json={
                "user_id": "u",
                "session_id": "s",
                "event_type": "invalid",
                "content": "x",
            },
        )
        assert resp.status_code == 422

    def test_missing_content_rejected(self, client):
        """Missing required field gets a 422."""
        tc, _, _ = client
        resp = tc.post(
            "/api/ingest",
            json={
                "user_id": "u",
                "session_id": "s",
                "event_type": "error",
            },
        )
        assert resp.status_code == 422

    def test_metadata_passthrough(self, client):
        """Metadata dict is preserved in the response."""
        tc, _, _ = client
        resp = tc.post(
            "/api/ingest",
            json={
                "user_id": "u",
                "session_id": "s",
                "event_type": "ai_message",
                "content": "response",
                "metadata": {"model": "claude-3", "tokens": 150},
            },
        )
        data = resp.json()
        assert data["metadata"]["model"] == "claude-3"
        assert data["metadata"]["tokens"] == 150


class TestQueryEndpoints:
    def test_list_users_empty(self, client):
        """GET /api/users returns empty list when no data."""
        tc, mock_db, _ = client
        mock_db.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = iter(
            []
        )
        resp = tc.get("/api/users")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_session_not_found(self, client):
        """GET /api/users/{uid}/sessions/{sid} returns 404 for missing session."""
        tc, mock_db, _ = client
        # Entity model uses db.document("users/alice").collection("sessions").document("x").get()
        mock_session_doc = MagicMock()
        mock_session_doc.exists = False
        mock_db.document.return_value.collection.return_value.document.return_value.get.return_value = mock_session_doc
        resp = tc.get("/api/users/alice/sessions/nonexistent")
        assert resp.status_code == 404


class TestDashboard:
    def test_index_returns_html(self, client):
        """GET / returns the dashboard HTML."""
        tc, _, _ = client
        resp = tc.get("/")
        assert resp.status_code == 200
        assert "seerai" in resp.text
        assert "text/html" in resp.headers["content-type"]

    def test_sessions_page_returns_html(self, client):
        """GET /sessions/{uid} returns HTML."""
        tc, _, _ = client
        resp = tc.get("/sessions/alice")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_session_detail_page_returns_html(self, client):
        """GET /session/{uid}/{sid} returns HTML."""
        tc, _, _ = client
        resp = tc.get("/session/alice/s1")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
