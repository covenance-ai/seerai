"""Model validation tests — verify Pydantic schemas accept/reject correctly."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from seerai.entities import Session
from seerai.models import (
    IngestEvent,
    SessionDetail,
    StoredEvent,
)


class TestIngestEvent:
    def test_valid_user_message(self):
        """Basic user message round-trips through the model."""
        e = IngestEvent(
            user_id="alice",
            session_id="s1",
            event_type="user_message",
            content="hello",
        )
        assert e.user_id == "alice"
        assert e.metadata is None

    def test_valid_with_metadata(self):
        """Metadata dict is preserved as-is."""
        e = IngestEvent(
            user_id="bob",
            session_id="s2",
            event_type="ai_message",
            content="hi",
            metadata={"model": "claude-3", "tokens": 42},
        )
        assert e.metadata["model"] == "claude-3"

    def test_all_event_types_accepted(self):
        """Each declared EventType literal is valid."""
        for t in ("user_message", "ai_message", "error"):
            e = IngestEvent(user_id="u", session_id="s", event_type=t, content="x")
            assert e.event_type == t

    def test_invalid_event_type_rejected(self):
        """Unknown event types are rejected."""
        with pytest.raises(ValidationError):
            IngestEvent(
                user_id="u",
                session_id="s",
                event_type="tool_use",
                content="x",
            )

    def test_missing_required_field(self):
        """Omitting content raises ValidationError."""
        with pytest.raises(ValidationError):
            IngestEvent(user_id="u", session_id="s", event_type="error")


class TestStoredEvent:
    def test_extends_ingest_event(self):
        """StoredEvent adds event_id and timestamp to IngestEvent fields."""
        e = StoredEvent(
            user_id="u",
            session_id="s",
            event_type="user_message",
            content="hi",
            event_id="abc-123",
            timestamp=datetime(2025, 1, 1, tzinfo=UTC),
        )
        assert e.event_id == "abc-123"
        assert e.user_id == "u"

    def test_serialization_roundtrip(self):
        """model_dump -> model_validate roundtrip preserves all fields."""
        original = StoredEvent(
            user_id="u",
            session_id="s",
            event_type="ai_message",
            content="response",
            event_id="id-1",
            timestamp=datetime(2025, 6, 1, tzinfo=UTC),
            metadata={"model": "gpt-4"},
        )
        rebuilt = StoredEvent.model_validate(original.model_dump())
        assert rebuilt == original


class TestSession:
    def test_all_event_types_in_last_event(self):
        """last_event_type accepts all valid types and None."""
        for t in ("user_message", "ai_message", "error", None):
            s = Session(
                session_id="s",
                user_id="u",
                last_event_at=datetime.now(UTC),
                event_count=1,
                last_event_type=t,
            )
            assert s.last_event_type == t


class TestSessionDetail:
    def test_events_list_ordering_preserved(self):
        """Events list maintains insertion order (caller is responsible for sorting)."""
        events = [
            StoredEvent(
                user_id="u",
                session_id="s",
                event_type="user_message",
                content=f"msg-{i}",
                event_id=f"e{i}",
                timestamp=datetime(2025, 1, 1, i, tzinfo=UTC),
            )
            for i in range(1, 4)
        ]
        detail = SessionDetail(session_id="s", user_id="u", events=events)
        assert [e.content for e in detail.events] == ["msg-1", "msg-2", "msg-3"]
