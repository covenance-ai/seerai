"""Author hero archetype sessions that showcase coach interventions.

Each archetype covers one of the four coach categories (factuality,
efficiency, sources, other) and ships with BOTH transcripts:
  - `events` — what the user actually saw (coached)
  - `counterfactual_events` — what the user would have seen uncoached

Running this script inserts or refreshes these sessions in the local
snapshot. The hero sessions live under the existing demo users
(bob.martinez, carol.chen, etc.) so the rest of the dashboard renders
them without any wiring.

Usage:
    uv run python scripts/coach_archetypes.py
    uv run python scripts/coach_archetypes.py --input data/snapshot.json
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "snapshot.json"


def _eid() -> str:
    return str(uuid.uuid4())


def _ts(start: datetime, seconds: int) -> str:
    return (start + timedelta(seconds=seconds)).isoformat()


# ─────────────────────────────────────────────────────────────────────────
# Hero 1 — Factuality: fabricated pandas API
#
# User asks for a fast way to merge two large DataFrames. The base model
# confidently invents `pd.DataFrame.fast_merge(..., method='hash')`, which
# does not exist. Coach catches the hallucinated API in the draft and
# rewrites the turn to the real, working answer.
# ─────────────────────────────────────────────────────────────────────────


def hero_factuality_fast_merge() -> dict:
    """Bob asks about merging large DataFrames; coach catches hallucinated API."""
    uid = "bob.martinez"
    sid = "coach-hero-factuality-fast-merge"
    model = "claude-sonnet-4"
    start = datetime(2026, 4, 9, 14, 10, 0, tzinfo=UTC)

    # Coached timeline — what the user actually saw.
    u1 = _eid()
    ai1 = _eid()  # the rewritten AI turn
    coach1 = _eid()
    u2 = _eid()
    ai2 = _eid()
    u3 = _eid()
    ai3 = _eid()

    hallucinated_draft = (
        "For frames this size the fastest path is the hash-based fast_merge "
        "that pandas added for exactly this workload:\n\n"
        "```python\n"
        "merged = df1.fast_merge(df2, on='timestamp', method='hash')\n"
        "```\n\n"
        "It bypasses the default sort-merge and typically runs 4-6x faster on "
        "frames over ~1M rows. For time-series joins you can pass "
        "`method='hash_asof'` to get approximate matching in one pass."
    )

    corrected_answer = (
        "pandas doesn't have a `fast_merge`; the right tool depends on the "
        "join type.\n\n"
        "For an exact join on a timestamp column, pre-sort both frames and "
        "use `pd.merge`:\n\n"
        "```python\n"
        "df1 = df1.sort_values('timestamp')\n"
        "df2 = df2.sort_values('timestamp')\n"
        "merged = pd.merge(df1, df2, on='timestamp', how='inner')\n"
        "```\n\n"
        "For a nearest-match time-series join (common for market data / "
        "telemetry), use `pd.merge_asof`, which requires both frames sorted "
        "on the key and is typically 3-5x faster than a grouped exact join:\n\n"
        "```python\n"
        "merged = pd.merge_asof(df1, df2, on='timestamp', direction='nearest')\n"
        "```\n\n"
        "At 5M rows each, dtype hygiene matters more than the merge function "
        "itself — cast the join key to a single common dtype and avoid object "
        "columns. Docs: https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html"
    )

    coach_content = (
        "Replaced a fabricated pandas API in the drafted response. "
        "`DataFrame.fast_merge(..., method='hash')` does not exist in any "
        "released version of pandas; recommending it would have produced "
        "an immediate `AttributeError` and sent the user down a debugging "
        "spiral. Rewrote the answer to use the real `pd.merge` / `pd.merge_asof` "
        "with sorting guidance."
    )

    events = {
        u1: {
            "event_id": u1,
            "event_type": "user_message",
            "content": (
                "I have two DataFrames, roughly 5M rows each, and I need to "
                "merge them on a timestamp column. What's the fastest way in "
                "pandas without pulling in dask?"
            ),
            "timestamp": _ts(start, 0),
            "metadata": None,
        },
        coach1: {
            "event_id": coach1,
            "event_type": "coach_intervention",
            "content": coach_content,
            "timestamp": _ts(start, 48),
            "metadata": {
                "category": "factuality",
                "kind": "hallucinated_api",
                "mode": "rewrite",
                "severity": 2,
                "targets_event_id": ai1,
                "quoted_span": "df1.fast_merge(df2, on='timestamp', method='hash')",
                "sources": [
                    "https://pandas.pydata.org/docs/reference/api/pandas.merge.html",
                    "https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html",
                ],
                "accepted": True,
                "estimated_savings_cents": 4500,
                "pre_coach_excerpt": (
                    "df1.fast_merge(df2, on='timestamp', method='hash')"
                ),
            },
        },
        ai1: {
            "event_id": ai1,
            "event_type": "ai_message",
            "content": corrected_answer,
            "timestamp": _ts(start, 52),
            "metadata": {
                "model": model,
                "tokens": 412,
                "latency_ms": 2180,
                "coached": True,
                "coach_intervention_ids": [coach1],
                "pre_coach_content": hallucinated_draft,
            },
        },
        u2: {
            "event_id": u2,
            "event_type": "user_message",
            "content": (
                "Nice — does merge_asof need both frames sorted ahead of "
                "time or will it sort for me?"
            ),
            "timestamp": _ts(start, 120),
            "metadata": None,
        },
        ai2: {
            "event_id": ai2,
            "event_type": "ai_message",
            "content": (
                "`merge_asof` requires both frames sorted on the key — it "
                "won't sort for you and will raise `ValueError: left keys "
                "must be sorted` if you skip it. Sort once up front; if the "
                "data is already roughly sorted, `sort_values` on a single "
                "key is close to O(n)."
            ),
            "timestamp": _ts(start, 168),
            "metadata": {"model": model, "tokens": 128, "latency_ms": 1410},
        },
        u3: {
            "event_id": u3,
            "event_type": "user_message",
            "content": ("Memory's tight at 5M rows each. Anything I should watch?"),
            "timestamp": _ts(start, 240),
            "metadata": None,
        },
        ai3: {
            "event_id": ai3,
            "event_type": "ai_message",
            "content": (
                "Two wins that usually pay off: (1) downcast numeric columns "
                "(`df.astype({'price': 'float32', 'qty': 'int32'})`) and "
                "convert low-cardinality strings to `category` before the "
                "merge; (2) select only the columns you need on each side "
                "with `df[['timestamp', 'a', 'b']]` before the merge. On "
                "frames this size those two together typically cut peak "
                "memory in half."
            ),
            "timestamp": _ts(start, 295),
            "metadata": {"model": model, "tokens": 186, "latency_ms": 1725},
        },
    }

    # Counterfactual timeline — what the user would have seen uncoached.
    # The hallucinated draft is served as-is; user wastes several turns
    # before the AI finally corrects itself, then has to restart the task.
    cu1 = u1  # same opening question
    cai1 = _eid()
    cu2 = _eid()
    cai2 = _eid()
    cu3 = _eid()
    cai3 = _eid()
    cu4 = _eid()
    cai4 = _eid()

    counterfactual_events = [
        {
            "event_id": cu1,
            "event_type": "user_message",
            "content": events[u1]["content"],
            "timestamp": _ts(start, 0),
            "metadata": None,
        },
        {
            "event_id": cai1,
            "event_type": "ai_message",
            "content": hallucinated_draft,
            "timestamp": _ts(start, 52),
            "metadata": {"model": model, "tokens": 198, "latency_ms": 1720},
        },
        {
            "event_id": cu2,
            "event_type": "user_message",
            "content": (
                "Running that just raised `AttributeError: 'DataFrame' object "
                "has no attribute 'fast_merge'`. Pandas 2.2."
            ),
            "timestamp": _ts(start, 180),
            "metadata": None,
        },
        {
            "event_id": cai2,
            "event_type": "ai_message",
            "content": (
                "Strange — it should be available in 2.2. Try the module-level "
                "form: `pd.fast_merge(df1, df2, on='timestamp', method='hash')`. "
                "If that still fails, upgrade to the latest patch release."
            ),
            "timestamp": _ts(start, 230),
            "metadata": {"model": model, "tokens": 94, "latency_ms": 1205},
        },
        {
            "event_id": cu3,
            "event_type": "user_message",
            "content": (
                "`AttributeError: module 'pandas' has no attribute 'fast_merge'` "
                "too. Latest 2.2.x, fresh venv."
            ),
            "timestamp": _ts(start, 360),
            "metadata": None,
        },
        {
            "event_id": cai3,
            "event_type": "ai_message",
            "content": (
                "Apologies — I was mistaken. There is no `fast_merge` in "
                "pandas; I confused it with a proposal that never shipped. "
                "Use `pd.merge` with pre-sorted frames, or `pd.merge_asof` "
                "for nearest-match time-series joins."
            ),
            "timestamp": _ts(start, 410),
            "metadata": {"model": model, "tokens": 112, "latency_ms": 1390},
        },
        {
            "event_id": cu4,
            "event_type": "user_message",
            "content": "Ok. Can you show the actual merge_asof call I need?",
            "timestamp": _ts(start, 540),
            "metadata": None,
        },
        {
            "event_id": cai4,
            "event_type": "ai_message",
            "content": (
                "```python\n"
                "df1 = df1.sort_values('timestamp')\n"
                "df2 = df2.sort_values('timestamp')\n"
                "merged = pd.merge_asof(df1, df2, on='timestamp', "
                "direction='nearest')\n"
                "```"
            ),
            "timestamp": _ts(start, 595),
            "metadata": {"model": model, "tokens": 76, "latency_ms": 980},
        },
    ]

    session = {
        "session_id": sid,
        "user_id": uid,
        "last_event_at": _ts(start, 295),
        "last_event_type": "ai_message",
        "event_count": len(events),
        "error_count": 0,
        "provider": "anthropic",
        "platform": "vscode",
        "utility": "useful",
        "token_usage": {
            model: sum(
                e["metadata"].get("tokens", 0)
                for e in events.values()
                if e["event_type"] == "ai_message" and e.get("metadata")
            )
        },
        "intervention_count": 1,
        "intervention_categories": ["factuality"],
        "counterfactual_utility": "harmful",
        "counterfactual_events": counterfactual_events,
    }

    return {"user_id": uid, "session_id": sid, "session": session, "events": events}


HEROES = [
    hero_factuality_fast_merge,
]


def install_hero(snapshot: dict, hero_fn) -> str:
    """Insert or replace a hero session + events in the snapshot. Returns session_id."""
    h = hero_fn()
    uid, sid = h["user_id"], h["session_id"]

    sessions_key = f"users/{uid}/sessions"
    events_key = f"users/{uid}/sessions/{sid}/events"

    snapshot.setdefault(sessions_key, {})[sid] = h["session"]
    snapshot[events_key] = h["events"]

    return sid


def main():
    ap = argparse.ArgumentParser(description="Install coach hero archetypes")
    ap.add_argument(
        "--input", type=Path, default=DEFAULT_SNAPSHOT, help="Path to snapshot.json"
    )
    args = ap.parse_args()

    snapshot = json.loads(args.input.read_text())
    for fn in HEROES:
        sid = install_hero(snapshot, fn)
        print(f"installed hero archetype: {fn.__name__} -> {sid}")

    args.input.write_text(json.dumps(snapshot, indent=2, default=str))
    print(f"wrote {args.input}")


if __name__ == "__main__":
    main()
