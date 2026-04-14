import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from google.cloud.firestore_v1 import Increment

from seerai.firestore_client import get_firestore_client
from seerai.models import IngestEvent, StoredEvent

router = APIRouter(tags=["ingest"])


def _write_event(event: IngestEvent) -> StoredEvent:
    db = get_firestore_client()
    event_id = str(uuid.uuid4())
    ts = event.timestamp or datetime.now(UTC)

    user_ref = db.collection("users").document(event.user_id)
    session_ref = user_ref.collection("sessions").document(event.session_id)
    event_ref = session_ref.collection("events").document(event_id)

    batch = db.batch()

    batch.set(
        user_ref,
        {"user_id": event.user_id, "last_active": ts},
        merge=True,
    )

    session_data = {
        "session_id": event.session_id,
        "user_id": event.user_id,
        "last_event_at": ts,
        "last_event_type": event.event_type,
        "event_count": Increment(1),
    }
    if event.event_type == "error":
        session_data["error_count"] = Increment(1)

    batch.set(session_ref, session_data, merge=True)

    batch.set(
        event_ref,
        {
            "event_id": event_id,
            "event_type": event.event_type,
            "content": event.content,
            "metadata": event.metadata,
            "timestamp": ts,
        },
    )

    batch.commit()

    return StoredEvent(
        event_id=event_id, timestamp=ts, **event.model_dump(exclude={"timestamp"})
    )


@router.post("/ingest")
def ingest(event: IngestEvent) -> StoredEvent:
    return _write_event(event)


@router.post("/ingest/batch")
def ingest_batch(events: list[IngestEvent]) -> list[StoredEvent]:
    return [_write_event(e) for e in events]
