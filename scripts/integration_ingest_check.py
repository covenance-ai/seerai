"""End-to-end ingest check against real Firestore.

The unit tests in ``tests/test_ingest.py`` stub Firestore out with ``MagicMock``
— they prove the FastAPI layer parses payloads and shapes the batch write
correctly, but can never catch "credentials broken", "Firestore index missing",
"types don't round-trip through the real backend", or similar integration
bugs. This script does the real thing: spins up the FastAPI app wired to
real Firestore, POSTs realistic events through ``/api/ingest``, reads them
back with the entity API, and asserts the round-trip.

To keep production data untouched, every artifact is written under a
quarantined child-org ``covenance.ai-integ`` and user ids are prefixed with
``_integ_``. Run with ``--cleanup`` to remove the quarantined artifacts after
the checks pass (default behaviour leaves them in place so you can inspect
the dashboard afterwards).

Usage::

    # full run, leave artifacts for manual inspection
    DATA_SOURCE=firestore uv run python scripts/integration_ingest_check.py

    # full run, delete the test user + test org at the end
    DATA_SOURCE=firestore uv run python scripts/integration_ingest_check.py --cleanup

    # delete any artifacts from a previous run and exit
    DATA_SOURCE=firestore uv run python scripts/integration_ingest_check.py --cleanup-only
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta

from seerai.entities import Event, OrgNode, Session, User
from seerai.firestore_client import get_datasource, get_firestore_client
from seerai.ingest.endpoint import DEFAULT_INGEST_ORG_ID

REAL_ORG_ID = DEFAULT_INGEST_ORG_ID  # "covenance.ai"
TEST_ORG_ID = "covenance.ai-integ"  # child of covenance.ai, quarantined
TEST_USER_PREFIX = "_integ_"

# Small realistic conversation samples — keep the payload varied enough that
# token accumulation, error branches, and provider/platform tagging all run.
USER_MSGS = [
    "Draft a DPIA section for our new analytics vendor.",
    "Explain Article 35 of GDPR in plain English.",
    "Review this retention policy — is 7 years defensible?",
    "Help me write a breach notification to the DPA.",
]
AI_MSGS = [
    "Under Article 35 you need a DPIA when processing is likely to produce high risk. Key triggers include systematic profiling and large-scale sensitive data.",
    "Seven years is only defensible if you can point to a specific statutory retention period or a clear contractual need. Without one, minimise.",
    "The notification should be filed within 72 hours and cover the nature of the breach, affected categories, mitigations, and a DPO contact.",
]
PROVIDERS = [("anthropic", "claude-sonnet-4"), ("openai", "gpt-4o"), ("google", "gemini-2.5-pro")]
PLATFORMS = ["chrome", "vscode", "cli"]


# ---------- helpers ----------


def _require_firestore() -> None:
    """Refuse to run against the local JSON snapshot — integration means real Firestore."""
    src = get_datasource()
    if src != "firestore":
        print(
            f"[abort] datasource is '{src}', not 'firestore'. "
            "Set DATA_SOURCE=firestore (and ensure gcloud creds) before running.",
            file=sys.stderr,
        )
        sys.exit(2)


def _ensure_orgs() -> None:
    """Make sure both the real root org and the quarantined child exist."""
    if not OrgNode.get(REAL_ORG_ID):
        OrgNode(
            org_id=REAL_ORG_ID,
            name="Covenance",
            parent_id=None,
            path=[REAL_ORG_ID],
            depth=0,
        ).save(merge=False)
        print(f"  • bootstrapped root org '{REAL_ORG_ID}'")

    if not OrgNode.get(TEST_ORG_ID):
        OrgNode(
            org_id=TEST_ORG_ID,
            name="Covenance — Integration Tests",
            parent_id=REAL_ORG_ID,
            path=[REAL_ORG_ID, TEST_ORG_ID],
            depth=1,
        ).save(merge=False)
        print(f"  • bootstrapped quarantine org '{TEST_ORG_ID}'")


def _make_client():
    """Build a TestClient wired to the real app/Firestore.

    Imported lazily so ``--cleanup-only`` runs don't need fastapi.
    """
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)


def _post(tc, payload: dict) -> dict:
    resp = tc.post("/api/ingest", json=payload)
    if resp.status_code != 200:
        raise AssertionError(f"POST /api/ingest failed: {resp.status_code} {resp.text}")
    return resp.json()


# ---------- scenario ----------


def _make_session_events(user_id: str, session_id: str, base_ts: datetime) -> list[dict]:
    """A mini-conversation: user → ai → user → ai → error, spaced 30s apart."""
    provider, model = random.choice(PROVIDERS)
    platform = random.choice(PLATFORMS)
    common = {
        "user_id": user_id,
        "session_id": session_id,
        "provider": provider,
        "platform": platform,
    }
    events: list[dict] = []
    for i, (etype, content, meta) in enumerate(
        [
            ("user_message", random.choice(USER_MSGS), None),
            ("ai_message", random.choice(AI_MSGS), {"model": model, "tokens": 180}),
            ("user_message", "thanks, one follow-up — what are the penalties?", None),
            (
                "ai_message",
                "Tier-one penalties reach €20m or 4% of global annual turnover, whichever is higher.",
                {"model": model, "tokens": 120},
            ),
            ("error", "rate_limit_exceeded", {"code": 429}),
        ]
    ):
        events.append(
            {
                **common,
                "event_type": etype,
                "content": content,
                "metadata": meta,
                "timestamp": (base_ts + timedelta(seconds=30 * i)).isoformat(),
            }
        )
    return events


def run_checks() -> None:
    print(f"[integration] datasource = {get_datasource()}")
    _ensure_orgs()

    tc = _make_client()

    # One brand-new user id per run → exercises the "first-time user" branch
    # (new users should land in covenance.ai). We then reassign to the
    # quarantine org so the check's artefacts don't mix with real data.
    user_id = f"{TEST_USER_PREFIX}{uuid.uuid4().hex[:10]}"
    session_id_a = str(uuid.uuid4())
    session_id_b = str(uuid.uuid4())
    now = datetime.now(UTC).replace(microsecond=0)

    events_a = _make_session_events(user_id, session_id_a, now - timedelta(minutes=20))
    events_b = _make_session_events(user_id, session_id_b, now - timedelta(minutes=5))

    print(f"\n[integration] new user id: {user_id}")
    print(f"[integration] posting {len(events_a)} + {len(events_b)} events via /api/ingest …")

    first = _post(tc, events_a[0])
    assert first["event_id"], "ingest did not return event_id"
    for e in events_a[1:] + events_b:
        _post(tc, e)

    # --- Verify user was bootstrapped into covenance.ai ---
    user = User.get(user_id)
    assert user is not None, "user doc missing after ingest"
    assert user.org_id == REAL_ORG_ID, (
        f"new ingested user should land in '{REAL_ORG_ID}', got {user.org_id!r}"
    )
    print(f"  ✓ user exists, org_id={user.org_id}")

    # Move this integration user to the quarantine org so dashboards render it
    # as "Integration Tests" and not mixed with production covenance.ai data.
    user.org_id = TEST_ORG_ID
    user.sync()
    print(f"  ✓ reassigned user to quarantine org '{TEST_ORG_ID}'")

    # --- Verify sessions + event counts + token usage ---
    sessions = {s.session_id: s for s in Session.for_user(user_id)}
    assert session_id_a in sessions and session_id_b in sessions, (
        f"expected both sessions, got {list(sessions)}"
    )
    for sid in (session_id_a, session_id_b):
        s = sessions[sid]
        assert s.event_count == 5, f"session {sid}: event_count={s.event_count}, want 5"
        assert s.error_count == 1, f"session {sid}: error_count={s.error_count}, want 1"
        assert s.provider, "provider missing on session"
        assert s.platform, "platform missing on session"
        assert s.token_usage, "token_usage missing on session"
        total_tokens = sum(s.token_usage.values())
        assert total_tokens == 300, f"token_usage total {total_tokens} != 300"
    print(f"  ✓ 2 sessions written, event_count/error_count/token_usage match")

    # --- Verify events round-trip in order ---
    got = Event.for_session(user_id, session_id_a)
    assert len(got) == 5, f"event count {len(got)} != 5"
    timestamps = [e.timestamp for e in got]
    assert timestamps == sorted(timestamps), "events not ordered by timestamp"
    assert got[0].event_type == "user_message"
    assert got[-1].event_type == "error"
    print(f"  ✓ event round-trip: types={[e.event_type for e in got]}")

    # --- Returning-user invariant: re-ingest must NOT overwrite org_id ---
    _post(
        tc,
        {
            "user_id": user_id,
            "session_id": session_id_a,
            "event_type": "user_message",
            "content": "ping",
        },
    )
    user_after = User.get(user_id)
    assert user_after.org_id == TEST_ORG_ID, (
        f"returning-user ingest clobbered org_id: {user_after.org_id!r} "
        f"(wanted '{TEST_ORG_ID}', we had just reassigned it)"
    )
    print(f"  ✓ returning-user ingest preserved org_id='{TEST_ORG_ID}'")

    print(f"\n[integration] PASS — artefacts left under org '{TEST_ORG_ID}', user '{user_id}'")
    print("[integration] run with --cleanup to delete; --cleanup-only to purge all prior runs.")


# ---------- cleanup ----------


def _delete_user_fully(user_id: str) -> int:
    """Remove a user + all their sessions + all their events. Returns docs deleted."""
    db = get_firestore_client()
    count = 0
    # events under each session
    for s in Session.for_user(user_id, limit=0):
        evs_ref = (
            db.document(Session.parent_path(user_id))
            .collection("sessions")
            .document(s.session_id)
            .collection("events")
        )
        for ev in evs_ref.stream():
            ev.reference.delete()
            count += 1
        db.document(Session.parent_path(user_id)).collection("sessions").document(
            s.session_id
        ).delete()
        count += 1
    db.collection("users").document(user_id).delete()
    count += 1
    return count


def cleanup(*, include_test_org: bool = True) -> None:
    print(f"[cleanup] datasource = {get_datasource()}")
    total_docs = 0
    total_users = 0
    db = get_firestore_client()
    for user_doc in db.collection("users").stream():
        if not user_doc.id.startswith(TEST_USER_PREFIX):
            continue
        n = _delete_user_fully(user_doc.id)
        total_users += 1
        total_docs += n
        print(f"  • deleted user {user_doc.id} ({n} docs)")
    print(f"[cleanup] removed {total_users} users / {total_docs} docs")

    if include_test_org and OrgNode.get(TEST_ORG_ID):
        OrgNode.get(TEST_ORG_ID).delete()
        print(f"  • deleted quarantine org '{TEST_ORG_ID}'")


# ---------- cli ----------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--cleanup",
        action="store_true",
        help="after a successful check, delete the integration user + quarantine org.",
    )
    p.add_argument(
        "--cleanup-only",
        action="store_true",
        help="skip the check, just purge any leftover _integ_* artefacts.",
    )
    args = p.parse_args()

    # Failsafe — never touch the local snapshot from this script.
    _require_firestore()

    if args.cleanup_only:
        cleanup(include_test_org=True)
        return

    try:
        run_checks()
    finally:
        if args.cleanup:
            cleanup(include_test_org=True)


if __name__ == "__main__":
    # Integration scripts live outside of pytest so they don't depend on the
    # test runner — we import the FastAPI app directly. Make sure the local
    # dir is on the path when invoked via `python scripts/...`.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
