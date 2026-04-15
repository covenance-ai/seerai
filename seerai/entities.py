"""Firestore document entities — single source of truth for document shapes.

Each class mirrors a Firestore document type exactly. Fields here
are what gets written to and read from Firestore.

Collection hierarchy:
    orgs/{org_id}
    users/{user_id}
    users/{user_id}/sessions/{session_id}
    users/{user_id}/sessions/{session_id}/events/{event_id}
    subscriptions/{subscription_id}
    insights/{insight_id}
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel

from seerai.firestore_model import FirestoreModel

EventType = Literal["user_message", "ai_message", "error", "coach_intervention"]
UserRole = Literal["admin", "exec", "user"]

# Coach intervention taxonomy — four categories of observer value.
CoachCategory = Literal["factuality", "efficiency", "sources", "other"]
# Concrete intervention kinds. New kinds can be added freely; UI falls back
# to the category badge if the kind isn't in its lookup.
CoachKind = Literal[
    # factuality
    "hallucinated_api",
    "wrong_fact",
    "math_error",
    "self_contradiction",
    # efficiency
    "off_track",
    "repeat_failure",
    "wrong_tool",
    "redundant_work",
    # sources
    "fabricated_citation",
    "misquoted_source",
    "weak_source",
    "missing_source",
    # other
    "pii_leak",
    "scope_confirm",
    "missing_context",
    "prompt_nudge",
    "dangerous_action",
]
# How the coach intervened on this turn:
#   rewrite — replaced the AI's output entirely
#   amend   — appended/prepended context (caveat, source)
#   inject  — inserted a coach-only turn into the stream
#   block   — halted the AI's original output from being shown
CoachMode = Literal["rewrite", "amend", "inject", "block"]


class InlineEvent(BaseModel):
    """Event shape used when storing events inline on a parent doc.

    Same fields as Event but without the FirestoreModel subcollection
    machinery — used for counterfactual transcripts, where the events
    are always read together with the session.
    """

    event_id: str
    event_type: EventType
    content: str
    timestamp: datetime
    metadata: dict | None = None


class CoachInterventionMetadata(BaseModel):
    """Shape of `metadata` on a coach_intervention Event.

    Stored as a plain dict on the Event; this model documents and validates
    the expected keys. The `content` of the Event is the coach's rationale
    / user-visible correction text.
    """

    category: CoachCategory
    kind: CoachKind
    mode: CoachMode
    severity: int = 3  # 1 critical .. 5 info
    targets_event_id: str | None = None  # AI message this acts on
    quoted_span: str | None = None  # exact text being flagged
    sources: list[str] | None = None
    accepted: bool | None = None
    estimated_savings_cents: int = 0
    # When mode="rewrite"/"amend"/"block", the coached AI turn should carry
    # `metadata.pre_coach_content` with the original AI text for per-bubble
    # diffs. This field captures the same span on the intervention so the
    # coach feed can render it without cross-referencing.
    pre_coach_excerpt: str | None = None
# Utility classes:
#   non_work: off-topic chats, casual queries
#   trivial:  small lookups / drafting (low time savings)
#   useful:   substantive, time-saving sessions
#   harmful:  AI hurt productivity (hallucinated, sent user down wrong path,
#             produced confidently-wrong code that had to be reverted, etc.).
#             Only assigned by the post-hoc QA pipeline (stronger model + user
#             feedback) — the cheap ingest classifier never emits "harmful".
UtilityClass = Literal["non_work", "trivial", "useful", "harmful"]
InsightKind = Literal[
    "cross_department_interest",
    "above_paygrade",
    "below_paygrade",
    "negative_roi_pattern",
]


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
    token_usage: dict[str, int] | None = None  # {model_name: total_output_tokens}
    flagged_for_support_at: datetime | None = None  # set by exec to share with seer.ai support
    flag_note: str | None = None  # exec's reason for flagging (e.g. wrong AI analysis)
    # QA pipeline metadata: set when the stronger model / user feedback
    # post-processes a session and overrides the ingest-time utility.
    utility_qa_reviewed_at: datetime | None = None
    utility_qa_note: str | None = None  # short reason for the override
    # Coach intervention rollups — populated when the session's coached
    # transcript includes coach_intervention events.
    intervention_count: int = 0
    intervention_categories: list[CoachCategory] | None = None
    # Counterfactual utility: the class the session would have landed in
    # if coach had not intervened. None for uncoached sessions.
    counterfactual_utility: UtilityClass | None = None
    # Counterfactual transcript — what the user would have seen if coach
    # hadn't intervened. None for uncoached sessions. Inlined on the session
    # doc because we always read it together with the actual events.
    counterfactual_events: list[InlineEvent] | None = None

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


class Insight(FirestoreModel):
    """insights/{insight_id} — an AI-generated insight about an employee."""

    __collection__: ClassVar[str] = "insights"
    __id_field__: ClassVar[str] = "insight_id"

    insight_id: str
    kind: InsightKind
    priority: int  # 1 (critical) to 5 (low)
    created_at: datetime
    title: str
    description: str  # AI analysis text
    user_id: str
    org_id: str  # user's department
    target_org_id: str | None = None  # for cross_department_interest
    evidence_session_ids: list[str]
    dismissed_at: datetime | None = None  # None = active; set when user archives
    flagged_for_support_at: datetime | None = None  # exec flagged for seer.ai review
    flag_note: str | None = None  # reason: typically "wrong AI analysis" feedback


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
