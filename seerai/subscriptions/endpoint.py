import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from seerai.entities import Subscription

router = APIRouter(tags=["subscriptions"])


class CreateSubscriptionRequest(BaseModel):
    user_id: str
    provider: str
    plan: str
    monthly_cost_cents: int
    currency: str = "USD"
    started_at: datetime | None = None


@router.post("/subscriptions")
def create_subscription(req: CreateSubscriptionRequest) -> Subscription:
    sub = Subscription(
        subscription_id=str(uuid.uuid4()),
        user_id=req.user_id,
        provider=req.provider,
        plan=req.plan,
        monthly_cost_cents=req.monthly_cost_cents,
        currency=req.currency,
        started_at=req.started_at or datetime.now(UTC),
    )
    sub.save(merge=False)
    return sub


@router.get("/subscriptions")
def list_subscriptions(user_id: str | None = None) -> list[Subscription]:
    if user_id:
        return Subscription.query("user_id", "==", user_id)
    return Subscription.list(order_by=None, limit=0)


@router.delete("/subscriptions/{subscription_id}")
def delete_subscription(subscription_id: str) -> dict:
    sub = Subscription.get(subscription_id)
    if not sub:
        raise HTTPException(404, "Subscription not found")
    sub.delete()
    return {"deleted": subscription_id}
