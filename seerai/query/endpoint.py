from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from seerai.entities import Event, Session, User
from seerai.models import SessionDetail, StoredEvent

router = APIRouter(tags=["query"])


class HeatmapDay(BaseModel):
    date: str
    count: int


@router.get("/users")
def list_users() -> list[User]:
    return User.list(order_by="last_active", limit=100)


@router.get("/users/{user_id}/sessions")
def list_sessions(user_id: str) -> list[Session]:
    return Session.for_user(user_id)


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


@router.get("/users/{user_id}/sessions/{session_id}")
def get_session(user_id: str, session_id: str) -> SessionDetail:
    session = Session.get(session_id, parent_path=Session.parent_path(user_id))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    events = Event.for_session(user_id, session_id)

    return SessionDetail(
        session_id=session_id,
        user_id=user_id,
        events=[
            StoredEvent(user_id=user_id, session_id=session_id, **e.model_dump())
            for e in events
        ],
    )
