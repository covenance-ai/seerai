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

    def test_provider_and_platform_written_to_session(self, client):
        """provider and platform from the payload are included in the session batch write."""
        tc, mock_db, mock_batch = client
        tc.post(
            "/api/ingest",
            json={
                "user_id": "u",
                "session_id": "s",
                "event_type": "user_message",
                "content": "hi",
                "provider": "anthropic",
                "platform": "vscode",
            },
        )
        # Find the session set() call — the one whose data dict has "session_id"
        for call in mock_batch.set.call_args_list:
            data = call[0][1]
            if "session_id" in data:
                assert data["provider"] == "anthropic"
                assert data["platform"] == "vscode"
                break
        else:
            pytest.fail("No session batch.set call found")

    def test_provider_and_platform_omitted_when_absent(self, client):
        """When provider/platform are not sent, they don't appear in the session write."""
        tc, mock_db, mock_batch = client
        tc.post(
            "/api/ingest",
            json={
                "user_id": "u",
                "session_id": "s",
                "event_type": "user_message",
                "content": "hi",
            },
        )
        for call in mock_batch.set.call_args_list:
            data = call[0][1]
            if "session_id" in data:
                assert "provider" not in data
                assert "platform" not in data
                break


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

    def test_heatmap_returns_daily_counts(self, client):
        """GET /api/users/{uid}/heatmap returns date/count pairs covering recent months."""
        from datetime import UTC, datetime, timedelta

        tc, mock_db, _ = client
        today = datetime.now(UTC).date()

        # Create mock session docs for 3 sessions across 2 days
        def make_doc(session_id, days_ago):
            doc = MagicMock()
            dt = datetime(
                today.year, today.month, today.day, 10, tzinfo=UTC
            ) - timedelta(days=days_ago)
            doc.to_dict.return_value = {
                "session_id": session_id,
                "user_id": "alice",
                "last_event_at": dt,
                "event_count": 5,
            }
            return doc

        mock_docs = [make_doc("s1", 0), make_doc("s2", 0), make_doc("s3", 2)]
        # Session.list with parent_path goes: db.document(pp).collection(coll).order_by(...).stream()
        mock_db.document.return_value.collection.return_value.order_by.return_value.stream.return_value = iter(
            mock_docs
        )

        resp = tc.get("/api/users/alice/heatmap")
        assert resp.status_code == 200
        days = resp.json()
        assert len(days) > 30  # spans at least a few months
        assert all("date" in d and "count" in d for d in days)

        by_date = {d["date"]: d["count"] for d in days}
        assert by_date[today.isoformat()] == 2
        assert by_date[(today - timedelta(days=2)).isoformat()] == 1
        # Days without sessions have count 0
        assert by_date.get((today - timedelta(days=1)).isoformat(), 0) == 0


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
