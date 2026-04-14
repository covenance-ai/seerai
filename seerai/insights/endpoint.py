"""AI insights endpoints — surface patterns about employees."""

from fastapi import APIRouter

from seerai.entities import Insight, OrgNode

router = APIRouter(tags=["insights"])


@router.get("/insights")
def list_insights(user_id: str | None = None, org_id: str | None = None) -> list[Insight]:
    """List insights sorted by priority ASC, created_at DESC.

    Optional filters:
    - user_id: insights about a specific user
    - org_id: insights in this org or any descendant
    """
    all_insights = Insight.list(order_by=None, limit=0)

    if user_id:
        all_insights = [i for i in all_insights if i.user_id == user_id]

    if org_id:
        descendants = OrgNode.query("path", "array_contains", org_id)
        org_ids = {n.org_id for n in descendants}
        all_insights = [
            i
            for i in all_insights
            if i.org_id in org_ids or i.target_org_id in org_ids
        ]

    all_insights.sort(key=lambda i: (i.priority, -i.created_at.timestamp()))
    return all_insights
