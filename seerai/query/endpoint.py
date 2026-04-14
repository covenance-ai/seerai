from fastapi import APIRouter, HTTPException

from seerai.entities import Event, Session, User
from seerai.models import SessionDetail, StoredEvent

router = APIRouter(tags=["query"])


@router.get("/users")
def list_users() -> list[User]:
    return User.list(order_by="last_active", limit=100)


@router.get("/users/{user_id}/sessions")
def list_sessions(user_id: str) -> list[Session]:
    return Session.for_user(user_id)


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
