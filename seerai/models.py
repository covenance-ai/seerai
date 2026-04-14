"""API request/response models.

Entity types (what's stored in Firestore) live in entities.py.
These models are for API payloads and computed responses.
"""

from datetime import datetime

from pydantic import BaseModel

from seerai.entities import (  # noqa: F401
    Event,
    EventType,
    OrgNode,
    Session,
    User,
    UserRole,
)


class IngestEvent(BaseModel):
    """Payload POSTed by any client to record a chat event."""

    user_id: str
    session_id: str
    event_type: EventType
    content: str
    timestamp: datetime | None = None
    metadata: dict | None = None


class StoredEvent(IngestEvent):
    """API response after ingesting — event fields plus user/session context."""

    event_id: str
    timestamp: datetime


class SessionDetail(BaseModel):
    """Full session with its events — API response for session detail view."""

    session_id: str
    user_id: str
    events: list[StoredEvent]


class OrgNodeStats(BaseModel):
    """Org node with aggregate stats computed on read."""

    org_id: str
    name: str
    parent_id: str | None = None
    depth: int
    user_count: int = 0
    session_count: int = 0
    message_count: int = 0
    error_count: int = 0
