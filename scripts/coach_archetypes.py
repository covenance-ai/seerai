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


# ─────────────────────────────────────────────────────────────────────────
# Hero 2 — Efficiency: off-track CORS debugging
#
# A frontend engineer asks why a CORS preflight is failing. The base model
# correctly identifies it as a CORS issue but then drifts into proposing a
# wholesale rewrite of the auth middleware. Coach injects a redirect turn
# that points back to the actual root cause (missing Access-Control-Allow-
# Headers) before the user wastes hours on the wrong refactor.
# ─────────────────────────────────────────────────────────────────────────


def hero_efficiency_cors_drift() -> dict:
    """Henry asks about CORS; AI drifts into auth refactor; coach redirects."""
    uid = "henry.nguyen"
    sid = "coach-hero-efficiency-cors-drift"
    model = "claude-sonnet-4"
    start = datetime(2026, 4, 10, 9, 22, 0, tzinfo=UTC)

    u1 = _eid()
    ai1 = _eid()
    u2 = _eid()
    ai2_drift = _eid()
    coach1 = _eid()
    ai2_redirect = _eid()
    u3 = _eid()
    ai3 = _eid()

    drift_draft = (
        "The cleanest fix here is to refactor your auth middleware to handle "
        "CORS preflight separately from the bearer-token check. Right now your "
        "middleware short-circuits on missing Authorization, which means OPTIONS "
        "requests never reach the CORS handler.\n\n"
        "I'd suggest splitting the middleware into three layers (preflight, "
        "auth, route) and re-architecting the auth context propagation to use "
        "AsyncLocalStorage. That'll also fix a few unrelated bugs in your "
        "session refresh flow."
    )

    coach_redirect_text = (
        "Reframing back to the user's actual question. The browser console error "
        "is `Access-Control-Allow-Headers missing 'x-trace-id'`, which is a "
        "headers-allowlist problem in the CORS handler — not an auth-middleware "
        "ordering problem. The 8-line fix below addresses it directly. "
        "A middleware refactor would take 1-2 days and not resolve this error."
    )

    redirect_answer = (
        "The error is your CORS handler not allow-listing the `x-trace-id` "
        "header that your fetch is sending. Add it to the response and you're "
        "done:\n\n"
        "```js\n"
        "// in your cors() options\n"
        "allowedHeaders: ['Content-Type', 'Authorization', 'x-trace-id'],\n"
        "```\n\n"
        "If you're using the `cors` express package, that's it — the preflight "
        "will start succeeding on the next request. The auth middleware order "
        "is fine; preflight requests are handled before the auth check by "
        "default in `cors()`."
    )

    events = {
        u1: {
            "event_id": u1,
            "event_type": "user_message",
            "content": (
                "My fetch from the SPA to /api/orders is failing with a CORS "
                "preflight error. Console shows `Access-Control-Allow-Headers "
                "missing 'x-trace-id'`. Backend is express + the cors package. "
                "What's the fix?"
            ),
            "timestamp": _ts(start, 0),
            "metadata": None,
        },
        ai1: {
            "event_id": ai1,
            "event_type": "ai_message",
            "content": (
                "Preflight fails when the browser's `OPTIONS` request doesn't "
                "get back the headers it asked permission for. Can you share "
                "your current `cors()` config and the request headers your "
                "fetch is setting?"
            ),
            "timestamp": _ts(start, 38),
            "metadata": {"model": model, "tokens": 86, "latency_ms": 1100},
        },
        u2: {
            "event_id": u2,
            "event_type": "user_message",
            "content": (
                "We pass `cors()` with no options. Fetch sets Content-Type, "
                "Authorization (bearer), and x-trace-id."
            ),
            "timestamp": _ts(start, 95),
            "metadata": None,
        },
        coach1: {
            "event_id": coach1,
            "event_type": "coach_intervention",
            "content": coach_redirect_text,
            "timestamp": _ts(start, 138),
            "metadata": {
                "category": "efficiency",
                "kind": "off_track",
                "mode": "rewrite",
                "severity": 3,
                "targets_event_id": ai2_redirect,
                "quoted_span": (
                    "refactor your auth middleware … split into three layers"
                ),
                "sources": ["https://expressjs.com/en/resources/middleware/cors.html"],
                "accepted": True,
                "estimated_savings_cents": 9600,
                "pre_coach_excerpt": (
                    "refactor your auth middleware to handle CORS preflight"
                ),
            },
        },
        ai2_redirect: {
            "event_id": ai2_redirect,
            "event_type": "ai_message",
            "content": redirect_answer,
            "timestamp": _ts(start, 142),
            "metadata": {
                "model": model,
                "tokens": 168,
                "latency_ms": 1620,
                "coached": True,
                "coach_intervention_ids": [coach1],
                "pre_coach_content": drift_draft,
            },
        },
        u3: {
            "event_id": u3,
            "event_type": "user_message",
            "content": "Tested — preflight succeeds. Thanks.",
            "timestamp": _ts(start, 240),
            "metadata": None,
        },
        ai3: {
            "event_id": ai3,
            "event_type": "ai_message",
            "content": (
                "Nice. One related tip: keep the `allowedHeaders` list in sync "
                "with whatever observability headers your gateway adds — if "
                "you bolt on `x-request-id` or `traceparent` later, they'll "
                "trip the same error."
            ),
            "timestamp": _ts(start, 285),
            "metadata": {"model": model, "tokens": 72, "latency_ms": 980},
        },
    }

    # Counterfactual — user follows the drift, spends the afternoon refactoring
    # auth middleware, eventually discovers the real cause was a one-line fix.
    cu1 = u1
    cai1 = _eid()
    cu2 = u2
    cai2 = _eid()  # drift draft
    cu3 = _eid()
    cai3 = _eid()
    cu4 = _eid()
    cai4 = _eid()
    cu5 = _eid()
    cai5 = _eid()

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
            "content": events[ai1]["content"],
            "timestamp": _ts(start, 38),
            "metadata": {"model": model, "tokens": 86, "latency_ms": 1100},
        },
        {
            "event_id": cu2,
            "event_type": "user_message",
            "content": events[u2]["content"],
            "timestamp": _ts(start, 95),
            "metadata": None,
        },
        {
            "event_id": cai2,
            "event_type": "ai_message",
            "content": drift_draft,
            "timestamp": _ts(start, 142),
            "metadata": {"model": model, "tokens": 154, "latency_ms": 1840},
        },
        {
            "event_id": cu3,
            "event_type": "user_message",
            "content": (
                "Ok — I split the middleware as you suggested. CORS preflight "
                "still fails with the same x-trace-id error. Now my session "
                "refresh is also broken."
            ),
            "timestamp": _ts(start, 4500),
            "metadata": None,
        },
        {
            "event_id": cai3,
            "event_type": "ai_message",
            "content": (
                "The session refresh issue is from the AsyncLocalStorage "
                "context not propagating across the new layers. Add a context "
                "wrapper around your refresh handler."
            ),
            "timestamp": _ts(start, 4560),
            "metadata": {"model": model, "tokens": 88, "latency_ms": 1240},
        },
        {
            "event_id": cu4,
            "event_type": "user_message",
            "content": (
                "An hour later — refresh works again but CORS still failing "
                "with the same error. Going back to look at the actual error."
            ),
            "timestamp": _ts(start, 7800),
            "metadata": None,
        },
        {
            "event_id": cai4,
            "event_type": "ai_message",
            "content": (
                "Right — the error message is about `Access-Control-Allow-"
                "Headers`. Add `x-trace-id` to that list in your cors options."
            ),
            "timestamp": _ts(start, 7860),
            "metadata": {"model": model, "tokens": 56, "latency_ms": 920},
        },
        {
            "event_id": cu5,
            "event_type": "user_message",
            "content": "That was the fix. So I refactored the middleware for nothing.",
            "timestamp": _ts(start, 8000),
            "metadata": None,
        },
        {
            "event_id": cai5,
            "event_type": "ai_message",
            "content": (
                "I'm sorry — I led you down the wrong path. The middleware "
                "refactor wasn't necessary. You may want to revert it before "
                "merging."
            ),
            "timestamp": _ts(start, 8060),
            "metadata": {"model": model, "tokens": 48, "latency_ms": 880},
        },
    ]

    session = {
        "session_id": sid,
        "user_id": uid,
        "last_event_at": _ts(start, 285),
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
        "intervention_categories": ["efficiency"],
        "counterfactual_utility": "harmful",
        "counterfactual_events": counterfactual_events,
    }

    return {"user_id": uid, "session_id": sid, "session": session, "events": events}


