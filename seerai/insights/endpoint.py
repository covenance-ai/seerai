"""AI insights endpoints — surface patterns about employees."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from seerai.entities import Insight, OrgNode

router = APIRouter(tags=["insights"])


class FlagRequest(BaseModel):
    note: str | None = None


@router.get("/insights")
def list_insights(
    user_id: str | None = None,
    org_id: str | None = None,
    archived: bool = False,
    flagged: bool = False,
) -> list[Insight]:
    """List insights sorted by priority ASC, created_at DESC.

    Filters:
    - user_id: insights about a specific user
    - org_id: insights in this org or any descendant (subject's org only;
      target_org_id can point outside, but those insights belong to the
      subject's company)
    - archived: when True, only dismissed insights; otherwise only active
    - flagged: when True, only insights flagged for seer.ai support review
    """
    all_insights = Insight.list(order_by=None, limit=0)

    if archived:
        all_insights = [i for i in all_insights if i.dismissed_at is not None]
    else:
        all_insights = [i for i in all_insights if i.dismissed_at is None]

    if flagged:
        all_insights = [i for i in all_insights if i.flagged_for_support_at is not None]

    if user_id:
        all_insights = [i for i in all_insights if i.user_id == user_id]

    if org_id:
        descendants = OrgNode.query("path", "array_contains", org_id)
        org_ids = {n.org_id for n in descendants}
        all_insights = [i for i in all_insights if i.org_id in org_ids]

    all_insights.sort(key=lambda i: (i.priority, -i.created_at.timestamp()))
    return all_insights


@router.post("/insights/{insight_id}/dismiss")
def dismiss_insight(insight_id: str) -> Insight:
    """Mark an insight as archived. Idempotent — re-dismissing keeps original timestamp."""
    insight = Insight.get(insight_id)
    if insight is None:
        raise HTTPException(status_code=404, detail=f"Insight {insight_id} not found")
    if insight.dismissed_at is None:
        insight.dismissed_at = datetime.now(UTC)
        insight.sync()
    return insight


@router.post("/insights/{insight_id}/restore")
def restore_insight(insight_id: str) -> Insight:
    """Move an archived insight back to active."""
    insight = Insight.get(insight_id)
    if insight is None:
        raise HTTPException(status_code=404, detail=f"Insight {insight_id} not found")
    if insight.dismissed_at is not None:
        insight.dismissed_at = None
        insight.sync()
    return insight


@router.post("/insights/{insight_id}/flag")
def flag_insight(insight_id: str, req: FlagRequest) -> Insight:
    """Flag an insight for seer.ai support review (e.g. wrong analysis)."""
    insight = Insight.get(insight_id)
    if insight is None:
        raise HTTPException(status_code=404, detail=f"Insight {insight_id} not found")
    insight.flagged_for_support_at = datetime.now(UTC)
    insight.flag_note = req.note
    insight.sync()
    return insight


@router.post("/insights/{insight_id}/unflag")
def unflag_insight(insight_id: str) -> Insight:
    """Withdraw a support flag."""
    insight = Insight.get(insight_id)
    if insight is None:
        raise HTTPException(status_code=404, detail=f"Insight {insight_id} not found")
    insight.flagged_for_support_at = None
    insight.flag_note = None
    insight.sync()
    return insight
