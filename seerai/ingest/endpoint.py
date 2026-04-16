import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from google.cloud.firestore_v1 import Increment

from seerai.entities import Event, Session, User
from seerai.firestore_client import get_firestore_client
from seerai.models import IngestEvent, StoredEvent
from seerai.privacy import Visibility, privacy_surface

router = APIRouter(tags=["ingest"])


def _write_event(event: IngestEvent) -> StoredEvent:
    db = get_firestore_client()
    event_id = str(uuid.uuid4())
    ts = event.timestamp or datetime.now(UTC)

    user_ref = User._doc_ref(db, event.user_id)
    session_ref = Session._doc_ref(
        db, event.session_id, Session.parent_path(event.user_id)
    )
    event_ref = Event._doc_ref(
        db, event_id, Event.parent_path(event.user_id, event.session_id)
    )

    stored_event = Event(
        event_id=event_id,
        event_type=event.event_type,
        content=event.content,
        metadata=event.metadata,
        timestamp=ts,
    )

    batch = db.batch()
    batch.set(user_ref, {"user_id": event.user_id, "last_active": ts}, merge=True)

    session_data = {
        "session_id": event.session_id,
        "user_id": event.user_id,
        "last_event_at": ts,
        "last_event_type": event.event_type,
        "event_count": Increment(1),
    }
    if event.event_type == "error":
        session_data["error_count"] = Increment(1)
    if event.provider:
        session_data["provider"] = event.provider
    if event.platform:
        session_data["platform"] = event.platform

    # Accumulate output token counts per model at the session level
    if (
        event.event_type == "ai_message"
        and event.metadata
        and event.metadata.get("model")
        and event.metadata.get("tokens")
    ):
        model = event.metadata["model"]
        tokens = event.metadata["tokens"]
        session_data[f"token_usage.{model}"] = Increment(tokens)

    batch.set(session_ref, session_data, merge=True)

    batch.set(event_ref, stored_event.model_dump())
    batch.commit()

    return StoredEvent(
        event_id=event_id, timestamp=ts, **event.model_dump(exclude={"timestamp"})
    )


@router.post("/ingest")
@privacy_surface(Visibility.PUBLIC)
def ingest(event: IngestEvent) -> StoredEvent:
    return _write_event(event)


@router.post("/ingest/batch")
@privacy_surface(Visibility.PUBLIC)
def ingest_batch(events: list[IngestEvent]) -> list[StoredEvent]:
    return [_write_event(e) for e in events]
