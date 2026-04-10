from fastapi import APIRouter, HTTPException

from seerai.firestore_client import get_firestore_client
from seerai.models import SessionDetail, SessionSummary, StoredEvent, UserSummary

router = APIRouter(tags=["query"])


@router.get("/users")
def list_users() -> list[UserSummary]:
    db = get_firestore_client()
    docs = (
        db.collection("users")
        .order_by("last_active", direction="DESCENDING")
        .limit(100)
        .stream()
    )
    return [UserSummary(**doc.to_dict()) for doc in docs]


@router.get("/users/{user_id}/sessions")
def list_sessions(user_id: str) -> list[SessionSummary]:
    db = get_firestore_client()
    docs = (
        db.collection("users")
        .document(user_id)
        .collection("sessions")
        .order_by("last_event_at", direction="DESCENDING")
        .limit(50)
        .stream()
    )
    return [SessionSummary(**doc.to_dict()) for doc in docs]


@router.get("/users/{user_id}/sessions/{session_id}")
def get_session(user_id: str, session_id: str) -> SessionDetail:
    db = get_firestore_client()

    session_ref = (
        db.collection("users")
        .document(user_id)
        .collection("sessions")
        .document(session_id)
    )
    session_doc = session_ref.get()
    if not session_doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")

    event_docs = session_ref.collection("events").order_by("timestamp").stream()
    events = [
        StoredEvent(user_id=user_id, session_id=session_id, **doc.to_dict())
        for doc in event_docs
    ]

    return SessionDetail(
        session_id=session_id,
        user_id=user_id,
        events=events,
    )
