from datetime import datetime
from typing import Literal

from pydantic import BaseModel

EventType = Literal["user_message", "ai_message", "error"]


class IngestEvent(BaseModel):
    """Payload POSTed by any client to record a chat event."""

    user_id: str
    session_id: str
    event_type: EventType
    content: str
    timestamp: datetime | None = None
    metadata: dict | None = None


class StoredEvent(IngestEvent):
    """Event as persisted in Firestore, with server-assigned fields."""

    event_id: str
    timestamp: datetime


class SessionSummary(BaseModel):
    """Summary of a session for listing views."""

    session_id: str
    user_id: str
    last_event_at: datetime
    event_count: int
    last_event_type: EventType | None = None


class SessionDetail(BaseModel):
    """Full session with its events."""

    session_id: str
    user_id: str
    events: list[StoredEvent]


class UserSummary(BaseModel):
    """Summary of a user for listing views."""

    user_id: str
    last_active: datetime
