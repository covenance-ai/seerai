"""Firestore document entities — single source of truth for document shapes.

Each class mirrors a Firestore document type exactly. Fields here
are what gets written to and read from Firestore.

Collection hierarchy:
    orgs/{org_id}
    users/{user_id}
    users/{user_id}/sessions/{session_id}
    users/{user_id}/sessions/{session_id}/events/{event_id}
    subscriptions/{subscription_id}
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from seerai.firestore_model import FirestoreModel

EventType = Literal["user_message", "ai_message", "error"]
UserRole = Literal["exec", "user"]
UtilityClass = Literal["non_work", "trivial", "useful"]


class OrgNode(FirestoreModel):
    """orgs/{org_id} — a node in the organizational hierarchy."""

    __collection__: ClassVar[str] = "orgs"
    __id_field__: ClassVar[str] = "org_id"

    org_id: str
    name: str
    parent_id: str | None = None
    path: list[str]
    depth: int


class User(FirestoreModel):
    """users/{user_id} — a tracked user."""

    __collection__: ClassVar[str] = "users"
    __id_field__: ClassVar[str] = "user_id"

    user_id: str
    last_active: datetime
    org_id: str | None = None
    role: UserRole = "user"
    hourly_rate: float | None = None  # $/hr, proxy for employee paygrade


class Session(FirestoreModel):
    """users/{user_id}/sessions/{session_id} — a chat session."""

    __collection__: ClassVar[str] = "sessions"
    __id_field__: ClassVar[str] = "session_id"

    session_id: str
    user_id: str
    last_event_at: datetime
    last_event_type: EventType | None = None
    event_count: int = 0
    error_count: int = 0
    provider: str | None = None
    platform: str | None = None
    utility: UtilityClass | None = None

    @classmethod
    def parent_path(cls, user_id: str) -> str:
        return f"users/{user_id}"

    @classmethod
    def for_user(
        cls, user_id: str, *, order_by: str = "last_event_at", limit: int = 50
    ) -> list[Session]:
        return cls.list(
            parent_path=cls.parent_path(user_id), order_by=order_by, limit=limit
        )


class Event(FirestoreModel):
    """users/{user_id}/sessions/{session_id}/events/{event_id} — a single chat event."""

    __collection__: ClassVar[str] = "events"
    __id_field__: ClassVar[str] = "event_id"

    event_id: str
    event_type: EventType
    content: str
    timestamp: datetime
    metadata: dict | None = None

    @classmethod
    def parent_path(cls, user_id: str, session_id: str) -> str:
        return f"users/{user_id}/sessions/{session_id}"

    @classmethod
    def for_session(cls, user_id: str, session_id: str) -> list[Event]:
        return cls.list(
            parent_path=cls.parent_path(user_id, session_id),
            order_by="timestamp",
            direction="ASCENDING",
            limit=0,  # no limit
        )


class Subscription(FirestoreModel):
    """subscriptions/{subscription_id} — an AI subscription paid by the company."""

    __collection__: ClassVar[str] = "subscriptions"
    __id_field__: ClassVar[str] = "subscription_id"

    subscription_id: str
    user_id: str
    provider: str  # e.g. "anthropic", "openai", "google"
    plan: str  # e.g. "Claude Pro", "ChatGPT Plus"
    monthly_cost_cents: int  # 2000 = $20.00
    currency: str = "USD"
    started_at: datetime
    ended_at: datetime | None = None  # None = active
