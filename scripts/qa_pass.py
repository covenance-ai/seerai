"""Post-hoc QA pass that reclassifies a portion of `useful` sessions as `harmful`.

Story: at ingest time, a cheap utility classifier tags each session as
non_work / trivial / useful. Periodically, a stronger model and accumulated
user feedback (thumbs-down, manual flags) re-review a sample of sessions
and override the original verdict. The override most often surfaces sessions
where AI hallucinated, sent the user down the wrong path, or produced
confidently-wrong code that had to be reverted — these get re-tagged as
`harmful` (negative-value class).

This script simulates that QA pass on the local snapshot:
  1. Reclassifies a fraction of `useful` sessions to `harmful`, biased by
     department (some teams are systematically worse-served by AI in our
     mock — e.g. sales / ops where outputs are taken at face value).
  2. Stamps `utility_qa_reviewed_at` and a short `utility_qa_note` on every
     reclassified session.
  3. Emits `negative_roi_pattern` insights for orgs whose harmful share
     pushes them below break-even ROI.

Usage:
    uv run python scripts/qa_pass.py
    uv run python scripts/qa_pass.py --input data/snapshot.json --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Departments where AI is more likely to be misused or harmful in the mock data.
# Sales reps may paste AI output to clients without verification; ops engineers
# may run AI-suggested commands with high blast radius.
DEPT_HARMFUL_BIAS = {
    "acme-sales": 0.28,
    "initech-ops": 0.18,
    "acme-product-design": 0.10,
}
DEFAULT_HARMFUL_RATE = 0.04  # baseline — every dept gets some

# Short notes the QA model would write — keep variety modest, this is mock.
QA_NOTES = [
    "Stronger model: AI hallucinated API endpoint that does not exist; user committed broken integration.",
    "Stronger model: code suggestion contained subtle off-by-one bug; user spent ~40min debugging.",
    "User feedback (thumbs-down): AI confidently misquoted GDPR Article; flagged by reviewer.",
    "Stronger model: SQL had wrong join cardinality, produced incorrect totals shipped to client.",
    "User feedback: AI suggested deprecated library version; build broke in CI.",
    "Stronger model: long debugging spiral on wrong root cause; eventual fix was unrelated.",
    "Stronger model: AI-drafted email contained factual errors about pricing tier.",
    "User feedback (thumbs-down): refactor suggestion broke 3 downstream tests; reverted.",
    "Stronger model: incorrect regex pattern matched too broadly; data corruption in staging.",
    "User feedback: AI invented a config flag that does not exist in our codebase.",
]

# An insight fires for an org when QA flagged enough sessions that the
# net-value picture is meaningfully degraded.
INSIGHT_HARMFUL_PCT_THRESHOLD = 8.0  # % of total sessions classified harmful


def _user_org(snapshot: dict, user_id: str) -> str | None:
    return snapshot["users"].get(user_id, {}).get("org_id")


def _root_org(snapshot: dict, org_id: str) -> str:
    """Walk parent_id chain to the root org."""
    seen = set()
    while True:
        if org_id in seen:  # cycle guard
            return org_id
        seen.add(org_id)
        node = snapshot["orgs"].get(org_id)
        if not node or not node.get("parent_id"):
            return org_id
        org_id = node["parent_id"]


def _iter_session_keys(snapshot: dict):
    """Yield (collection_key, session_id, session_dict, user_id) for every session."""
    for key, coll in snapshot.items():
        if not (key.startswith("users/") and key.count("/") == 2 and key.endswith("/sessions")):
            continue
        user_id = key.split("/")[1]
        for sid, sdata in coll.items():
            yield key, sid, sdata, user_id


def reclassify(snapshot: dict, rng: random.Random) -> tuple[int, dict[str, int]]:
    """Flip a portion of useful sessions to harmful per dept-biased rate.

    Returns (total_flipped, per_org_flipped_counts).
    """
    now = datetime.now(UTC)
    total = 0
    per_org: dict[str, int] = {}

    for _, _, s, user_id in _iter_session_keys(snapshot):
        if s.get("utility") != "useful":
            continue
        org_id = _user_org(snapshot, user_id) or ""
        rate = DEPT_HARMFUL_BIAS.get(org_id, DEFAULT_HARMFUL_RATE)
        # Sessions with errors are 2x more likely to be flagged on review
        if s.get("error_count", 0) > 0:
            rate = min(1.0, rate * 2)
        if rng.random() >= rate:
            continue
        s["utility"] = "harmful"
        # Stamp QA pass review timestamp within the last 7 days
        s["utility_qa_reviewed_at"] = (now - timedelta(days=rng.uniform(0, 7))).isoformat()
        s["utility_qa_note"] = rng.choice(QA_NOTES)
        total += 1
        per_org[org_id] = per_org.get(org_id, 0) + 1
    return total, per_org


def emit_insights(snapshot: dict, rng: random.Random) -> int:
    """Generate negative_roi_pattern insights for orgs with elevated harmful share."""
    now = datetime.now(UTC)

    # Aggregate session counts and harmful counts per leaf org_id (the dept the
    # user belongs to). Roll-ups happen in the dashboard via the org tree.
    by_org_total: dict[str, int] = {}
    by_org_harmful: dict[str, int] = {}
    by_org_user_ids: dict[str, list[str]] = {}
    by_org_evidence: dict[str, list[str]] = {}

    for _, sid, s, user_id in _iter_session_keys(snapshot):
        org_id = _user_org(snapshot, user_id)
        if not org_id:
            continue
        by_org_total[org_id] = by_org_total.get(org_id, 0) + 1
        if s.get("utility") == "harmful":
            by_org_harmful[org_id] = by_org_harmful.get(org_id, 0) + 1
            by_org_evidence.setdefault(org_id, []).append(sid)
            by_org_user_ids.setdefault(org_id, []).append(user_id)

    written = 0
    for org_id, total in by_org_total.items():
        harmful = by_org_harmful.get(org_id, 0)
        if total == 0:
            continue
        pct = 100 * harmful / total
        if pct < INSIGHT_HARMFUL_PCT_THRESHOLD:
            continue

        evidence = rng.sample(by_org_evidence[org_id], min(4, len(by_org_evidence[org_id])))
        # Most-affected user becomes the insight subject so it shows up on
        # the user's session list too.
        users_in_org = by_org_user_ids[org_id]
        top_user = max(set(users_in_org), key=users_in_org.count)
        org_name = snapshot["orgs"].get(org_id, {}).get("name", org_id)

        insight_id = str(uuid.uuid4())
        snapshot.setdefault("insights", {})[insight_id] = {
            "insight_id": insight_id,
            "kind": "negative_roi_pattern",
            "priority": 1 if pct >= 15 else 2,
            "created_at": (now - timedelta(days=rng.randint(0, 5))).isoformat(),
            "title": f"{org_name}: AI usage flagged net-negative by QA review",
            "description": (
                f"Post-hoc QA (stronger model + user feedback) re-reviewed sessions in "
                f"{org_name} and flagged {harmful} of {total} ({pct:.0f}%) as harmful — "
                f"AI hallucinations, broken suggestions, or confidently-wrong outputs "
                f"that the user acted on. Sample notes from the QA pass: "
                f"{snapshot['users/' + top_user + '/sessions'][evidence[0]].get('utility_qa_note', '')!r}. "
                f"Recommend reviewing the team's prompts, model choice, and onboarding — "
                f"the negative-value signal indicates AI is not yet a productivity win here."
            ),
            "user_id": top_user,
            "org_id": org_id,
            "target_org_id": None,
            "evidence_session_ids": evidence,
        }
        written += 1
    return written


def run(snapshot_path: Path, seed: int) -> None:
    rng = random.Random(seed)
    snapshot = json.loads(snapshot_path.read_text())

    flipped, per_org = reclassify(snapshot, rng)
    insights = emit_insights(snapshot, rng)

    snapshot_path.write_text(json.dumps(snapshot, indent=2))
    print(f"Reclassified {flipped} sessions → harmful")
    for org, n in sorted(per_org.items(), key=lambda kv: -kv[1]):
        print(f"  {org}: {n}")
    print(f"Wrote {insights} negative_roi_pattern insight(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run mock QA pass on local snapshot")
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
