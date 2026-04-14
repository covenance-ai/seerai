"""Download all Firestore data to a local JSON snapshot.

Usage:
    uv run python -m seerai.snapshot                      # default: data/snapshot.json
    uv run python -m seerai.snapshot -o data/backup.json  # custom path
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

TOP_LEVEL_COLLECTIONS = ["users", "orgs", "subscriptions", "insights"]


def _default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Not JSON serializable: {type(obj)}")


def _firestore_client():
    """Always returns a real Firestore client, ignoring DATA_SOURCE setting."""
    import os

    from google.cloud.firestore import Client

    return Client(
        project=os.getenv("GCP_PROJECT", "covenance-469421"),
        database=os.getenv("FIRESTORE_DATABASE", "seerai"),
    )


def download(output: Path) -> dict[str, int]:
    """Download all Firestore collections to a JSON file. Returns collection counts."""
    db = _firestore_client()
    data: dict[str, dict] = {}
    counts: dict[str, int] = {}

    for name in TOP_LEVEL_COLLECTIONS:
        data[name] = {}
        for doc in db.collection(name).stream():
            data[name][doc.id] = doc.to_dict()
        counts[name] = len(data[name])
        log.info("%s: %d docs", name, counts[name])

    # Subcollections: sessions and events under each user
    session_count = event_count = 0
    for user_id in list(data["users"]):
        sessions_path = f"users/{user_id}/sessions"
        data[sessions_path] = {}
        for sdoc in db.document(f"users/{user_id}").collection("sessions").stream():
            data[sessions_path][sdoc.id] = sdoc.to_dict()
            session_count += 1

            events_path = f"{sessions_path}/{sdoc.id}/events"
            data[events_path] = {}
            for edoc in (
                db.document(f"{sessions_path}/{sdoc.id}").collection("events").stream()
            ):
                data[events_path][edoc.id] = edoc.to_dict()
                event_count += 1

    counts["sessions"] = session_count
    counts["events"] = event_count
    log.info("sessions: %d, events: %d", session_count, event_count)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, default=_default))
    log.info("Saved to %s (%.1f MB)", output, output.stat().st_size / 1e6)
    return counts


def main():
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Download Firestore snapshot")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "snapshot.json",
    )
    args = parser.parse_args()
    download(args.output)


if __name__ == "__main__":
    main()
