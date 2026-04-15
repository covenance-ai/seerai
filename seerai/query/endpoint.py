from collections import Counter
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from seerai.entities import Event, Session, User
from seerai.models import SessionDetail, StoredEvent

router = APIRouter(tags=["query"])


class HeatmapDay(BaseModel):
    date: str
    count: int


class FlagRequest(BaseModel):
    note: str | None = None


@router.get("/users")
def list_users() -> list[User]:
    return User.list(order_by="last_active", limit=100)


@router.get("/users/{user_id}/sessions")
def list_sessions(user_id: str) -> list[Session]:
    return Session.for_user(user_id, limit=0)


@router.get("/users/{user_id}/heatmap")
def user_heatmap(user_id: str) -> list[HeatmapDay]:
    """Session counts per day for the activity calendar."""
    sessions = Session.list(
        parent_path=Session.parent_path(user_id),
        order_by="last_event_at",
        direction="DESCENDING",
        limit=0,
    )
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=90)).replace(day=1)

    counts: Counter[str] = Counter()
    for s in sessions:
        d = s.last_event_at.date()
        if d >= start:
            counts[d.isoformat()] += 1

    heatmap = []
    d = start
    while d <= today:
        ds = d.isoformat()
        heatmap.append(HeatmapDay(date=ds, count=counts.get(ds, 0)))
        d += timedelta(days=1)
    return heatmap


@router.get("/sessions/flagged")
def list_flagged_sessions() -> list[Session]:
    """Cross-user query: every session flagged for seer.ai support review.

    Sorted by flagged_for_support_at DESC.
    """
    users = User.list(order_by=None, limit=0)
    flagged: list[Session] = []
    for u in users:
        for s in Session.for_user(u.user_id, order_by="last_event_at", limit=0):
            if s.flagged_for_support_at is not None:
                flagged.append(s)
    flagged.sort(key=lambda s: s.flagged_for_support_at, reverse=True)
    return flagged


@router.post("/users/{user_id}/sessions/{session_id}/flag")
def flag_session(user_id: str, session_id: str, req: FlagRequest) -> Session:
    """Flag a session for seer.ai support review."""
    session = Session.get(session_id, parent_path=Session.parent_path(user_id))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.flagged_for_support_at = datetime.now(UTC)
    session.flag_note = req.note
    session.sync()
    return session


@router.post("/users/{user_id}/sessions/{session_id}/unflag")
def unflag_session(user_id: str, session_id: str) -> Session:
    """Withdraw a session's support flag."""
    session = Session.get(session_id, parent_path=Session.parent_path(user_id))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.flagged_for_support_at = None
    session.flag_note = None
    session.sync()
    return session


@router.get("/users/{user_id}/sessions/{session_id}")
def get_session(user_id: str, session_id: str) -> SessionDetail:
    session = Session.get(session_id, parent_path=Session.parent_path(user_id))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    events = Event.for_session(user_id, session_id)

    # Fall back to archetype events for empty mock sessions
    if not events:
        from seerai.archetypes import match_archetype

        ref_uid, ref_sid = match_archetype(session.provider, session.utility)
        events = Event.for_session(ref_uid, ref_sid)

    return SessionDetail(
        session_id=session_id,
        user_id=user_id,
        events=[
            StoredEvent(user_id=user_id, session_id=session_id, **e.model_dump())
            for e in events
        ],
        flagged_for_support_at=session.flagged_for_support_at,
        flag_note=session.flag_note,
        utility=session.utility,
        counterfactual_events=session.counterfactual_events,
        counterfactual_utility=session.counterfactual_utility,
        intervention_count=session.intervention_count,
        intervention_categories=session.intervention_categories,
    )
