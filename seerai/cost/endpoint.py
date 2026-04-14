"""Cost efficiency and ROI endpoints.

Compares flat-rate subscription costs against:
1. API-equivalent costs computed from actual token usage
2. Estimated value generated, using: hourly_rate × log2(session_size) × utility_score
"""

import math
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from seerai.entities import Event, OrgNode, Session, Subscription, User
from seerai.pricing import token_cost

router = APIRouter(tags=["cost"])

UTILITY_SCORES = {"non_work": 0, "trivial": 1, "useful": 5}


def session_value(hourly_rate: float, event_count: int, utility: str | None) -> float:
    """Estimated value of a session to the company.

    Formula: hourly_rate × log2(event_count) × utility_score
    """
    if not utility or utility not in UTILITY_SCORES:
        return 0.0
    score = UTILITY_SCORES[utility]
    if score == 0 or event_count < 1:
        return 0.0
    return hourly_rate * math.log2(max(event_count, 1)) * score


class ModelUsage(BaseModel):
    model: str
    token_count: int
    api_cost: float


class UtilityBreakdown(BaseModel):
    non_work: int = 0
    trivial: int = 0
    useful: int = 0
    unclassified: int = 0


class UserCost(BaseModel):
    user_id: str
    org_id: str | None
    hourly_rate: float | None
    plans: list[str]
    monthly_subscription: float
    api_equivalent: float
    efficiency_ratio: float | None
    estimated_value: float
    roi: float | None  # value / subscription cost
    session_count: int
    utility_breakdown: UtilityBreakdown
    models: list[ModelUsage]


class OrgCostSummary(BaseModel):
    org_id: str
    org_name: str
    total_monthly_subscription: float
    total_api_equivalent: float
    efficiency_ratio: float | None
    total_estimated_value: float
    roi: float | None
    user_count: int
    utility_breakdown: UtilityBreakdown
    users: list[UserCost]


def _user_cost(user: User, sessions: list[Session], subs: list[Subscription]) -> UserCost:
    """Compute cost metrics from session-level token_usage (no event scanning)."""
    monthly_sub = sum(s.monthly_cost_cents for s in subs) / 100.0

    by_model: dict[str, int] = defaultdict(int)
    rate = user.hourly_rate or 0.0
    total_value = 0.0
    breakdown = UtilityBreakdown()

    for s in sessions:
        # Accumulate token usage from session-level data
        if s.token_usage:
            for model, tokens in s.token_usage.items():
                by_model[model] += tokens

        # Utility breakdown and value
        if s.utility == "non_work":
            breakdown.non_work += 1
        elif s.utility == "trivial":
            breakdown.trivial += 1
        elif s.utility == "useful":
            breakdown.useful += 1
        else:
            breakdown.unclassified += 1
        total_value += session_value(rate, s.event_count, s.utility)

    models = []
    api_equivalent = 0.0
    for model, tokens in sorted(by_model.items()):
        cost = token_cost(model, tokens)
        api_equivalent += cost
        models.append(ModelUsage(model=model, token_count=tokens, api_cost=round(cost, 4)))

    eff_ratio = api_equivalent / monthly_sub if monthly_sub > 0 else None
    roi = total_value / monthly_sub if monthly_sub > 0 else None

    return UserCost(
        user_id=user.user_id,
        org_id=user.org_id,
        hourly_rate=user.hourly_rate,
        plans=[s.plan for s in subs],
        monthly_subscription=monthly_sub,
        api_equivalent=round(api_equivalent, 2),
        efficiency_ratio=round(eff_ratio, 2) if eff_ratio is not None else None,
        estimated_value=round(total_value, 2),
        roi=round(roi, 2) if roi is not None else None,
        session_count=len(sessions),
        utility_breakdown=breakdown,
        models=models,
    )


@router.get("/cost/user/{user_id}")
def user_cost(user_id: str) -> UserCost:
    """Cost efficiency and ROI for a single user."""
    user = User.get(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    sessions = Session.for_user(user_id, order_by="last_event_at", limit=0)
    all_subs = Subscription.list(order_by=None, limit=0)
    subs = [s for s in all_subs if s.user_id == user_id and s.ended_at is None]
    return _user_cost(user, sessions, subs)


@router.get("/cost/org/{org_id}")
def org_cost(org_id: str) -> OrgCostSummary:
    """Cost efficiency and ROI for an org and all its descendants."""
    descendants = OrgNode.query("path", "array_contains", org_id)
    if not any(n.org_id == org_id for n in descendants):
        raise HTTPException(404, "Org not found")

    org_node = next(n for n in descendants if n.org_id == org_id)
    org_ids = [n.org_id for n in descendants]

    # Load all users in this org tree
    users: list[User] = []
    for i in range(0, len(org_ids), 30):
        batch = org_ids[i : i + 30]
        users.extend(User.query("org_id", "in", batch))

    # Load all active subscriptions for these users
    all_subs = Subscription.list(order_by=None, limit=0)
    user_ids = {u.user_id for u in users}
    subs_by_user: dict[str, list[Subscription]] = defaultdict(list)
    for s in all_subs:
        if s.user_id in user_ids and s.ended_at is None:
            subs_by_user[s.user_id].append(s)

    user_costs = [
        _user_cost(
            u,
            Session.for_user(u.user_id, order_by="last_event_at", limit=0),
            subs_by_user.get(u.user_id, []),
        )
        for u in users
    ]
    user_costs.sort(key=lambda u: u.roi or 0, reverse=True)

    total_sub = sum(u.monthly_subscription for u in user_costs)
    total_api = sum(u.api_equivalent for u in user_costs)
    total_value = sum(u.estimated_value for u in user_costs)
    eff_ratio = total_api / total_sub if total_sub > 0 else None
    roi = total_value / total_sub if total_sub > 0 else None

    org_breakdown = UtilityBreakdown(
        non_work=sum(u.utility_breakdown.non_work for u in user_costs),
        trivial=sum(u.utility_breakdown.trivial for u in user_costs),
        useful=sum(u.utility_breakdown.useful for u in user_costs),
        unclassified=sum(u.utility_breakdown.unclassified for u in user_costs),
    )

    return OrgCostSummary(
        org_id=org_id,
        org_name=org_node.name,
        total_monthly_subscription=total_sub,
        total_api_equivalent=round(total_api, 2),
        efficiency_ratio=round(eff_ratio, 2) if eff_ratio is not None else None,
        total_estimated_value=round(total_value, 2),
        roi=round(roi, 2) if roi is not None else None,
        user_count=len(user_costs),
        utility_breakdown=org_breakdown,
        users=user_costs,
    )


@router.post("/cost/backfill-token-usage")
def backfill_token_usage() -> dict:
    """One-time backfill: compute token_usage from events for sessions that lack it."""
    from seerai.firestore_client import get_firestore_client

    db = get_firestore_client()
    users = User.list(order_by=None, limit=0)
    updated = 0
    for user in users:
        sessions = Session.for_user(user.user_id, order_by="last_event_at", limit=0)
        for session in sessions:
            if session.token_usage:
                continue
            events = Event.for_session(user.user_id, session.session_id)
            usage: dict[str, int] = defaultdict(int)
            for event in events:
                if event.event_type != "ai_message" or not event.metadata:
                    continue
                model = event.metadata.get("model")
                tokens = event.metadata.get("tokens")
                if model and tokens:
                    usage[model] += tokens
            if usage:
                ref = Session._doc_ref(
                    db, session.session_id, Session.parent_path(user.user_id)
                )
                ref.update({"token_usage": dict(usage)})
                updated += 1
    return {"updated": updated}
