"""Cost efficiency endpoints.

Compares flat-rate subscription costs against API-equivalent costs
computed from actual token usage.
"""

from collections import defaultdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from seerai.entities import Event, OrgNode, Session, Subscription, User
from seerai.pricing import token_cost

router = APIRouter(tags=["cost"])


class ModelUsage(BaseModel):
    model: str
    token_count: int
    message_count: int
    api_cost: float


class UserCost(BaseModel):
    user_id: str
    org_id: str | None
    plans: list[str]
    monthly_subscription: float  # dollars
    api_equivalent: float  # dollars
    efficiency_ratio: float | None  # api/sub, None if no subscriptions
    models: list[ModelUsage]


class OrgCostSummary(BaseModel):
    org_id: str
    org_name: str
    total_monthly_subscription: float
    total_api_equivalent: float
    efficiency_ratio: float | None
    user_count: int
    users: list[UserCost]


def _user_api_cost(user_id: str) -> tuple[float, list[ModelUsage]]:
    """Sum API-equivalent cost from all AI message tokens for a user."""
    sessions = Session.for_user(user_id, order_by="last_event_at", limit=0)
    by_model: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "messages": 0})

    for session in sessions:
        events = Event.for_session(user_id, session.session_id)
        for event in events:
            if event.event_type != "ai_message" or not event.metadata:
                continue
            model = event.metadata.get("model")
            tokens = event.metadata.get("tokens")
            if not model or not tokens:
                continue
            by_model[model]["tokens"] += tokens
            by_model[model]["messages"] += 1

    models = []
    total_cost = 0.0
    for model, stats in sorted(by_model.items()):
        cost = token_cost(model, stats["tokens"])
        total_cost += cost
        models.append(
            ModelUsage(
                model=model,
                token_count=stats["tokens"],
                message_count=stats["messages"],
                api_cost=round(cost, 4),
            )
        )

    return total_cost, models


def _user_cost(user: User, subs: list[Subscription]) -> UserCost:
    monthly_sub = sum(s.monthly_cost_cents for s in subs) / 100.0
    api_equivalent, models = _user_api_cost(user.user_id)
    ratio = api_equivalent / monthly_sub if monthly_sub > 0 else None
    return UserCost(
        user_id=user.user_id,
        org_id=user.org_id,
        plans=[s.plan for s in subs],
        monthly_subscription=monthly_sub,
        api_equivalent=round(api_equivalent, 2),
        efficiency_ratio=round(ratio, 2) if ratio is not None else None,
        models=models,
    )


@router.get("/cost/org/{org_id}")
def org_cost(org_id: str) -> OrgCostSummary:
    """Cost efficiency for an org and all its descendants."""
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

    user_costs = [_user_cost(u, subs_by_user.get(u.user_id, [])) for u in users]
    user_costs.sort(key=lambda u: u.efficiency_ratio or 0, reverse=True)

    total_sub = sum(u.monthly_subscription for u in user_costs)
    total_api = sum(u.api_equivalent for u in user_costs)
    ratio = total_api / total_sub if total_sub > 0 else None

    return OrgCostSummary(
        org_id=org_id,
        org_name=org_node.name,
        total_monthly_subscription=total_sub,
        total_api_equivalent=round(total_api, 2),
        efficiency_ratio=round(ratio, 2) if ratio is not None else None,
        user_count=len(user_costs),
        users=user_costs,
    )
