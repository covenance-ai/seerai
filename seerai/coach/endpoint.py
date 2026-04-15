"""Coach API — aggregate intervention metrics + recent feed."""

from __future__ import annotations

from fastapi import APIRouter

from seerai.coach.analytics import (
    CoachFeedItem,
    CoachSummary,
    coach_feed,
    coach_summary,
)
from seerai.entities import CoachCategory

router = APIRouter(tags=["coach"])


@router.get("/coach/summary")
def get_coach_summary(
    user_id: str | None = None,
    org_id: str | None = None,
    category: CoachCategory | None = None,
) -> CoachSummary:
    """Without · with · delta KPIs for the filter scope."""
    return coach_summary(user_id=user_id, org_id=org_id, category=category)


@router.get("/coach/feed")
def get_coach_feed(
    user_id: str | None = None,
    org_id: str | None = None,
    category: CoachCategory | None = None,
    limit: int = 50,
) -> list[CoachFeedItem]:
    """Most-recent coach interventions in scope."""
    return coach_feed(user_id=user_id, org_id=org_id, category=category, limit=limit)