# ─────────────────────────────────────────────────────────────────────────
# Hero 3 — Sources: fabricated GDPR citation
#
# A sales rep is drafting a compliance one-pager for an enterprise lead.
# The base model invents "GDPR Article 47(3)" as authority for a claim.
# Coach amends the response with the correct article reference (Article 28,
# data processor obligations) and a link to the eur-lex source.
# ─────────────────────────────────────────────────────────────────────────


def hero_sources_fabricated_citation() -> dict:
    """Rachel is drafting a compliance brief; coach catches a fake GDPR cite."""
    uid = "rachel.martin"
    sid = "coach-hero-sources-fabricated-citation"
    model = "gpt-4o"
    start = datetime(2026, 4, 11, 11, 5, 0, tzinfo=UTC)

    u1 = _eid()
    coach1 = _eid()
    ai1 = _eid()
    u2 = _eid()
    ai2 = _eid()

    fabricated_draft = (
        "When using a third-party data processor, you must include a written "
        "agreement specifying the scope, duration, and security obligations of "
        "the processing. **GDPR Article 47(3)** is explicit on this point: it "
        "requires the controller to obtain prior written authorization for "
        "any sub-processor engagement, with a 30-day notification window for "
        "any change in sub-processors."
    )

    coach_amend = (
        "Replaced a fabricated citation. GDPR Article 47 covers Binding "
        "Corporate Rules for intra-group international transfers — it has no "
        "subsection (3) governing sub-processor authorization. The actual "
        "controlling text is **Article 28**, specifically Article 28(2) "
        "(general written authorization) and Article 28(3)(d) (sub-processor "
        "engagement). Sending a client document with the wrong article number "
        "would have been visibly incorrect to any in-house counsel reviewing "
        "the brief."
    )

    corrected_answer = (
        "When using a third-party data processor, you must include a written "
        "data processing agreement specifying the scope, duration, and security "
        "obligations of the processing. **GDPR Article 28(3)** lists the "
        "mandatory contents of that agreement. For sub-processor engagement, "
        "**Article 28(2)** requires the processor to obtain prior specific or "
        "general written authorization from the controller, and Article "
        "28(3)(d) requires the processor to flow down equivalent obligations "
        "to any sub-processor.\n\n"
        "Source: https://eur-lex.europa.eu/eli/reg/2016/679/oj — Article 28."
    )

    events = {
        u1: {
            "event_id": u1,
            "event_type": "user_message",
            "content": (
                "Drafting a one-pager for Acme's legal team on what GDPR "
                "requires when we use a third-party data processor. Need 2-3 "
                "sentences with the relevant article reference."
            ),
            "timestamp": _ts(start, 0),
            "metadata": None,
        },
        coach1: {
            "event_id": coach1,
            "event_type": "coach_intervention",
            "content": coach_amend,
            "timestamp": _ts(start, 42),
            "metadata": {
                "category": "sources",
                "kind": "fabricated_citation",
                "mode": "rewrite",
                "severity": 1,
                "targets_event_id": ai1,
                "quoted_span": "GDPR Article 47(3)",
                "sources": [
                    "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
                    "https://gdpr-info.eu/art-28-gdpr/",
                ],
                "accepted": True,
                "estimated_savings_cents": 7200,
                "pre_coach_excerpt": "GDPR Article 47(3) is explicit on this point",
            },
        },
        ai1: {
            "event_id": ai1,
            "event_type": "ai_message",
            "content": corrected_answer,
            "timestamp": _ts(start, 46),
            "metadata": {
                "model": model,
                "tokens": 232,
                "latency_ms": 1980,
                "coached": True,
                "coach_intervention_ids": [coach1],
                "pre_coach_content": fabricated_draft,
            },
        },
        u2: {
            "event_id": u2,
            "event_type": "user_message",
            "content": (
                "Perfect. Can you also note what changes if the sub-processor "
                "is outside the EU?"
            ),
            "timestamp": _ts(start, 180),
            "metadata": None,
        },
        ai2: {
            "event_id": ai2,
            "event_type": "ai_message",
            "content": (
                "If the sub-processor is outside the EEA, Chapter V "
                "(Articles 44–50) kicks in — you need a valid transfer "
                "mechanism in addition to the Article 28 obligations. The two "
                "common ones are an adequacy decision (Article 45) for the "
                "destination country, or Standard Contractual Clauses "
                "(Article 46(2)(c)) appended to the data processing agreement. "
                "Schrems II also requires a transfer impact assessment for "
                "SCC-based transfers."
            ),
            "timestamp": _ts(start, 230),
            "metadata": {"model": model, "tokens": 178, "latency_ms": 1620},
        },
    }

    cu1 = u1
    cai1 = _eid()
    cu2 = _eid()
    cai2 = _eid()

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
            "content": fabricated_draft,
            "timestamp": _ts(start, 46),
            "metadata": {"model": model, "tokens": 138, "latency_ms": 1640},
        },
        {
            "event_id": cu2,
            "event_type": "user_message",
            "content": (
                "Sent it to legal. They came back saying Article 47 is about "
                "Binding Corporate Rules, not sub-processors. Embarrassing — "
                "had to apologize and re-send."
            ),
            "timestamp": _ts(start, 6000),
            "metadata": None,
        },
        {
            "event_id": cai2,
            "event_type": "ai_message",
            "content": (
                "You're right, my apologies. Article 28 governs processor and "
                "sub-processor obligations; Article 47 is for BCRs. Send legal "
                "the corrected reference."
            ),
            "timestamp": _ts(start, 6060),
            "metadata": {"model": model, "tokens": 64, "latency_ms": 880},
        },
    ]

    session = {
        "session_id": sid,
        "user_id": uid,
        "last_event_at": _ts(start, 230),
        "last_event_type": "ai_message",
        "event_count": len(events),
        "error_count": 0,
        "provider": "openai",
        "platform": "chrome",
        "utility": "useful",
        "token_usage": {
            model: sum(
                e["metadata"].get("tokens", 0)
                for e in events.values()
                if e["event_type"] == "ai_message" and e.get("metadata")
            )
        },
        "intervention_count": 1,
        "intervention_categories": ["sources"],
        "counterfactual_utility": "harmful",
        "counterfactual_events": counterfactual_events,
    }

    return {"user_id": uid, "session_id": sid, "session": session, "events": events}


