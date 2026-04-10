import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from google.cloud.firestore_v1 import SERVER_TIMESTAMP, Increment

from seerai.firestore_client import get_firestore_client
from seerai.models import IngestEvent, StoredEvent

router = APIRouter(tags=["ingest"])


def _write_event(event: IngestEvent) -> StoredEvent:
    db = get_firestore_client()
    event_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    user_ref = db.collection("users").document(event.user_id)
    session_ref = user_ref.collection("sessions").document(event.session_id)
    event_ref = session_ref.collection("events").document(event_id)

    batch = db.batch()

    batch.set(
        user_ref,
        {"user_id": event.user_id, "last_active": SERVER_TIMESTAMP},
        merge=True,
    )

    batch.set(
        session_ref,
        {
            "session_id": event.session_id,
            "user_id": event.user_id,
            "last_event_at": SERVER_TIMESTAMP,
            "last_event_type": event.event_type,
            "event_count": Increment(1),
        },
        merge=True,
    )

    batch.set(
        event_ref,
        {
            "event_id": event_id,
            "event_type": event.event_type,
            "content": event.content,
            "metadata": event.metadata,
            "timestamp": SERVER_TIMESTAMP,
        },
    )

    batch.commit()

    return StoredEvent(event_id=event_id, timestamp=now, **event.model_dump())


@router.post("/ingest")
def ingest(event: IngestEvent) -> StoredEvent:
    return _write_event(event)


@router.post("/ingest/batch")
def ingest_batch(events: list[IngestEvent]) -> list[StoredEvent]:
    return [_write_event(e) for e in events]
