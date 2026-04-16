"""Generate `prevented_harm_pattern` insights from coach intervention data.

Story: coach interventions rescue sessions from harmful outcomes (hallucinated
APIs, fabricated citations, PII leaks, runaway token spend). This script rolls
up per-session coach value into org-level insights that show up on
`/exec/insights`, so an exec sees the aggregate "$ prevented" alongside
per-employee paygrade and cross-department insights.

For each top-level org (acme, initech) with at least one coach intervention
in its subtree, we call `coach_summary(org_id=...)` and emit one insight
summarising the prevented-harm delta, categories, and evidence sessions.

Usage:
    uv run python scripts/coach_insights.py
    uv run python scripts/coach_insights.py --input data/snapshot.json --seed 42

Idempotent: re-running removes prior `prevented_harm_pattern` insights and
regenerates from current snapshot state.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Minimum interventions in an org's subtree before we emit an insight.
# Loose for the demo — four heroes fire one intervention each, and we want
# each of them to count. Raise for a noisier dataset.
MIN_INTERVENTIONS = 1


def _root_org(snapshot: dict, org_id: str) -> str:
    """Walk the parent_id chain to the root org (e.g. 'acme', 'initech')."""
    seen: set[str] = set()
    while True:
        if org_id in seen:
            return org_id
        seen.add(org_id)
        node = snapshot["orgs"].get(org_id)
        if not node or not node.get("parent_id"):
            return org_id
        org_id = node["parent_id"]


def _coached_sessions_by_root(
    snapshot: dict,
) -> dict[str, list[tuple[str, str, dict]]]:
    """Group (user_id, session_id, session_dict) with interventions by root org."""
    out: dict[str, list[tuple[str, str, dict]]] = {}
    for key, coll in snapshot.items():
        if not (
            key.startswith("users/")
            and key.count("/") == 2
            and key.endswith("/sessions")
        ):
            continue
        user_id = key.split("/")[1]
        user_org = snapshot["users"].get(user_id, {}).get("org_id")
        if not user_org:
            continue
        root = _root_org(snapshot, user_org)
        for sid, sdata in coll.items():
            if sdata.get("intervention_count", 0) > 0:
                out.setdefault(root, []).append((user_id, sid, sdata))
    return out


def _clear_prior_insights(snapshot: dict) -> int:
    """Remove previously-generated prevented_harm_pattern insights."""
    insights = snapshot.get("insights", {})
    to_drop = [
        iid
        for iid, ins in insights.items()
        if ins.get("kind") == "prevented_harm_pattern"
    ]
    for iid in to_drop:
        del insights[iid]
    return len(to_drop)


def _format_shifts(shifts) -> str:
    """Render the top utility shifts as 'rescued N from harmful'-style phrase."""
    parts = []
    for sh in shifts:
        n = sh.sessions
        parts.append(
            f"rescued {n} session{'s' if n != 1 else ''} from {sh.from_class}"
        )
    return "; ".join(parts) if parts else "no utility-class shifts observed"


def _format_kinds(by_kind: dict[str, int], limit: int = 3) -> str:
    """Render the top N intervention kinds as 'N x fabricated_citation, ...'."""
    if not by_kind:
        return "no categorised interventions"
    ranked = sorted(by_kind.items(), key=lambda kv: -kv[1])[:limit]
    pretty = [f"{n}x {kind.replace('_', ' ')}" for kind, n in ranked]
    return ", ".join(pretty)


def emit_insights(snapshot: dict, rng: random.Random) -> int:
    """Generate one prevented_harm_pattern insight per qualifying root org."""
    # Local import: pulling coach_summary at module top forces firestore-client
    # setup at import time; we want snapshot path resolution to win first.
    from seerai.coach.analytics import coach_summary

    now = datetime.now(UTC)
    by_root = _coached_sessions_by_root(snapshot)
    written = 0

    for root_id, sessions in sorted(by_root.items()):
        summary = coach_summary(org_id=root_id)
        if summary.interventions_total < MIN_INTERVENTIONS:
            continue

        org_name = snapshot["orgs"].get(root_id, {}).get("name", root_id)
        value_dollars = summary.value_cents.delta / 100
        evidence = [sid for _, sid, _ in sessions]
        # Pick the user with the most rescued sessions as the insight subject.
        user_counts = Counter(uid for uid, _, _ in sessions)
        top_user = user_counts.most_common(1)[0][0]

        kinds_phrase = _format_kinds(summary.by_kind)
        shifts_phrase = _format_shifts(summary.utility_shifts)

        insight_id = str(uuid.uuid4())
        snapshot.setdefault("insights", {})[insight_id] = {
            "insight_id": insight_id,
            "kind": "prevented_harm_pattern",
            "priority": 2,
            "created_at": (now - timedelta(days=rng.randint(0, 3))).isoformat(),
            "title": f"Coach prevented ~${value_dollars:,.0f} in likely waste in {org_name}",
            "description": (
                f"Across {summary.sessions_observed} observed sessions in {org_name}, "
                f"{summary.coached_sessions} were coached "
                f"({summary.interventions_total} interventions total). "
                f"Coach {shifts_phrase}; top interventions: {kinds_phrase}. "
                f"Counterfactual value: {summary.value_cents.without_coach / 100:,.0f} USD "
                f"without coach vs {summary.value_cents.with_coach / 100:,.0f} USD with coach "
                f"(delta {value_dollars:+,.0f} USD). Review the coach feed to confirm "
                f"these interventions align with the team's risk appetite."
            ),
            "user_id": top_user,
            "org_id": root_id,
            "target_org_id": None,
            "evidence_session_ids": evidence,
        }
        written += 1
    return written


def run(snapshot_path: Path, seed: int) -> None:
    # Point the firestore client at the snapshot so coach_summary reads from it.
    os.environ["LOCAL_DATA_PATH"] = str(snapshot_path)
    os.environ["DATA_SOURCE"] = "local"
    from seerai import firestore_client as fc

    fc._client = None
    fc._source = None
    fc.set_datasource("local")

    rng = random.Random(seed)
    snapshot = json.loads(snapshot_path.read_text())

    cleared = _clear_prior_insights(snapshot)
    written = emit_insights(snapshot, rng)

    snapshot_path.write_text(json.dumps(snapshot, indent=2, default=str))
    print(f"Cleared {cleared} prior prevented_harm_pattern insight(s).")
    print(f"Wrote {written} prevented_harm_pattern insight(s).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Emit prevented_harm_pattern insights on local snapshot"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "snapshot.json",
    )
    parser.add_argument("--seed", type=int, default=20260414)
    args = parser.parse_args()
    run(args.input, args.seed)


if __name__ == "__main__":
    main()