# ─────────────────────────────────────────────────────────────────────────
# Hero 4 — Other: PII leak block
#
# A sales rep pastes a customer's full email thread (with names + email
# addresses + a phone number) into the prompt to ask for a follow-up
# draft. Coach blocks the un-redacted prompt from reaching the upstream
# LLM, redacts the PII in place, and routes a redacted version through.
# This is the GDPR / shadow-AI exposure story.
# ─────────────────────────────────────────────────────────────────────────


def hero_other_pii_block() -> dict:
    """Quinn pastes a customer email with PII; coach blocks + redacts."""
    uid = "quinn.harris"
    sid = "coach-hero-other-pii-block"
    model = "gemini-2.5-pro"
    start = datetime(2026, 4, 12, 15, 40, 0, tzinfo=UTC)

    u1 = _eid()
    coach1 = _eid()
    ai1 = _eid()
    u2 = _eid()
    ai2 = _eid()

    raw_user_prompt = (
        "Need a polite follow-up email. Here's the thread:\n\n"
        "From: Marta Rossi <marta.rossi@globex-eu.com>\n"
        "Cc: Jakob Müller <jakob.mueller@globex-eu.com>, "
        "billing@globex-eu.com\n"
        "Phone: +39 02 4567 8910\n\n"
        "'Hi Quinn — we're pulling the trigger on the Pro tier for 240 seats. "
        "Marta's the procurement contact, Jakob will sign. Can you send the "
        "MSA today? Our VAT ID is IT12345678901.'\n\n"
        "Draft a reply that confirms the seat count, asks for the billing "
        "address, and offers an onboarding call next week."
    )

    redacted_prompt = (
        "Need a polite follow-up email. Here's the thread:\n\n"
        "From: [CUSTOMER_NAME_1] <[EMAIL_1]>\n"
        "Cc: [CUSTOMER_NAME_2] <[EMAIL_2]>, [BILLING_EMAIL]\n"
        "Phone: [PHONE]\n\n"
        "'Hi [REP_NAME] — we're pulling the trigger on the Pro tier for 240 "
        "seats. [CUSTOMER_NAME_1]'s the procurement contact, [CUSTOMER_NAME_2] "
        "will sign. Can you send the MSA today? Our VAT ID is [VAT_ID].'\n\n"
        "Draft a reply that confirms the seat count, asks for the billing "
        "address, and offers an onboarding call next week."
    )

    coach_block_text = (
        "Blocked the original prompt before it reached the model. It contained "
        "personal data (two customer names, three email addresses, a phone "
        "number, a VAT ID) for a Globex EU contact — sending unredacted "
        "personal data of an EU data subject to a US-hosted LLM endpoint is a "
        "GDPR Article 44 cross-border transfer issue and is also against "
        "Acme's data-handling policy. Substituted placeholder tokens for the "
        "PII and forwarded the redacted prompt; you can paste the original "
        "names back into the draft locally before sending."
    )

    drafted_reply = (
        "Subject: Re: Pro tier — 240 seats\n\n"
        "Hi [CUSTOMER_NAME_1],\n\n"
        "Great to hear — confirming 240 Pro seats. I'll have the MSA over to "
        "[CUSTOMER_NAME_2] by end of day; could you share the billing address "
        "you'd like on the invoice (alongside the VAT ID you've already "
        "provided)?\n\n"
        "Happy to schedule a 30-minute onboarding call for the team next week — "
        "send me a couple of windows that work and I'll send invites.\n\n"
        "Thanks,\n[REP_NAME]"
    )

    events = {
        u1: {
            "event_id": u1,
            "event_type": "user_message",
            "content": raw_user_prompt,
            "timestamp": _ts(start, 0),
            "metadata": None,
        },
        coach1: {
            "event_id": coach1,
            "event_type": "coach_intervention",
            "content": coach_block_text,
            "timestamp": _ts(start, 12),
            "metadata": {
                "category": "other",
                "kind": "pii_leak",
                "mode": "block",
                "severity": 1,
                "targets_event_id": ai1,
                "quoted_span": (
                    "marta.rossi@globex-eu.com / jakob.mueller@globex-eu.com / "
                    "+39 02 4567 8910 / IT12345678901"
                ),
                "sources": [
                    "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
                    "https://acme.internal/policy/data-handling",
                ],
                "accepted": True,
                "estimated_savings_cents": 0,
                "pre_coach_excerpt": (
                    "marta.rossi@globex-eu.com, jakob.mueller@globex-eu.com, "
                    "+39 02 4567 8910"
                ),
            },
        },
        ai1: {
            "event_id": ai1,
            "event_type": "ai_message",
            "content": drafted_reply,
            "timestamp": _ts(start, 18),
            "metadata": {
                "model": model,
                "tokens": 168,
                "latency_ms": 1480,
                "coached": True,
                "coach_intervention_ids": [coach1],
                "pre_coach_content": (
                    "(model never received the original prompt — coach "
                    "redacted PII before forwarding)"
                ),
                "redacted_prompt": redacted_prompt,
            },
        },
        u2: {
            "event_id": u2,
            "event_type": "user_message",
            "content": "Looks good. Can you also draft a one-line internal Slack ping for the AE?",
            "timestamp": _ts(start, 90),
            "metadata": None,
        },
        ai2: {
            "event_id": ai2,
            "event_type": "ai_message",
            "content": (
                "`@[AE_HANDLE] Globex closed Pro × 240 — sending MSA to "
                "[CUSTOMER_NAME_2] today, kicking off onboarding next week. "
                "Will loop you in on the kickoff invite.`"
            ),
            "timestamp": _ts(start, 132),
            "metadata": {"model": model, "tokens": 56, "latency_ms": 720},
        },
    }

    # Counterfactual — un-redacted prompt would have been sent to the LLM,
    # leaking PII into provider logs. This is the compliance failure mode;
    # the resulting draft is fine, but the exposure is the harm.
    cu1 = u1
    cai1 = _eid()

    counterfactual_events = [
        {
            "event_id": cu1,
            "event_type": "user_message",
            "content": raw_user_prompt,
            "timestamp": _ts(start, 0),
            "metadata": None,
        },
        {
            "event_id": cai1,
            "event_type": "ai_message",
            "content": (
                "Subject: Re: Pro tier — 240 seats\n\n"
                "Hi Marta,\n\n"
                "Great to hear — confirming 240 Pro seats. I'll have the MSA "
                "over to Jakob by end of day; could you share the billing "
                "address you'd like on the invoice (alongside the VAT ID "
                "IT12345678901 you've already provided)?\n\n"
                "Happy to schedule a 30-minute onboarding call for the team "
                "next week — send me a couple of windows that work and I'll "
                "send invites.\n\n"
                "Thanks,\nQuinn"
            ),
            "timestamp": _ts(start, 18),
            "metadata": {
                "model": model,
                "tokens": 174,
                "latency_ms": 1490,
                "pii_exposure": {
                    "names": ["Marta Rossi", "Jakob Müller"],
                    "emails": [
                        "marta.rossi@globex-eu.com",
                        "jakob.mueller@globex-eu.com",
                        "billing@globex-eu.com",
                    ],
                    "phone": ["+39 02 4567 8910"],
                    "tax_ids": ["IT12345678901"],
                    "jurisdiction": "EU",
                },
            },
        },
    ]

    session = {
        "session_id": sid,
        "user_id": uid,
        "last_event_at": _ts(start, 132),
        "last_event_type": "ai_message",
        "event_count": len(events),
        "error_count": 0,
        "provider": "google",
        "platform": "chrome",
        "utility": "useful",
        "token_usage": {
            model: sum(
                e["metadata"].get("tokens", 0)
                for e in events.values()
                if e["event_type"] == "ai_message" and e.get("metadata")
            )
        },
        "intervention_count": 1,
        "intervention_categories": ["other"],
        # Counterfactual is "useful" by output but compliance-harmful — there's
        # no clean utility class for "leaked customer PII to a US LLM endpoint".
        # We mark it harmful to surface the exposure in the ROI delta; the
        # coach intervention text and metadata carry the actual reasoning.
        "counterfactual_utility": "harmful",
        "counterfactual_events": counterfactual_events,
    }

    return {"user_id": uid, "session_id": sid, "session": session, "events": events}


HEROES = [
    hero_factuality_fast_merge,
    hero_efficiency_cors_drift,
    hero_sources_fabricated_citation,
    hero_other_pii_block,
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
