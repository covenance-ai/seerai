"""Create the ``covenance.ai`` root org that real ingested users bootstrap into.

Idempotent: running it twice is a no-op. Runs against whatever datasource
``get_firestore_client()`` resolves to (Firestore in production, LocalStore
if a local snapshot is present).

Usage:
    uv run python scripts/bootstrap_real_org.py
"""

from __future__ import annotations

from seerai.entities import OrgNode
from seerai.ingest.endpoint import DEFAULT_INGEST_ORG_ID


def ensure_real_org() -> OrgNode:
    existing = OrgNode.get(DEFAULT_INGEST_ORG_ID)
    if existing:
        print(f"✓ Org '{DEFAULT_INGEST_ORG_ID}' already exists")
        return existing
    node = OrgNode(
        org_id=DEFAULT_INGEST_ORG_ID,
        name="Covenance",
        parent_id=None,
        path=[DEFAULT_INGEST_ORG_ID],
        depth=0,
    )
    node.save(merge=False)
    print(f"✓ Created org '{DEFAULT_INGEST_ORG_ID}'")
    return node


if __name__ == "__main__":
    ensure_real_org()
