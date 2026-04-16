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
from seerai.privacy import Visibility, privacy_surface


def _subject(user_id: str | None = None, **_) -> str | None:
    return user_id


router = APIRouter(tags=["coach"])


@router.get("/coach/summary")
@privacy_surface(Visibility.INDIVIDUAL, subject=_subject)
def get_coach_summary(
    user_id: str | None = None,
    org_id: str | None = None,
    category: CoachCategory | None = None,
) -> CoachSummary:
    """Without · with · delta KPIs for the filter scope."""
    return coach_summary(user_id=user_id, org_id=org_id, category=category)


@router.get("/coach/feed")
@privacy_surface(Visibility.INDIVIDUAL, subject=_subject)
def get_coach_feed(
    user_id: str | None = None,
    org_id: str | None = None,
    category: CoachCategory | None = None,
    limit: int = 50,
) -> list[CoachFeedItem]:
    """Most-recent coach interventions in scope."""
    return coach_feed(user_id=user_id, org_id=org_id, category=category, limit=limit)
